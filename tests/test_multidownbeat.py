"""Five-point calibration changes notation, never the recognized performance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from server import app as service
from server.melody_score import generate_melody_score
from server.meter_grid import score_grid
from server.basic_harmony import generate_basic_harmony
from server.editing import edit_score
from server.project import normalize_project

PARAMS={'bpm':120,'meter':'4/4','key':'C major'}


def material():
    starts=[.1,.5,1.1,2.,3.7,4.7,5.6,6.4,7.8,8.55,9.2,10.4,11.6,12.9,13.6,15.2,16.1,17.,18.]
    source={'duration':19.,'engine':'game','sourceSha256':'a'*64,'engineSignature':{'test':'fixed'},'notes':[{'id':f'gf-{i+1:06d}','start':t,'end':t+.2,'midi':60+(i%5),'midiFloat':float(60+i%5)} for i,t in enumerate(starts)]}
    refs=[{'noteId':source['notes'][i]['id'],'measure':m} for i,m in zip((1,5,9,13,17),(1,3,5,7,9))]
    return source,refs


class MultiDownbeatTests(unittest.TestCase):
    def test_supported_meters_and_audio_zero_remain_invertible(self):
        source,refs=material()
        for meter in ('3/4','4/4','5/4','6/8','7/8'):
            with self.subTest(meter=meter):
                score=generate_melody_score(source,120,meter,'C major',downbeats=refs);grid=score_grid(score)
                for p in score['downbeats']:
                    bar=score['measures'][p['measureNumber']-1]
                    self.assertEqual(bar['displayNumber'],p['measure']);self.assertAlmostEqual(bar['start'],p['time'],6)
                self.assertAlmostEqual(grid.time(grid.tick(source['duration'])),source['duration'],7)
        source['notes'][0]['start']=0
        zero=[{'noteId':source['notes'][0]['id'],'measure':1}]+refs[1:]
        score=generate_melody_score(source,**PARAMS,downbeats=zero)
        self.assertFalse(score['measures'][0]['pickup']);self.assertEqual(score['measures'][0]['start'],0)
        with self.assertRaises(ValueError):generate_melody_score(source,**PARAMS,downbeats=[{**zero[0],'measure':2}])

    def test_five_points_land_on_bar_starts_and_all_xml_measures_balance(self):
        source,refs=material();before=copy.deepcopy(source)
        base=generate_melody_score(source,**PARAMS)
        score=generate_melody_score(source,**PARAMS,downbeats=refs);grid=score_grid(score)
        self.assertEqual(score['events'],base['events']);self.assertEqual(source,before)
        self.assertEqual(score['baseFingerprint'],base['scoreFingerprint'])
        self.assertEqual(len(score['downbeats']),5)
        for p in score['downbeats']:
            note=next(n for n in score['notes'] if n['id']==p['noteId']);bar=score['measures'][p['measureNumber']-1]
            self.assertEqual(bar['displayNumber'],p['measure']);self.assertEqual(note['startTick'],bar['startTick']);self.assertAlmostEqual(bar['start'],note['start'],6)
        for tick in (0,13,32,100,256,512,900,1250):self.assertAlmostEqual(grid.tick(grid.time(tick)),tick,7)
        harmony=generate_basic_harmony(score);root=ET.fromstring(harmony['xml'])
        for meta,measure in zip(score['measures'],root.findall('./part/measure')):
            for staff in ('1','2'):
                self.assertEqual(sum(int(n.findtext('duration')) for n in measure.findall(f'note[staff="{staff}"]') if n.find('chord') is None),meta['endTick']-meta['startTick'])
        self.assertAlmostEqual(grid.time(score['notes'][-2]['startTick']+128)-grid.time(score['notes'][-2]['startTick']),2,6)

    def test_middle_reference_only_changes_its_two_neighboring_intervals(self):
        source,refs=material();old=generate_melody_score(source,**PARAMS,downbeats=refs)
        changed=copy.deepcopy(refs);changed[2]['measure']+=1
        new=generate_melody_score(source,**PARAMS,downbeats=changed)
        for a,b in zip(old['notes'],new['notes']):
            if a['end']<=4.7 or a['start']>=12.9:self.assertEqual(a,b)
        self.assertNotEqual(old['notes'][9]['startTick'],new['notes'][9]['startTick'])
        self.assertEqual(old['events'],new['events'])
        extra={**source,'notes':sorted(source['notes']+[{'id':'extra','start':6.8,'end':6.9,'midi':60}],key=lambda n:n['start'])}
        added=generate_melody_score(extra,**PARAMS,downbeats=refs)
        self.assertEqual({n['id']:n['startTick'] for n in added['notes'] if n['start']>=8.55},{n['id']:n['startTick'] for n in old['notes'] if n['start']>=8.55})

    def test_bad_references_are_rejected_and_anchor_notes_are_protected(self):
        source,refs=material()
        invalid=([],refs+[refs[-1]],list(reversed(refs)),[refs[0],refs[0]],[{**refs[0],'measure':True}],[{**refs[0],'measure':0}],[{**refs[0],'measure':4097}],[{'noteId':'missing','measure':1}],{'points':refs})
        for points in invalid:
            with self.subTest(points=points):
                with self.assertRaises(ValueError):generate_melody_score(source,**PARAMS,downbeats=points)
        score=generate_melody_score(source,**PARAMS,downbeats=refs)
        body={**PARAMS,'sourceFingerprint':score['scoreFingerprint'],'downbeats':refs}
        with self.assertRaisesRegex(ValueError,'downbeat'):edit_score(source,{**body,'operation':{'kind':'delete','id':refs[3]['noteId']}})
        edited=edit_score(source,{**body,'operation':{'kind':'update','id':'gf-000003','midi':67}})['score']
        self.assertEqual(edited['downbeats'],score['downbeats'])

    def test_project_and_api_roundtrip_retain_all_five_points(self):
        source,refs=material();base=generate_melody_score(source,**PARAMS);score=generate_melody_score(source,**PARAMS,downbeats=refs);h=generate_basic_harmony(score)
        payload={'kind':'audio-converter-project','schemaVersion':1,'source':{**source,**PARAMS,'name':'synthetic.flac','scoreFingerprint':base['scoreFingerprint']},'versions':[{}, {'downbeats':refs,'harmony':{'fingerprint':h['fingerprint'],'locks':{},'phraseStarts':h['phraseStarts'],'chordOffsetMs':0}}],'activeVersion':1}
        _,_,workspace=normalize_project(payload)
        self.assertEqual(workspace['versions'][1]['score'],{**score,'sourceName':'synthetic.flac'})
        job='a'*32
        with tempfile.TemporaryDirectory() as temporary,patch.object(service,'RUNTIME',Path(temporary)),patch.dict(service.jobs,{},clear=True):
            directory=service.owned_dir(job);directory.mkdir();path=directory/'analysis.json';path.write_text(json.dumps(source),encoding='utf-8');original=path.read_bytes()
            service.jobs[job]={'analysisReady':True,'name':'synthetic.flac'};client=service.app.test_client()
            body={**PARAMS,'sourceFingerprint':base['scoreFingerprint'],'downbeats':refs,'includeHarmony':True}
            r=client.post(f'/api/jobs/{job}/rebar',json=body);self.assertEqual(r.status_code,200,r.json)
            self.assertEqual(r.json['score']['downbeats'],score['downbeats']);self.assertEqual(path.read_bytes(),original)
            follow={**body,'sourceFingerprint':score['scoreFingerprint']}
            response=client.post(f'/api/jobs/{job}/harmony',json=follow);self.assertEqual(response.status_code,200,response.json)
            with patch('server.app.run_texture',return_value={'accepted':True}) as worker:
                response=client.post(f'/api/jobs/{job}/texture',json={**follow,'harmonyFingerprint':response.json['fingerprint']})
                self.assertEqual(response.status_code,400,response.json);self.assertIn('two complete',response.json['error']);worker.assert_not_called()


if __name__=='__main__':unittest.main()
