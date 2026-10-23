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
from server.basic_harmony import generate_basic_harmony

runtime=Path(sys.executable).resolve().parent
assert all(Path(m.__file__).resolve().is_relative_to(runtime) for m in (np,torch,onnxruntime,librosa,soundfile))
assert service.ROOT==runtime.parent
health=service.app.test_client().get('/api/health').json
assert health['ready'] and health['textureReady'] and health['appVersion']=='0.3.0',health
result=GameTranscriber().transcribe(np.zeros(44100,np.float32),44100)
assert result['duration']==1 and result['engine']=='game'
source={'engine':'game','sourceSha256':'a'*64,'engineSignature':{'test':'portable'},'duration':4,'notes':[{'id':f'gf-{i+1:06d}','start':i,'end':i+.8,'midi':60+i,'midiFloat':float(60+i)} for i in range(4)]}
score=generate_melody_score(source,120,'4/4','C major');harmony=generate_basic_harmony(score)
original_runtime=service.RUNTIME
with tempfile.TemporaryDirectory(prefix='portable-audio-smoke-') as temporary:
    service.RUNTIME=Path(temporary);identifier='a'*32;directory=service.owned_dir(identifier);directory.mkdir();(directory/'analysis.json').write_text(json.dumps(source),encoding='utf-8');service.jobs[identifier]={'analysisReady':True,'name':'synthetic.flac'}
    body={'bpm':120,'meter':'4/4','key':'C major','sourceFingerprint':score['scoreFingerprint'],'harmonyFingerprint':harmony['fingerprint'],'requestId':'b'*32}
    response=service.app.test_client().post('/api/jobs/'+identifier+'/texture',json=body)
    assert response.status_code==200,response.json
    assert response.json['events'] and response.json['settings']['voicing']=='layered'
    service.cancel(identifier)
service.RUNTIME=original_runtime
print(json.dumps({'version':health['appVersion'],'isolatedRuntime':True,'gameSilenceInference':True,'textureSubprocessInference':True,'notes':len(response.json['events'])}))
