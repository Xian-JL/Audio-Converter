"""Run with the bundled interpreter: no development path may supply imports."""
import json
from pathlib import Path
import sys
import tempfile
import numpy as np
import torch
import onnxruntime
import librosa
import soundfile
from server import app as service
from server.game import GameTranscriber
from server.melody_score import generate_melody_score
from server.adaptive_harmony import generate as generate_basic_harmony

runtime=Path(sys.executable).resolve().parent
assert all(Path(m.__file__).resolve().is_relative_to(runtime) for m in (np,torch,onnxruntime,librosa,soundfile))
assert service.ROOT==runtime.parent
health=service.app.test_client().get('/api/health').json
assert health['ready'] and health['textureReady'] and health['appVersion']==service.APP_VERSION,health
result=GameTranscriber().transcribe(np.zeros(44100,np.float32),44100)
assert result['duration']==1 and result['engine']=='game'
source={'engine':'game','sourceSha256':'a'*64,'engineSignature':{'test':'portable'},'duration':12,'notes':[{'id':f'gf-{i+1:06d}','start':i+4,'end':i+4.8,'midi':60+i,'midiFloat':float(60+i)} for i in range(4)]}
score=generate_melody_score(source,120,'4/4','C major');harmony=generate_basic_harmony(score)
original_runtime=service.RUNTIME
with tempfile.TemporaryDirectory(prefix='portable-audio-smoke-') as temporary:
    service.RUNTIME=Path(temporary);identifier='a'*32;directory=service.owned_dir(identifier);directory.mkdir();(directory/'analysis.json').write_text(json.dumps(source),encoding='utf-8');service.jobs[identifier]={'analysisReady':True,'name':'synthetic.flac'}
    body={'bpm':120,'meter':'4/4','key':'C major','sourceFingerprint':score['scoreFingerprint'],'harmonyFingerprint':harmony['fingerprint'],'requestId':'b'*32,'harmonyPolicy':'adaptive-block-v1','emotion':{'engine':'emo','feeling':'sad','contour':'rising'}}
    response=service.app.test_client().post('/api/jobs/'+identifier+'/texture',json=body)
    assert response.status_code==200,response.json
    assert response.json['events'] and response.json['settings']['mode']=='hybrid-v2'
    service.cancel(identifier)
    def layer(instrument,count=1):return {'instrument':instrument,'timbre':'warm','count':count,'gain':100,'pan':0,'enabled':True}
    ensembles=[[layer('violin',4)],[layer('piano'),layer('cello')]]
    project={'kind':'audio-converter-project','schemaVersion':2,'source':{**source,'name':'synthetic.flac','bpm':120,'meter':'4/4','key':'C major','scoreFingerprint':score['scoreFingerprint'],'identityNotesJson':score['identityNotesJson']},'versions':[{}],'activeVersion':0,'ensembles':ensembles,'scoreLayout':'compact'}
    imported=service.app.test_client().post('/api/projects/open',json=project)
    assert imported.status_code==200,imported.json
    assert imported.json['workspace']['ensembles']==ensembles
    service.cancel(imported.json['job']['id'])
service.RUNTIME=original_runtime
print(json.dumps({'version':health['appVersion'],'isolatedRuntime':True,'gameSilenceInference':True,'textureSubprocessInference':True,'projectSchemaTwoEnsembles':True,'notes':len(response.json['events'])}))
