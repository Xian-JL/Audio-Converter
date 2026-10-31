import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from server.emotional_score import checked,condition,quadrant,emit_notes,pitch_for,pitch_tokens
from server.hybrid import compose_result,generate
from server.project import restore_texture
from server.adaptive_harmony import generate as harmony_for_score
from server.melody_score import generate_melody_score
from server import app as service


def fixture():
    raw={'duration':12.,'engine':'game','sourceSha256':'a'*64,'notes':[{'id':'gf-1','start':4.,'end':7.9,'midi':60}]}
    score=generate_melody_score(raw,120,'4/4','C major');return raw,score,harmony_for_score(score)


class EmotionTests(unittest.TestCase):
    def test_explicit_affect_and_contour_are_validated_and_reproducible(self):
        settings=checked();self.assertEqual(settings,{'engine':'emo','feeling':'sad','contour':'rising'})
        start,end=condition(settings,0),condition(settings,1)
        self.assertLess(start[0],0);self.assertEqual(start[0],end[0]);self.assertLess(start[1],end[1])
        self.assertEqual(quadrant(start),'Q3');self.assertEqual(quadrant(end),'Q2')
        falling={**settings,'contour':'falling'};self.assertEqual(condition(falling,0),end)
        for bad in ([],{},True,{**settings,'feeling':[]},{**settings,'engine':'unknown'},{**settings,'extra':1}):
            with self.assertRaises(ValueError):checked(bad)

    def test_score_conversion_preserves_boundaries_and_minor_mapping_is_deterministic(self):
        bars=[{'playStart':10.,'playEnd':12.},{'playStart':12.,'playEnd':14.}];notes=[]
        emit_notes(notes,0,bars,12,8,60,.7)
        self.assertEqual(notes,[{'start':11.5,'end':12.5,'midi':60,'velocity':.7}])
        emit_notes(notes,1,bars,12,16,72,.5);self.assertEqual(notes[-1]['end'],14.)
        for key in ('C major','D major','Bb major'):
            for midi in range(36,85):
                octave,roman=pitch_tokens(key,midi);self.assertEqual(pitch_for(key,int(octave.split('_')[-1]),roman.split('_')[-1]),midi)
        self.assertEqual(pitch_for('A minor',4,'III'),pitch_for('A minor',4,'III'))

    def test_velocity_and_emotion_survive_generation_and_reopen_without_model(self):
        _,score,harmony=fixture();before=copy.deepcopy(score)
        settings={'engine':'midi-emotion','feeling':'sad','contour':'rising'}
        decoded=[{'start':.1,'end':1.,'midi':60,'velocity':.2},{'start':.1,'end':1.,'midi':64,'velocity':.8}]
        with patch('server.emotional_score.infer',return_value=(decoded,[],{'version':'test'})) as infer:
            take=generate(score,harmony,3,provided=[{'firstMeasure':1,'lastMeasure':2}],emotion=settings);infer.assert_called_once()
        self.assertEqual(score,before);self.assertEqual(take['settings']['mode'],'hybrid-v2');self.assertEqual(take['settings']['emotion'],settings)
        actual=sorted((e['start'],e['end'],p,e['velocity']) for e in take['events'] if e['role']=='instrumental' for p in e['pitches'])
        self.assertEqual(actual,sorted((n['start'],n['end'],n['midi'],n['velocity']) for n in decoded))
        self.assertEqual(restore_texture(take,score,harmony)['events'],take['events'])
        for value in ('missing','null','badengine','unbounded'):
            bad=copy.deepcopy(take)
            if value=='missing':del bad['settings']['emotion']
            elif value=='null':bad['settings']['emotion']=None
            elif value=='badengine':bad['settings']['emotion']['engine']='unknown'
            else:bad['events'][0]['velocity']=2
            with self.assertRaises(ValueError):restore_texture(bad,score,harmony)

    def test_bad_emotion_api_input_does_not_launch_inference(self):
        raw,score,harmony=fixture();job='c'*32
        with tempfile.TemporaryDirectory() as temporary,patch.object(service,'RUNTIME',Path(temporary)),patch.dict(service.jobs,{},clear=True):
            path=service.owned_dir(job);path.mkdir();(path/'analysis.json').write_text(json.dumps(raw),encoding='utf-8');service.jobs[job]={'analysisReady':True}
            body={'bpm':120,'meter':'4/4','key':'C major','sourceFingerprint':score['scoreFingerprint'],'harmonyFingerprint':harmony['fingerprint'],'emotion':{'engine':'unknown','feeling':'sad','contour':'rising'}}
            with patch('server.app.run_texture') as run:
                response=service.app.test_client().post(f'/api/jobs/{job}/texture',json=body)
                self.assertEqual(response.status_code,400);run.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec('torch'),'Optional CPU inference dependency')
    def test_midi_incremental_logits_match_full_forward_on_condition_and_prefix_changes(self):
        import torch
        from server.emotion_runtime import module,MidiLogits,ROOT
        source=module('_test_emotion_midi',ROOT/'vendor/midi-emotion/src/models/music_multi.py')
        torch.manual_seed(9)
        model=source.MusicTransformerMulti(embedding_dim=32,d_inner=64,d_condition=8,vocab_size=64,num_layer=2,num_head=4,max_seq=64,dropout=0.,pad_token=0).eval()
        cached=MidiLogits(model)
        for tokens,values in [([1,2,3],[-.7,-.2]),([1,2,3,4],[-.7,-.2]),([1,2,3,4,5],[-.7,-.2]),([1,2,3,4,5],[-.7,.7]),([6,7],[-.7,.7])]:
            with torch.inference_mode():expected=model(torch.tensor([tokens]),torch.tensor([values]))[0,-1]
            self.assertTrue(torch.allclose(cached(tokens,values),expected,atol=1e-5,rtol=1e-5))

    @unittest.skipUnless(importlib.util.find_spec('torch') and importlib.util.find_spec('transformers') and Path('models/emo-disentanger/resource-manifest.json').exists(),'Optional local EMO weights')
    def test_emo_causal_cpu_cache_and_actual_checkpoint_compatibility(self):
        import torch
        from server.emotion_runtime import emo_models,EmoPerformanceLogits
        _,model,vocabs,_=emo_models();v= vocabs[1];tokens=[v.index(x) for x in ('Emotion_Q2','Key_C','Track_LeadSheet','Bar_None')];segments=[0]*len(tokens);cached=EmoPerformanceLogits(model)
        for word in ('Beat_0','Note_Octave_4','Note_Degree_I'):
            tokens.append(v.index(word));segments.append(0)
            with torch.inference_mode():expected=model(torch.tensor([tokens]),torch.tensor([segments]))[0,-1]
            self.assertTrue(torch.allclose(cached(tokens,segments),expected,atol=1e-4,rtol=1e-4))
        with torch.inference_mode():
            original=model(torch.tensor([tokens]),torch.tensor([segments]))[0,0]
            changed=tokens.copy();changed[-1]=v.index('Note_Degree_V')
            future=model(torch.tensor([changed]),torch.tensor([segments]))[0,0]
        self.assertTrue(torch.equal(original,future))


if __name__=='__main__':unittest.main()
