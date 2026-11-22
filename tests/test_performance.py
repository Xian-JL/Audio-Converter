"""Polyphonic identity, independent edits, score timing and schema-3/API boundaries."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
from server.performance_score import generate, checked_notes
from server.performance_editing import edit
from server.project import normalize_project
from server import app as service

PARAMS={'bpm':120,'meter':'4/4','key':'C major'}


def source(kind='piano'):
    return {'sourceKind':kind,'duration':8.,'sourceSha256':'a'*64,'engine':'transkun' if kind=='piano' else 'basic-pitch','engineSignature':{'version':'test','files':{}},'notes':[
        {'id':'bass','start':0.,'end':3.,'midi':48,'velocity':.4},
        {'id':'c','start':0.,'end':1.,'midi':60,'velocity':.6},
        {'id':'e','start':0.,'end':1.,'midi':64,'velocity':.8},
        {'id':'repeat','start':.5,'end':2.,'midi':60,'velocity':.5}]}


def project(raw=None):
    raw=raw or source();score=generate(raw,PARAMS)
    return {'kind':'audio-converter-project','schemaVersion':3,'source':{**raw,**PARAMS,'name':'piano.flac','scoreFingerprint':score['scoreFingerprint']},'versions':[{'scoreMode':'performance'}],'activeVersion':0}


class PerformanceTests(unittest.TestCase):
    def test_same_pitch_unison_events_keep_distinct_notation_voices(self):
        raw=source();raw['notes'].append({**raw['notes'][1],'id':'other-hand'})
        score=generate(raw,PARAMS)
        unison=[n for n in score['notes'] if n['id'] in ('c','other-hand')]
        self.assertEqual(len({(n['staff'],n['voice']) for n in unison}),2)
        self.assertEqual({f['noteId'] for f in score['fragments']},{n['id'] for n in raw['notes']})

    def test_source_comparison_and_pedals_are_bound_to_project_identity(self):
        raw=source('guzheng');raw['baselineNotes']=copy.deepcopy(raw['notes']);raw['controllers']=[{'controller':64,'start':0,'end':1,'value':127}]
        saved=project(raw);normalize_project(saved)
        for field in ('baselineNotes','controllers'):
            bad=copy.deepcopy(saved);bad['source'][field]=[]
            with self.subTest(field=field),self.assertRaises(ValueError):normalize_project(bad)

    def test_polyphony_repeated_pitch_and_cross_bar_ties_preserve_every_event(self):
        raw=source();before=copy.deepcopy(raw);score=generate(raw,PARAMS)
        self.assertEqual(raw,before);self.assertEqual(len(score['notes']),4)
        self.assertEqual([(e['id'],e['start'],e['end'],e['pitches'][0]) for e in score['events']],[(n['id'],n['start'],n['end'],n['midi']) for n in checked_notes(raw['notes'],8.)])
        self.assertEqual({f['noteId'] for f in score['fragments']},{n['id'] for n in raw['notes']})
        root=ET.fromstring(score['xml']);self.assertFalse(root.findall('.//clef-octave-change'))
        self.assertEqual(len(root.findall('.//clef')),2);self.assertEqual(len(root.findall('.//chord')),1)
        # Every voice must advance one complete measure, counting chord heads once.
        for measure in root.findall('./part/measure'):
            position=0;maximum=0
            for node in measure:
                if node.tag=='backup':position-=int(node.findtext('duration'));self.assertGreaterEqual(position,0)
                elif node.tag=='note' and node.find('chord') is None:position+=int(node.findtext('duration'));maximum=max(maximum,position)
            self.assertEqual(maximum,256);self.assertEqual(position,256)

    def test_edit_only_one_chord_member_and_reassign_staff(self):
        raw=source();old=generate(raw,PARAMS)
        new=edit(raw,{**PARAMS,'sourceFingerprint':old['scoreFingerprint'],'operation':{'kind':'update','id':'e','midi':65,'staff':2}})['score']
        for note in new['notes']:
            previous=next(n for n in old['notes'] if n['id']==note['id'])
            if note['id']=='e':self.assertEqual((note['midi'],note['staff']),(65,2))
            else:self.assertEqual((note['midi'],note['start'],note['end']),(previous['midi'],previous['start'],previous['end']))
        self.assertEqual(raw['notes'][2]['midi'],64)

    def test_downbeats_retime_notation_without_changing_performance(self):
        raw=source();old=generate(raw,PARAMS);new=generate(raw,{**PARAMS,'downbeats':[{'noteId':'repeat','measure':1}]})
        self.assertEqual(old['events'],new['events']);self.assertEqual(new['baseFingerprint'],old['baseFingerprint']);self.assertNotEqual(new['scoreFingerprint'],old['scoreFingerprint'])
        self.assertEqual(new['downbeats'][0]['noteId'],'repeat')

    def test_project_roundtrip_never_loads_models_and_detects_tampering(self):
        saved=project();first=normalize_project(saved)
        with patch('server.instrument_runtime.transcribe',side_effect=AssertionError('Must not run model')):
            second=normalize_project(json.loads(json.dumps(saved)))
        self.assertEqual(first,second)
        bad=copy.deepcopy(saved);bad['source']['notes'][0]['midi']=49
        with self.assertRaises(ValueError):normalize_project(bad)
        bad=copy.deepcopy(saved);bad['versions'][0]={'scoreMode':'melody'}
        with self.assertRaises(ValueError):normalize_project(bad)

    def test_baseline_and_sparse_pitch_trajectory_survive_data_only_restore(self):
        raw=source('guzheng');raw['notes'][1]['pitchBends']=[[0.,0.],[.5,30.],[1.,0.]];raw['baselineNotes']=copy.deepcopy(raw['notes'][:2])
        original,score,_=normalize_project(project(raw));self.assertEqual(original['notes'],checked_notes(raw['notes'],8.));self.assertEqual(score['sourceBaselineNotes'],checked_notes(raw['baselineNotes'],8.))

    def test_melody_branch_is_separate_and_has_no_vocal_octave_shift(self):
        raw=source();old=generate(raw,PARAMS);lead=generate(raw,{**PARAMS,'scoreMode':'melody'})
        self.assertEqual(raw['notes'],source()['notes']);self.assertLess(lead['noteCount'],old['noteCount'])
        self.assertTrue(all(a['end']<=b['start'] for a,b in zip(lead['notes'],lead['notes'][1:])))
        self.assertNotIn('clef-octave-change',lead['xml'])

    def test_invalid_ids_times_trajectory_and_staff_are_rejected(self):
        raw=source()['notes']
        for update in ({'start':True},{'end':float('nan')},{'midi':128},{'staff':3},{'pitchBends':[[9.,0.]]}):
            bad=copy.deepcopy(raw);bad[0].update(update)
            with self.subTest(update=update),self.assertRaises(ValueError):checked_notes(bad,8.)
        with self.assertRaises(ValueError):checked_notes([raw[0],raw[0]],8.)

    def test_api_does_not_add_accompaniment_to_original_performance(self):
        raw=source();identifier='a'*32
        with tempfile.TemporaryDirectory() as temp,patch.object(service,'RUNTIME',Path(temp)),patch.dict(service.jobs,{},clear=True):
            folder=service.owned_dir(identifier);folder.mkdir();(folder/'analysis.json').write_text(json.dumps(raw),encoding='utf-8');service.jobs[identifier]={'analysisReady':True,'name':'piano.flac'}
            client=service.app.test_client();score=generate(raw,PARAMS)
            response=client.get('/api/jobs/'+identifier+'/score?bpm=120&meter=4/4&key=C+major');self.assertEqual(response.status_code,200)
            response=client.post('/api/jobs/'+identifier+'/harmony',json={**PARAMS,'sourceFingerprint':score['scoreFingerprint']});self.assertEqual(response.status_code,400)
            response=client.post('/api/jobs/'+identifier+'/melody-branch',json={**PARAMS,'sourceFingerprint':score['scoreFingerprint']});self.assertEqual(response.status_code,200)
            lead=response.json['score'];self.assertEqual(lead['scoreMode'],'melody')
            response=client.post('/api/jobs/'+identifier+'/harmony',json={**PARAMS,'scoreMode':'melody','editedNotes':lead['editedNotes'],'sourceFingerprint':lead['scoreFingerprint'],'melodyConfirmed':True,'harmonyPolicy':'adaptive-block-v1'});self.assertEqual(response.status_code,200)


if __name__=='__main__':unittest.main()
