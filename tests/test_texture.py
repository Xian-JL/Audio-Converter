import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from server import app as service
from server.melody_score import generate_melody_score
from server.basic_harmony import generate_basic_harmony
from server.accompaniment import generate_accompaniment, reduce_left_hand, render_texture, CACHE

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

    def test_invalid_settings_and_meter_do_not_load_model(self):
        _,score,harmony=fixture()
        for options in ({'density':True},{'variant':9},{'style':'unknown'}):
            with self.assertRaises(ValueError):generate_accompaniment(score,harmony,**options)
        with self.assertRaisesRegex(ValueError,'4/4'):generate_accompaniment({**score,'meter':'3/4'},harmony)

    def test_real_cpu_inference_deterministic_and_distinct_alternatives(self):
        _,score,harmony=fixture();CACHE.clear();before=copy.deepcopy((score,harmony))
        first=generate_accompaniment(score,harmony)
        repeat=generate_accompaniment(score,harmony)
        alternate=generate_accompaniment(score,harmony,'flowing',2,2)
        self.assertEqual(first,repeat);self.assertNotEqual(first['events'],alternate['events'])
        self.assertEqual(first['sourceFingerprint'],score['scoreFingerprint'])
        self.assertEqual(first['harmonyFingerprint'],harmony['fingerprint'])
        self.assertTrue(first['references']);self.assertEqual((score,harmony),before)
        first['events'].clear();self.assertTrue(generate_accompaniment(score,harmony)['events'])
        Path('tests/output/inference.json').write_text(json.dumps({'seconds':repeat['generationSeconds'],'attacks':len(repeat['events']),'alternativeAttacks':len(alternate['events']),'model':repeat['model']},indent=2),encoding='utf-8')

    def test_api_rejects_stale_score_and_harmony_without_inference(self):
        result,score,harmony=fixture();identifier='c'*32
        with tempfile.TemporaryDirectory() as temporary,patch.object(service,'RUNTIME',Path(temporary)):
            directory=service.owned_dir(identifier);directory.mkdir();(directory/'analysis.json').write_text(json.dumps(result),encoding='utf-8')
            service.jobs[identifier]={'analysisReady':True,'name':'test.flac'}
            try:
                client=service.app.test_client();body={'bpm':68,'meter':'4/4','key':'C major','anchorNoteId':'gf-000001','sourceFingerprint':score['scoreFingerprint'],'harmonyFingerprint':harmony['fingerprint'],'locks':{'2':'5:7'}}
                self.assertEqual(client.post(f'/api/jobs/{identifier}/texture',json={**body,'sourceFingerprint':'stale'}).status_code,409)
                self.assertEqual(client.post(f'/api/jobs/{identifier}/texture',json={**body,'harmonyFingerprint':'stale'}).status_code,409)
                with patch('server.accompaniment.generate_accompaniment',side_effect=ValueError('Accompaniment resources are missing.')):
                    response=client.post(f'/api/jobs/{identifier}/texture',json=body)
                    self.assertEqual(response.status_code,400);self.assertIn('resources',response.json['error'])
                self.assertEqual(client.post(f'/api/jobs/{identifier}/harmony',json=body).status_code,200)
            finally:service.jobs.pop(identifier,None)

if __name__=='__main__':unittest.main()
