import copy
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from server import app as service
from server.melody_score import generate_melody_score
from server.basic_harmony import generate_basic_harmony
from server.accompaniment import generate_accompaniment, perform_model_notes, model_notes, reduce_left_hand, render_texture, CACHE
from server.project import restore_texture

Path('tests/output').mkdir(parents=True,exist_ok=True)

def fixture():
    old=json.loads(Path('tests/fixtures/ember-score.json').read_text(encoding='utf-8'))
    result={k:old[k] for k in ('duration','notes','engineSignature','sourceSha256')};result['engine']='game'
    score=generate_melody_score(result,68,'4/4','C major','gf-000001')
    return result,score,generate_basic_harmony(score,{'2':'5:7'})

class TextureTests(unittest.TestCase):
    def test_reduction_protects_fixed_harmony_register_and_measure_lengths(self):
        _,score,harmony=fixture();before=copy.deepcopy((score,harmony));step=score['divisions']//4
        proposals=[{'tick':t,'length':step*5,'pitches':[25,44,61,78,91]} for t in range(0,score['measures'][-1]['endTick'],step)]
        written=reduce_left_hand(score,harmony,proposals,2)
        self.assertTrue(written)
        palette={c['id']:c['pitchClasses'] for c in harmony['choices']}
        for e in written:
            self.assertTrue(1<=len(e['pitches'])<=3)
            self.assertTrue(all(48<=p<=64 and p%12 in palette[e['chordId']] for p in e['pitches']))
            self.assertLessEqual(max(e['pitches'])-min(e['pitches']),12)
            self.assertGreater(e['endTick'],e['startTick'])
        for a,b in zip(written,written[1:]):self.assertLessEqual(a['endTick'],b['startTick'])
        events,notation,xml,_=render_texture(score,harmony,written)
        self.assertTrue(events);self.assertTrue(notation)
        root=ET.fromstring(xml);original=ET.fromstring(score['xml'])
        for old,new,meta in zip(original.findall('./part/measure'),root.findall('./part/measure'),score['measures']):
            self.assertEqual([ET.tostring(n) for n in old.findall('note')],[ET.tostring(n) for n in new.findall('note[staff="1"]')])
            length=meta['endTick']-meta['startTick']
            for staff in ('1','2'):
                self.assertEqual(sum(int(n.findtext('duration')) for n in new.findall(f'note[staff="{staff}"]') if n.find('chord') is None),length)
        self.assertEqual((score,harmony),before)

    def test_unsupported_meter_does_not_load_model(self):
        _,score,harmony=fixture()
        with patch('server.amt_model.infer') as infer:
            with self.assertRaisesRegex(ValueError,'4/4'):generate_accompaniment({**score,'meter':'3/4'},harmony)
            infer.assert_not_called()

    def test_raw_tones_survive_overlap_chord_conflicts_and_bar_boundaries(self):
        _,score,harmony=fixture();CACHE.clear();before=copy.deepcopy((score,harmony))
        first=next(b for b in harmony['bars'] if b['root'] is not None);tick=first['startTick'];step=score['divisions']//4
        proposals=[{'tick':tick,'pitches':[25,44,61,78,91],'length':step,'tones':[{'midi':p,'length':n*step} for p,n in zip([25,44,61,78,91],[24,2,4,6,8])]},
                   {'tick':tick+step,'pitches':[25,61],'length':step*3,'tones':[{'midi':25,'length':step*3},{'midi':61,'length':step*19}]}]
        decoded=[{'start':p['tick']*60/score['bpm']/score['divisions'],'end':(p['tick']+t['length'])*60/score['bpm']/score['divisions'],'midi':t['midi']} for p in proposals for t in p['tones']]
        with patch('server.amt_model.infer',return_value=(decoded,[],{'commit':'test','files':{}})),patch('server.accompaniment.reduce_left_hand',side_effect=AssertionError('must not reduce')),patch('server.accompaniment.layer_left_hand',side_effect=AssertionError('must not layer')):
            generated=generate_accompaniment(score,harmony)
        expected=Counter((round(n['start'],6),round(n['end'],6),n['midi']) for n in decoded)
        actual=Counter((n['start'],n['end'],m) for n in generated['events'] for m in n['pitches'])
        self.assertEqual(expected,actual);self.assertEqual((score,harmony),before)
        self.assertEqual(generated['settings'],{'mode':'amt','seed':0})
        self.assertGreater(max(n['voice'] for n in generated['events']),4)
        # XML ties split a long tone across measures without shortening playback.
        root=ET.fromstring(generated['xml']);original=ET.fromstring(score['xml'])
        for old,new,meta in zip(original.findall('./part/measure'),root.findall('./part/measure'),score['measures']):
            self.assertEqual([ET.tostring(n) for n in old.findall('note')],[ET.tostring(n) for n in new.findall('note[staff="1"]')])
            for voice in {str(n['voice']) for n in generated['events']}:
                self.assertEqual(sum(int(n.findtext('duration')) for n in new.findall(f'note[voice="{voice}"]') if n.find('chord') is None),meta['endTick']-meta['startTick'])
        restored=restore_texture(generated,score,harmony)
        self.assertEqual(restored['events'],generated['events']);self.assertEqual(restored['writtenChords'],generated['writtenChords']);self.assertEqual(restored['xml'],generated['xml'])
        for bad in ([-1],[128],[True]):
            damaged=copy.deepcopy(generated);damaged['events'][0]['pitches']=bad;damaged['writtenChords'][0]['pitches']=bad
            with self.assertRaises(ValueError):restore_texture(damaged,score,harmony)

    def test_real_cpu_inference_is_preserved_and_deterministic(self):
        source,_,_=fixture();source['duration']=12.;source['notes']=[{**n,'end':min(12.,n['end'])} for n in source['notes'] if n['start']<12.]
        score=generate_melody_score(source,68,'4/4','C major');harmony=generate_basic_harmony(score);CACHE.clear();before=copy.deepcopy((score,harmony))
        from server.amt_model import infer
        captured=[]
        def decode(*args,**kwargs):
            value=infer(*args,**kwargs);captured.append(value);return value
        with patch('server.amt_model.infer',side_effect=decode):
            first=generate_accompaniment(score,harmony)
        decoded,_,_=captured[0]
        repeat=generate_accompaniment(score,harmony)
        self.assertEqual(first,repeat)
        expected=perform_model_notes(score,harmony,decoded)[1]
        self.assertEqual(Counter((n['startTick'],n['endTick'],p) for n in first['writtenChords'] for p in n['pitches']),Counter((n['startTick'],n['endTick'],p) for n in expected for p in n['pitches']))
        self.assertEqual(restore_texture(first,score,harmony)['events'],first['events'])
        self.assertEqual(first['sourceFingerprint'],score['scoreFingerprint'])
        self.assertEqual(first['harmonyFingerprint'],harmony['fingerprint'])
        self.assertTrue(first['references']);self.assertEqual((score,harmony),before)
        first['events'].clear();self.assertTrue(generate_accompaniment(score,harmony)['events'])
        Path('tests/output/inference.json').write_text(json.dumps({'seconds':repeat['generationSeconds'],'events':len(repeat['events']),'decodedTones':len(decoded),'voices':len({e['voice'] for e in repeat['events']}),'model':repeat['model']},indent=2),encoding='utf-8')

    def test_api_rejects_stale_score_and_harmony_without_inference(self):
        result,score,harmony=fixture();identifier='c'*32
        with tempfile.TemporaryDirectory() as temporary,patch.object(service,'RUNTIME',Path(temporary)):
            directory=service.owned_dir(identifier);directory.mkdir();(directory/'analysis.json').write_text(json.dumps(result),encoding='utf-8')
            service.jobs[identifier]={'analysisReady':True,'name':'test.flac'}
            try:
                client=service.app.test_client();body={'bpm':68,'meter':'4/4','key':'C major','anchorNoteId':'gf-000001','sourceFingerprint':score['scoreFingerprint'],'harmonyFingerprint':harmony['fingerprint'],'locks':{'2':'5:7'}}
                self.assertEqual(client.post(f'/api/jobs/{identifier}/texture',json={**body,'sourceFingerprint':'stale'}).status_code,409)
                self.assertEqual(client.post(f'/api/jobs/{identifier}/texture',json={**body,'harmonyFingerprint':'stale'}).status_code,409)
                with patch('server.app.run_texture') as worker:
                    response=client.post(f'/api/jobs/{identifier}/texture',json=body)
                    self.assertEqual(response.status_code,409);worker.assert_not_called()
                self.assertEqual(client.post(f'/api/jobs/{identifier}/harmony',json=body).status_code,200)
            finally:service.jobs.pop(identifier,None)

if __name__=='__main__':unittest.main()
