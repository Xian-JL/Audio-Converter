import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from server.basic_harmony import generate_basic_harmony, palette, resources
from server.melody_score import generate_melody_score
from server import app as service

ROOT=Path(__file__).resolve().parents[1]

def simple(notes=None,duration=8,key='C major',meter='4/4'):
    return generate_melody_score({'duration':duration,'notes':notes if notes is not None else [{'start':0,'end':3.8,'midi':60},{'start':4,'end':7.8,'midi':67}], 'sourceSha256':'a'*64},120,meter,key)

class BasicHarmonyTests(unittest.TestCase):
    def test_actual_gf_determinism_and_no_melody_changes(self):
        score=json.loads((ROOT/'tests/fixtures/ember-score.json').read_text(encoding='utf-8'));before=copy.deepcopy(score)
        result=generate_basic_harmony(score)
        self.assertEqual(result,generate_basic_harmony(score));self.assertEqual(score,before)
        self.assertEqual(len(result['bars']),len(score['measures']))
        self.assertEqual(len(ET.fromstring(result['xml']).findall('.//harmony')),len(result['writtenChords']))
        old=ET.fromstring(score['xml']);new=ET.fromstring(result['xml'])
        self.assertEqual([ET.tostring(n) for n in old.findall('.//note')],[ET.tostring(n) for n in new.findall('.//note[staff="1"]')])
        self.assertEqual(new.findtext('.//clef-octave-change'),'-1')
        self.assertEqual(new.findtext('.//staves'),'2')
        self.assertEqual(new.findtext('.//clef[@number="2"]/sign'),'F')
        bar_ticks=score['divisions']*4
        for measure in new.findall('.//measure'):
            self.assertEqual(int(measure.findtext('backup/duration')),bar_ticks)
            for staff in ('1','2'):
                self.assertEqual(sum(int(n.findtext('duration')) for n in measure.findall(f'note[staff="{staff}"]') if n.find('chord') is None),bar_ticks)
        for bar,event in zip(result['bars'],result['events']):
            self.assertIn(bar['quality'],('major','minor','dim','7','none'))
            if bar['pitches']:
                self.assertGreaterEqual(min(bar['pitches']),48);self.assertLessEqual(max(bar['pitches']),67)
                self.assertLessEqual(max(bar['pitches'])-min(bar['pitches']),12)
            self.assertLessEqual(event['end'],score['duration'])
        self.assertEqual(len(resources()['templates']),130)

    def test_locks_survive_other_edits_and_phrases(self):
        score=simple();locked=generate_basic_harmony(score,{'1':'7:dim','2':'none'},[1,3])
        self.assertEqual(locked['bars'][0]['chordId'],'7:dim');self.assertTrue(locked['bars'][0]['locked'])
        self.assertTrue(locked['bars'][0]['needsReview'])
        self.assertEqual(locked['bars'][1]['pitches'],[])
        other=generate_basic_harmony(score,{'1':'7:dim','2':'none','4':'5:7'},[1,2,3])
        self.assertEqual(other['bars'][0]['chordId'],locked['bars'][0]['chordId'])
        self.assertEqual(other['bars'][3]['chordId'],'5:7')

    def test_silent_bars_stay_empty_and_manual_chords_work(self):
        score=simple([{'start':2.2,'end':3.8,'midi':60}])
        result=generate_basic_harmony(score)
        self.assertEqual([b['number'] for b in result['bars'] if b['chordId']=='none'],[1,3,4])
        self.assertEqual(len(result['events']),1)
        xml=ET.fromstring(result['xml'])
        self.assertFalse(xml.find('part/measure').findall('note[staff="2"][pitch]'))
        result=generate_basic_harmony(score,{'1':'1:major'})
        self.assertTrue(result['bars'][0]['pitches'])
        self.assertEqual(result['events'][0]['start'],0)
        with self.assertRaises(ValueError):generate_basic_harmony(simple([],2))

    def test_transposition_and_minor_dominant_palette(self):
        first=simple();second=simple([{'start':n['start'],'end':n['end'],'midi':n['midi']+2} for n in first['notes']],key='D major')
        self.assertEqual([b['chordId'] for b in generate_basic_harmony(first)['bars']],[b['chordId'] for b in generate_basic_harmony(second)['bars']])
        chords={c['id']:c for c in palette('A minor')}
        self.assertEqual(chords['5:major']['name'],'E');self.assertEqual(chords['5:7']['pitchClasses'],[4,8,11,2])
        for meter in ('3/4','6/8','5/4','7/8'):
            score=simple(meter=meter);h=generate_basic_harmony(score)
            self.assertEqual([(b['start'],b['end']) for b in h['bars']],[(b['start'],b['end']) for b in score['measures']])

    def test_reject_invalid_locks_and_boundaries(self):
        score=simple()
        for locks in ([],{'0':'1:major'},{'99':'1:major'},{'1':'1:maj7'},{'01':'1:major'},{'1':[]}):
            with self.assertRaises(ValueError):generate_basic_harmony(score,locks)
        for phrases in ([],[2],[1,1],[1,3,2],[1,99],[True]):
            with self.assertRaises(ValueError):generate_basic_harmony(score,{},phrases)

    def test_endpoint_requires_same_melody_and_local_origin(self):
        source={'duration':8,'notes':[{'start':0,'end':3,'midi':60}],'engine':'game'}
        score=generate_melody_score(source,120,'4/4','C major');job='f'*32
        with tempfile.TemporaryDirectory() as directory,patch.object(service,'RUNTIME',Path(directory)):
            target=service.owned_dir(job);target.mkdir();(target/'analysis.json').write_text(json.dumps(source),encoding='utf-8');service.jobs[job]={'analysisReady':True}
            try:
                client=service.app.test_client();body={'bpm':120,'meter':'4/4','key':'C major','sourceFingerprint':score['scoreFingerprint'],'locks':{'1':'5:7'}}
                reply=client.post(f'/api/jobs/{job}/harmony',json=body)
                self.assertEqual(reply.status_code,200);self.assertEqual(reply.json['bars'][0]['chordId'],'5:7')
                self.assertEqual(json.loads((target/'analysis.json').read_text(encoding='utf-8')),source)
                self.assertEqual(client.post(f'/api/jobs/{job}/harmony',json={**body,'sourceFingerprint':'stale'}).status_code,409)
                self.assertEqual(client.post(f'/api/jobs/{job}/harmony',json={**body,'locks':{'1':'bad'}}).status_code,400)
                self.assertEqual(client.post(f'/api/jobs/{job}/harmony',json=body,headers={'Origin':'https://example.com'}).status_code,403)
            finally:service.jobs.pop(job,None)

if __name__=='__main__':unittest.main()
