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
from server.meter_grid import score_grid

def material():
    return {'duration':8.5,'engine':'game','notes':[{'start':a,'end':a+.6,'midi':p} for a,p in [(0.1,60),(1.,62),(3.,64),(5.,65),(7.,67)]]}

class DownbeatTests(unittest.TestCase):
    def test_third_beat_becomes_downbeat_without_changing_performance(self):
        source=material();before=copy.deepcopy(source)
        original=generate_melody_score(source,120,'4/4','C major')
        rebuilt=generate_melody_score(source,120,'4/4','C major','gf-000004')
        oldbar=next(m for m in original['measures'] if m['start']<=5<m['end'])
        self.assertEqual((5-oldbar['start'])/.5+1,3)
        anchor=rebuilt['notes'][3];bar=rebuilt['measures'][rebuilt['downbeat']['measureNumber']-1]
        self.assertEqual(anchor['startTick'],bar['startTick']);self.assertEqual(bar['start'],5)
        self.assertEqual(rebuilt['events'],original['events']);self.assertEqual(source,before)
        self.assertEqual(rebuilt['baseFingerprint'],original['scoreFingerprint'])
        self.assertNotEqual(rebuilt['scoreFingerprint'],original['scoreFingerprint'])
        self.assertEqual(rebuilt['measures'][0]['end'],1)
        self.assertTrue(rebuilt['measures'][0]['pickup']);self.assertEqual(rebuilt['measures'][0]['displayNumber'],0)
        self.assertEqual(ET.fromstring(rebuilt['xml']).find('part/measure').get('implicit'),'yes')

    def test_pickup_and_both_staves_have_correct_measure_durations(self):
        for meter in ('3/4','4/4','6/8','5/4','7/8'):
            score=generate_melody_score(material(),120,meter,'C major','gf-000004')
            harmony=generate_basic_harmony(score)
            root=ET.fromstring(harmony['xml']);grid=score_grid(score)
            for meta,measure in zip(score['measures'],root.findall('./part/measure')):
                length=meta['endTick']-meta['startTick']
                self.assertEqual(int(measure.findtext('backup/duration')),length)
                for staff in ('1','2'):
                    self.assertEqual(sum(int(n.findtext('duration')) for n in measure.findall(f'note[staff="{staff}"]') if n.find('chord') is None),length)
                if not meta['pickup']:self.assertEqual(length,grid.bar_ticks)
            for e in harmony['writtenChords']:
                self.assertLessEqual(abs(grid.time(e['startTick'])-e['start']),grid.seconds_per_tick*2)
            selected=score['notes'][3]
            self.assertEqual(selected['startTick'],score['measures'][score['downbeat']['measureNumber']-1]['startTick'])

    def test_first_note_and_zero_phase_anchor(self):
        first=generate_melody_score(material(),120,'4/4','C major','gf-000001')
        self.assertEqual(first['downbeat']['time'],.1);self.assertEqual(first['measures'][1]['start'],.1)
        source={'duration':4,'notes':[{'start':0,'end':1.8,'midi':60},{'start':2,'end':3.8,'midi':62}]}
        base=generate_melody_score(source,120,'4/4','C major')
        anchored=generate_melody_score(source,120,'4/4','C major','gf-000002')
        self.assertFalse(anchored['measures'][0]['pickup']);self.assertEqual(len(base['measures']),len(anchored['measures']))
        self.assertEqual(base['events'],anchored['events'])

    def test_ties_and_dense_anchors_do_not_drop_notes(self):
        source={'duration':8,'notes':[{'start':.1,'end':4.8,'midi':60},{'start':5,'end':7.8,'midi':67}]}
        score=generate_melody_score(source,120,'4/4','C major','gf-000002')
        self.assertTrue(ET.fromstring(score['xml']).findall('.//tie'));self.assertEqual(score['noteCount'],2)
        dense={'duration':.4,'notes':[{'start':i*.05,'end':i*.05+.04,'midi':60} for i in range(8)]}
        score=generate_melody_score(dense,30,'4/4','C major','gf-000006')
        self.assertEqual(score['divisions'],64);self.assertEqual(score['noteCount'],8)
        self.assertEqual(score['notes'][5]['startTick'],score['measures'][1]['startTick'])

    def test_invalid_references_are_rejected(self):
        for anchor in ('','gf-999999',[],{},True):
            with self.assertRaises(ValueError):generate_melody_score(material(),120,'4/4','C major',anchor)

    def test_rebar_api_preserves_original_and_harmonizes_new_grid(self):
        source=material();base=generate_melody_score(source,120,'4/4','C major');job='d'*32
        with tempfile.TemporaryDirectory() as temporary,patch.object(service,'RUNTIME',Path(temporary)):
            directory=service.owned_dir(job);directory.mkdir();path=directory/'analysis.json';path.write_text(json.dumps(source),encoding='utf-8')
            service.jobs[job]={'analysisReady':True,'name':'test.flac'}
            try:
                client=service.app.test_client();payload={'bpm':120,'meter':'4/4','key':'C major','sourceFingerprint':base['scoreFingerprint'],'anchorNoteId':'gf-000004','includeHarmony':True}
                response=client.post(f'/api/jobs/{job}/rebar',json=payload);self.assertEqual(response.status_code,200)
                new=response.json['score'];h=response.json['harmony']
                self.assertEqual(new['events'],base['events']);self.assertEqual(h['locks'],{});self.assertEqual(h['alignment']['offsetMs'],0)
                self.assertEqual(h['sourceFingerprint'],new['scoreFingerprint']);self.assertEqual(json.loads(path.read_text(encoding='utf-8')),source)
                original=client.get(f'/api/jobs/{job}/score?bpm=120&meter=4/4&key=C%20major').json
                self.assertEqual(original['scoreFingerprint'],base['scoreFingerprint'])
                follow=client.post(f'/api/jobs/{job}/harmony',json={**payload,'sourceFingerprint':new['scoreFingerprint'],'locks':{'2':'5:7'}})
                self.assertEqual(follow.status_code,200);self.assertEqual(follow.json['bars'][1]['chordId'],'5:7')
                self.assertEqual(client.post(f'/api/jobs/{job}/rebar',json={**payload,'sourceFingerprint':'stale'}).status_code,409)
                self.assertEqual(client.post(f'/api/jobs/{job}/rebar',json={**payload,'anchorNoteId':'gf-999999'}).status_code,400)
                self.assertEqual(client.post(f'/api/jobs/{job}/rebar',json=payload,headers={'Origin':'https://example.com'}).status_code,403)
            finally:service.jobs.pop(job,None)

if __name__=='__main__':unittest.main()
