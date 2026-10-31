"""AMT control timing, cached inference, partial editing and legacy persistence."""
from collections import Counter
import copy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from server import app as service
from server.accompaniment import generate_accompaniment,perform_model_notes,CACHE
from server.melody_score import generate_melody_score
from server.basic_harmony import generate_basic_harmony
from server.project import restore_texture
from server.amt_model import CachedLogits,chunks,tokens_for,sample_window,DenseGeneration
from server.texture_worker import write_progress

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/anticipation'))
from anticipation import vocab,ops


def fixture():
    source={'engine':'game','duration':12.,'notes':[{'id':f'gf-{i+1:06d}','start':i*.5,'end':i*.5+.4,'midi':60+i%5} for i in range(24)]}
    score=generate_melody_score(source,120,'4/4','C major');return score,generate_basic_harmony(score)


class AmtTests(unittest.TestCase):
    def test_transient_windows_progress_lock_cannot_fail_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'task.texture'
            with patch.object(Path,'replace',side_effect=PermissionError('reader holds file')):
                write_progress(path,{'stage':'generating','progress':.5})
            write_progress(path,{'stage':'generating','progress':1.})
            self.assertTrue(path.with_suffix('.progress').is_file())
    def test_repeated_time_candidate_is_rejected_without_returning_partial_notes(self):
        with patch('server.amt_model.cached_add_token',return_value=[500,vocab.DUR_OFFSET+50,vocab.NOTE_OFFSET+48]):
            with self.assertRaises(DenseGeneration):sample_window(None,None,ops,vocab,None,[],[],-5,4,4,lambda _:None)
    def test_first_control_survives_official_five_second_clip_and_long_notes_split(self):
        raw=[{'start':0.,'end':15.,'midi':60}]
        encoded=tokens_for(raw,-5,53,vocab,True)
        self.assertEqual(encoded[0]-vocab.ATIME_OFFSET,500)
        self.assertEqual(ops.clip(encoded,5,21),encoded)
        self.assertTrue(all(0<d-vocab.ADUR_OFFSET<=999 for d in encoded[1::3]))
        self.assertEqual(sum(d-vocab.ADUR_OFFSET for d in encoded[1::3]),1500)
        self.assertEqual(raw,[{'start':0.,'end':15.,'midi':60}])

    @unittest.skipUnless(importlib.util.find_spec('transformers') and importlib.util.find_spec('torch'),'Optional local AMT inference dependencies')
    def test_cache_matches_full_forward_after_append_and_changed_prefix(self):
        os.environ['USE_TF']='0';os.environ['USE_FLAX']='0'
        from transformers import GPT2Config,GPT2LMHeadModel
        import torch
        torch.manual_seed(7)
        model=GPT2LMHeadModel(GPT2Config(vocab_size=64,n_positions=32,n_embd=32,n_head=2,n_layer=2,attn_pdrop=0.0,resid_pdrop=0.0,embd_pdrop=0.0)).eval()
        cached=CachedLogits(model)
        for sequence in ([1,2,3],[1,2,3,4],[1,2,3,4,5],[7,8,9],[7,8,9,10],[7,8,9,10]):
            direct=CachedLogits(model)(list(sequence),False)
            self.assertTrue(torch.allclose(cached(list(sequence)),direct,atol=1e-5,rtol=1e-5))

    @unittest.skipUnless(importlib.util.find_spec('torch'),'Optional local AMT inference dependencies')
    def test_stream_rolls_in_blocks_and_sampler_cannot_stall_at_one_instant(self):
        import torch
        from anticipation import sample
        from server.amt_model import cached_add_token
        class Logits:
            def __init__(self):self.stream=None;self.window_start=0;self.lengths=[]
            def __call__(self,tokens):self.lengths.append(len(tokens));return torch.zeros(vocab.VOCAB_SIZE)
        step=Logits();tokens=[]
        for i in range(339):tokens.extend([i*10,vocab.DUR_OFFSET+20,vocab.NOTE_OFFSET+48])
        generator=torch.Generator().manual_seed(3)
        first=cached_add_token(step,sample,ops,vocab,generator,tokens,.95,3380);tokens+=first
        cached_add_token(step,sample,ops,vocab,generator,tokens,.95,first[0])
        self.assertGreater(step.window_start,0);self.assertLessEqual(max(step.lengths),1024)
        repeat=[]
        for _ in range(16):repeat.extend([500,vocab.DUR_OFFSET,vocab.REST])
        result=cached_add_token(step,sample,ops,vocab,generator,repeat,.95,500)
        self.assertGreaterEqual(result[0],525)

    def test_raw_performance_not_snapped_and_partial_scope_preserves_outside(self):
        score,h=fixture();CACHE.clear();before=copy.deepcopy(score)
        decoded=[{'start':.013,'end':2.178,'midi':37},{'start':4.023,'end':4.099,'midi':79},{'start':9.012,'end':11.321,'midi':54}]
        meta={'files':{},'commit':'test','revision':'test'}
        with patch('server.amt_model.infer',return_value=(decoded,[],meta)):
            base=generate_accompaniment(score,h,1)
        self.assertEqual(Counter((e['start'],e['end'],p) for e in base['events'] for p in e['pitches']),Counter((n['start'],n['end'],n['midi']) for n in decoded))
        self.assertEqual(restore_texture(base,score,h)['events'],base['events']);self.assertEqual(before,score)
        selection={'firstMeasure':3,'lastMeasure':4}
        changed=[decoded[0],{'start':4.2,'end':5.2,'midi':52},decoded[2]]
        with patch('server.amt_model.infer',return_value=(changed,[],meta)) as infer:
            new=generate_accompaniment(score,h,2,selection=selection,base_arrangement=base)
            self.assertEqual(infer.call_args.args[4],selection)
            self.assertEqual(len(infer.call_args.args[5]),3)
        self.assertEqual(new['settings']['baseFingerprint'],base['fingerprint'])
        outside=lambda events:Counter((e['start'],e['end'],p) for e in events if e['start']<4 or e['start']>=8 for p in e['pitches'])
        self.assertEqual(outside(base['events']),outside(new['events']))
        self.assertEqual(restore_texture(new,score,h)['events'],new['events'])
        self.assertEqual(len(chunks(score,h,selection)),1)
        for bad in ({'firstMeasure':0,'lastMeasure':1},{'firstMeasure':4,'lastMeasure':3},{'firstMeasure':True,'lastMeasure':3}):
            with self.assertRaises(ValueError):generate_accompaniment(score,h,selection=bad,base_arrangement=base)
        stale={**base,'sourceFingerprint':'stale'}
        with self.assertRaises(ValueError):generate_accompaniment(score,h,selection=selection,base_arrangement=stale)

    def test_legacy_model_results_still_restore(self):
        score,h=fixture();decoded=[{'start':1.,'end':1.8,'midi':53}]
        events,written,_,_=perform_model_notes(score,h,decoded)
        old={'sourceFingerprint':score['scoreFingerprint'],'harmonyFingerprint':h['fingerprint'],'fingerprint':'a'*64,'settings':{'mode':'model'},'events':events,'writtenChords':written}
        self.assertEqual(restore_texture(old,score,h)['events'],events)


if __name__=='__main__':unittest.main()
