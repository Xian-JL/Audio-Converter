"""Owned UI/API QA server, saved GF notes only; never uses the user's .runtime."""
from pathlib import Path
import json
import shutil
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import app as service

root=Path(__file__).resolve().parents[1]
score=json.loads((root/'tests/fixtures/ember-score.json').read_text(encoding='utf-8'))
with tempfile.TemporaryDirectory(prefix='local-audio-harmony-qa-') as temporary:
    service.RUNTIME=Path(temporary)
    identifier='e'*32;directory=service.owned_dir(identifier);directory.mkdir()
    result={k:score[k] for k in ('duration','sourceSha256','engineSignature')}
    result['notes']=[{k:n[k] for k in ('id','start','end','midi','midiFloat')} for n in score['notes']];result['engine']='game'
    (directory/'analysis.json').write_text(json.dumps(result),encoding='utf-8')
    shutil.copy2(root/'tests/fixtures/ui-preview.mp3',directory/'audio.mp3')
    service.jobs[identifier]={'id':identifier,'name':score['sourceName'],'stage':'ready','progress':1,'analysisReady':True,'playbackReady':True,'downloadName':'the-ember.mp3','client':'qa-reference','info':{'duration':score['duration'],'sampleRate':44100,'channels':2,'format':'FLAC'}}
    full=json.loads((root/'tests/fixtures/ember-full-analysis.json').read_text(encoding='utf-8'));full_id='f'*32;full_dir=service.owned_dir(full_id);full_dir.mkdir()
    (full_dir/'analysis.json').write_text(json.dumps(full),encoding='utf-8')
    import subprocess
    subprocess.run([str(service.FFMPEG),'-v','error','-y','-i',str(root/'tests/fixtures/ui-preview.mp3'),'-af',f"apad=whole_dur={full['duration']}",'-t',str(full['duration']),'-c:a','libmp3lame','-b:a','32k',str(full_dir/'audio.mp3')],check=True)
    service.jobs[full_id]={'id':full_id,'name':'门尼 - 呜（The Ember）.flac','stage':'ready','progress':1,'analysisReady':True,'playbackReady':True,'downloadName':'the-ember.mp3','client':'qa-full','info':{'duration':full['duration'],'sampleRate':44100,'channels':2,'format':'FLAC'}}
    try:service.app.run(host='127.0.0.1',port=int(sys.argv[1]) if len(sys.argv)>1 else 8770,threaded=True,use_reloader=False)
    finally:service.shutdown()
