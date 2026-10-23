import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from server import app as service
from server.editing import edit_score,score_for_request
from server.project import normalize_project
from server.basic_harmony import generate_basic_harmony
from server.accompaniment import layer_left_hand,render_texture
from server.texture_model import choose_donors
import numpy as np

def source():
    return {'engine':'game','duration':4,'sourceSha256':'a'*64,'engineSignature':{'test':'fixed'},'notes':[{'id':f'gf-{i+1:06d}','start':i,'end':i+.8,'midi':60+i,'midiFloat':float(60+i)} for i in range(4)]}

PARAMS={'bpm':120,'meter':'4/4','key':'C major'}
def project():
    raw=source();score=score_for_request(raw,PARAMS)
    return {'kind':'audio-converter-project','schemaVersion':1,'appVersion':'0.3.0','source':{**raw,**PARAMS,'name':'test.flac','scoreFingerprint':score['scoreFingerprint']},'versions':[{}],'activeVersion':0,'textureSets':{},'instruments':['flute','cello'],'voices':[True,False],'position':1.5,'loop':{'enabled':True,'startMeasure':1,'endMeasure':2}}

class WorkspaceTests(unittest.TestCase):
    def test_edit_operations_are_immutable_and_preserve_ids(self):
        raw=source();before=copy.deepcopy(raw);score=score_for_request(raw,PARAMS)
        body={**PARAMS,'sourceFingerprint':score['scoreFingerprint']}
        changed=edit_score(raw,{**body,'operation':{'kind':'update','id':'gf-000002','midi':65,'end':1.95}})['score']
        self.assertEqual(raw,before);self.assertEqual(changed['notes'][1]['id'],'gf-000002');self.assertEqual(changed['events'][1]['pitches'],[65])
        anchored=score_for_request(raw,{**PARAMS,'editedNotes':changed['editedNotes'],'anchorNoteId':'gf-000002'})
        self.assertEqual(anchored['events'],changed['events']);self.assertEqual(anchored['downbeat']['time'],1)
        split=edit_score(raw,{**body,'operation':{'kind':'split','id':'gf-000001','time':.4}})['score']
        self.assertEqual(split['noteCount'],5);self.assertEqual(split['notes'][0]['id'],'gf-000001')
        merged=edit_score(raw,{**PARAMS,'sourceFingerprint':split['scoreFingerprint'],'editedNotes':split['editedNotes'],'operation':{'kind':'merge','id':'gf-000001'}})['score']
        self.assertEqual(merged['events'],score['events'])
        inserted=edit_score(raw,{**body,'operation':{'kind':'insert','start':.8,'end':1,'midi':63}})['score']
        self.assertEqual(inserted['noteCount'],5)
        deleted=edit_score(raw,{**PARAMS,'sourceFingerprint':inserted['scoreFingerprint'],'editedNotes':inserted['editedNotes'],'operation':{'kind':'delete','id':inserted['notes'][1]['id']}})['score']
        self.assertEqual(deleted['events'],score['events'])

    def test_invalid_edits_cannot_destroy_original_or_downbeat(self):
        raw=source();score=score_for_request(raw,PARAMS)
        for operation in ({'kind':'update','id':'gf-000001','end':1.1},{'kind':'insert','start':0,'end':1,'midi':60},{'kind':'merge','id':'gf-000001'},{'kind':'update','id':'gf-000001','midi':60.5}):
            with self.assertRaises(ValueError):edit_score(raw,{**PARAMS,'sourceFingerprint':score['scoreFingerprint'],'operation':operation})
        with self.assertRaises(ValueError):edit_score(raw,{**PARAMS,'sourceFingerprint':'stale','operation':{'kind':'delete','id':'gf-000001'}})
        anchored=score_for_request(raw,{**PARAMS,'anchorNoteId':'gf-000001'})
        with self.assertRaisesRegex(ValueError,'downbeat'):edit_score(raw,{**PARAMS,'anchorNoteId':'gf-000001','sourceFingerprint':anchored['scoreFingerprint'],'operation':{'kind':'delete','id':'gf-000001'}})

    def test_project_restores_versions_chords_layered_events_and_playback_settings(self):
        payload=project();raw,root,_=normalize_project(payload)
        edited=edit_score(raw,{**PARAMS,'sourceFingerprint':root['scoreFingerprint'],'operation':{'kind':'update','id':'gf-000002','midi':60}})['score']
        h=generate_basic_harmony(edited)
        first=h['writtenChords'][0];tick=first['startTick']
        notes=[{**first,'id':'saved-bass','voice':2,'pitches':[first['pitches'][0]],'velocity':.6,'endTick':tick+32},{**first,'id':'saved-upper','voice':3,'pitches':[first['pitches'][-1]],'velocity':.5,'endTick':tick+8}]
        events,written,xml,_=render_texture(edited,h,notes)
        item={'sourceFingerprint':edited['scoreFingerprint'],'harmonyFingerprint':h['fingerprint'],'fingerprint':'b'*64,'settings':{'style':'lyrical','density':1,'variant':0,'voicing':'layered'},'events':events,'writtenChords':written,'xml':'<evil/>','model':{},'references':[],'generationSeconds':0}
        payload['versions'].append({'editedNotes':edited['editedNotes'],'kind':'edit','harmony':{'fingerprint':h['fingerprint'],'locks':h['locks'],'phraseStarts':h['phraseStarts'],'chordOffsetMs':0}})
        payload['textureSets']={f"1:{h['fingerprint']}":{'items':[item],'active':0}};payload['activeVersion']=1
        _,new_root,workspace=normalize_project(payload)
        self.assertEqual(root,new_root);self.assertEqual(workspace['versions'][1]['score']['events'],edited['events']);self.assertEqual(workspace['instruments'],['flute','cello']);self.assertEqual(workspace['voices'],[True,False]);self.assertEqual(workspace['position'],1.5)
        restored=next(iter(workspace['textureSets'].values()))['items'][0]
        self.assertEqual(restored['events'],events);self.assertEqual(restored['xml'],xml);self.assertEqual(workspace['loop'],payload['loop'])

    def test_invalid_project_and_audio_keep_active_job_and_other_tab(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(service,'RUNTIME',Path(temporary)),patch.dict(service.jobs,{},clear=True),patch.dict(service.client_sequences,{},clear=True):
            client=service.app.test_client();identifier='d'*32;directory=service.owned_dir(identifier);directory.mkdir();(directory/'keep').write_text('keep')
            service.jobs[identifier]={'id':identifier,'client':'this-tab','name':'keep.flac','analysisReady':True}
            bad=project();bad['source']['scoreFingerprint']='stale'
            self.assertEqual(client.post('/api/projects/open',json=bad).status_code,400)
            response=client.post('/api/jobs',data={'file':(io.BytesIO(b'broken'),'broken.mp3')},headers={'X-Client-Session':'this-tab'})
            self.assertEqual(response.status_code,400);self.assertIn(identifier,service.jobs);self.assertTrue((directory/'keep').is_file())
            response=client.post('/api/projects/open',json=project(),headers={'X-Client-Session':'other-tab'})
            self.assertEqual(response.status_code,200);self.assertIn(identifier,service.jobs)
            client.post('/api/reset',json={'client':'other-tab','sequence':1});self.assertIn(identifier,service.jobs)

    def test_link_source_rejects_wrong_bytes_then_links_exact_source_without_analysis(self):
        file=Path('tests/fixtures/ui-upload.flac').read_bytes();payload=project();payload['source']['sourceSha256']=hashlib.sha256(file).hexdigest()
        original={k:payload['source'][k] for k in ('notes','duration','sourceSha256','engineSignature')};payload['source']['scoreFingerprint']=score_for_request(original,PARAMS)['scoreFingerprint']
        with tempfile.TemporaryDirectory() as temporary,patch.object(service,'RUNTIME',Path(temporary)),patch.dict(service.jobs,{},clear=True),patch.dict(service.client_sequences,{},clear=True):
            client=service.app.test_client();opened=client.post('/api/projects/open',json=payload).json;identifier=opened['job']['id'];analysis=(service.owned_dir(identifier)/'analysis.json').read_bytes()
            self.assertEqual(client.post(f'/api/jobs/{identifier}/source',data={'file':(io.BytesIO(b'wrong'),'wrong.flac')}).status_code,400)
            self.assertEqual((service.owned_dir(identifier)/'analysis.json').read_bytes(),analysis)
            response=client.post(f'/api/jobs/{identifier}/source',data={'file':(io.BytesIO(file),'test.flac')})
            self.assertEqual(response.status_code,200);self.assertTrue(response.json['playbackReady']);self.assertEqual((service.owned_dir(identifier)/'analysis.json').read_bytes(),analysis)
            response=client.get(f'/api/jobs/{identifier}/audio');self.assertEqual(response.status_code,200);response.close()

    def test_real_worker_cancel_and_cancel_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(service,'RUNTIME',Path(temporary)),patch.dict(service.jobs,{},clear=True):
            identifier='d'*32;service.owned_dir(identifier).mkdir();service.jobs[identifier]={'client':'qa'}
            token='1'*32;child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);errors=[]
            def run():
                try:service.run_texture(identifier,{'requestId':token},{},{})
                except ValueError as error:errors.append(str(error))
            with patch.object(service,'start_texture_process',return_value=child):
                thread=threading.Thread(target=run);thread.start()
                deadline=time.monotonic()+3
                while token not in service.jobs[identifier].get('textureProcesses',{}) and time.monotonic()<deadline:time.sleep(.01)
                response=service.app.test_client().delete(f'/api/jobs/{identifier}/texture/{token}');self.assertEqual(response.status_code,204);thread.join(5)
            self.assertFalse(thread.is_alive());self.assertIsNotNone(child.poll());self.assertEqual(errors,['Arrangement cancelled.'])
            token='2'*32;service.app.test_client().delete(f'/api/jobs/{identifier}/texture/{token}')
            with self.assertRaisesRegex(ValueError,'cancelled'):service.run_texture(identifier,{'requestId':token},{},{})

    def test_layered_bass_survives_upper_attacks_and_each_xml_voice_balances(self):
        raw=source();score=score_for_request(raw,PARAMS);h=generate_basic_harmony(score)
        p=[{'tick':0,'pitches':[48,55],'length':8,'tones':[{'midi':48,'length':64},{'midi':55,'length':8}]},{'tick':16,'pitches':[55],'length':8,'tones':[{'midi':55,'length':8}]}]
        notes=layer_left_hand(score,h,p,1)
        # A single upper-note attack must not reattack/cut the sustained bass lane.
        bass=next(n for n in notes if n['startTick']==0 and n['voice']==2)
        self.assertEqual(bass['endTick'],64)
        events,written,xml,_=render_texture(score,h,notes);root=ET.fromstring(xml)
        self.assertTrue(any(e.get('voice')==3 for e in events))
        for measure,meta in zip(root.findall('./part/measure'),score['measures']):
            for voice in ('1','2','3'):
                self.assertEqual(sum(int(n.findtext('duration')) for n in measure.findall(f'note[voice="{voice}"]') if n.find('chord') is None),meta['endTick']-meta['startTick'])

    def test_repeated_phrase_reuses_motif_and_layered_voice_constraints(self):
        raw=source();raw['duration']=16;raw['notes']=[{'id':f'gf-{i+1:06d}','start':i*.5,'end':i*.5+.4,'midi':[60,62,64,67][i%4],'midiFloat':float([60,62,64,67][i%4])} for i in range(32)]
        score=score_for_request(raw,PARAMS);h=generate_basic_harmony(score,phrases=[1,5])
        bank={'melody':np.ones((12,16),np.float32),'stats':np.array([[1+i*.1,2,.4+i*.03] for i in range(12)],np.float32)}
        pieces=choose_donors(score,h,'lyrical',1,0,bank,True)
        self.assertEqual(len(pieces),2);self.assertEqual(pieces[1]['motifOf'],1);self.assertEqual(pieces[0]['donor'],pieces[1]['donor'])
        proposals=[{'tick':t,'pitches':[48,55,60],'length':64,'tones':[{'midi':48,'length':96},{'midi':55,'length':16},{'midi':60,'length':32}]} for t in range(0,1024,16)]
        notes=layer_left_hand(score,h,proposals,1)
        for tick in sorted({n['startTick'] for n in notes}):
            active=[n['pitches'][0] for n in notes if n['startTick']<=tick<n['endTick']]
            self.assertLessEqual(len(active),3);self.assertLessEqual(max(active)-min(active),12)
        for voice in (2,3,4):
            local=[n for n in notes if n['voice']==voice]
            self.assertTrue(all(a['endTick']<=b['startTick'] for a,b in zip(local,local[1:])))

if __name__=='__main__':unittest.main()
