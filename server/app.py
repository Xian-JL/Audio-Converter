"""Same-origin, loopback-only UI/API with one isolated analysis subprocess."""
from pathlib import Path
import atexit
import hashlib
import tempfile
import json
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import uuid
from flask import Flask, request, jsonify, send_file
from werkzeug.serving import ThreadedWSGIServer
from werkzeug.exceptions import RequestEntityTooLarge
from .audio import MAX_BYTES, FFMPEG, FFPROBE

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
app = Flask(__name__, static_folder=str(ROOT / 'dist'), static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = MAX_BYTES + 512 * 1024
jobs = {}
client_sequences = {}
lock = threading.RLock()

def owned_dir(job_id):
    if not re.fullmatch(r'[a-f0-9]{32}', job_id):
        raise ValueError('Invalid task ID.')
    path = RUNTIME / job_id
    if path.resolve().parent != RUNTIME.resolve():
        raise ValueError('Invalid task directory.')
    return path

def cancel(job_id):
    with lock:
        job = jobs.pop(job_id, None)
    if not job:
        return
    for process in list(job.get('textureProcesses',{}).values()):
        terminate_process(process)
    process = job.get('process')
    terminate_process(process)
    path = owned_dir(job_id)
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass
    except OSError:
        threading.Thread(target=cleanup_directory, args=(path,), daemon=True).start()

def terminate_process(process):
    if process and process.poll() is None:
        if sys.platform == 'win32':
            try:subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=15)
            except subprocess.SubprocessError:process.kill()
        else:
            process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()

def public_job(job):
    return {k:v for k,v in job.items() if k not in ('process','textureProcesses','cancelledTextures')}

def start_texture_process(path):
    return subprocess.Popen([sys.executable,'-m','server.texture_worker',str(path)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)

def run_texture(job_id,body,melody,harmony):
    token=body.get('requestId',uuid.uuid4().hex)
    if not isinstance(token,str) or not re.fullmatch('[a-f0-9]{32}',token):raise ValueError('Invalid arrangement request.')
    with lock:
        job=jobs.get(job_id)
        if not job:raise ValueError('This task is no longer active.')
        if token in job.get('cancelledTextures',set()):raise ValueError('Arrangement cancelled.')
        workers=job.setdefault('textureProcesses',{})
        if workers:raise ValueError('An arrangement is already running. Cancel it before starting another.')
        path=owned_dir(job_id)/(token+'.texture')
        path.write_text(json.dumps({'score':melody,'harmony':harmony,'style':body.get('style','lyrical'),'density':body.get('density',1),'variant':body.get('variant',0),'voicing':body.get('voicing','layered')}),encoding='utf-8')
        process=start_texture_process(path)
        workers[token]=process
    try:
        process.wait()
        with lock:
            if jobs.get(job_id) is not job or workers.get(token) is not process:raise ValueError('Arrangement cancelled.')
        if process.returncode or not path.with_suffix('.result').is_file():raise ValueError('Arrangement stopped unexpectedly. Please retry.')
        value=json.loads(path.with_suffix('.result').read_text(encoding='utf-8'))
        if 'error' in value:raise ValueError(value['error'])
        return value['result']
    finally:
        with lock:workers.pop(token,None)
        path.unlink(missing_ok=True);path.with_suffix('.result').unlink(missing_ok=True)

@app.delete('/api/jobs/<job_id>/texture/<token>')
def cancel_texture(job_id,token):
    if not re.fullmatch('[a-f0-9]{32}',token):return jsonify(error='Invalid arrangement request.'),400
    with lock:
        job=jobs.get(job_id)
        if job:
            cancelled=job.setdefault('cancelledTextures',set())
            if len(cancelled)>256:cancelled.clear()
            cancelled.add(token)
        process=job.get('textureProcesses',{}).pop(token,None) if job else None
    terminate_process(process)
    return '',204

def cleanup_directory(path):
    if path.resolve().parent != RUNTIME.resolve() or not re.fullmatch(r'[a-f0-9]{32}', path.name):
        raise ValueError('Refusing to clean an unowned directory.')
    for _ in range(180):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(.5)
    app.logger.warning('Task cleanup deferred until next startup: %s', path.name)

def watch(job_id, process):
    for line in process.stdout:
        try:
            update = json.loads(line)
        except json.JSONDecodeError:
            continue
        with lock:
            if job_id in jobs:
                jobs[job_id].update(update)
    process.stdout.close()
    code = process.wait()
    with lock:
        job = jobs.get(job_id)
        if job and code and not job.get('error') and not job.get('analysisError'):
            job.update(stage='error', analysisError='Analysis stopped unexpectedly. Please retry or choose another file.')

def launch(job_id):
    directory = owned_dir(job_id)
    log = (directory / 'worker.log').open('a', encoding='utf-8')
    process = subprocess.Popen([sys.executable, '-u', '-m', 'server.worker', str(directory), '--mode', jobs[job_id].get('separationMode', 'enhanced')], cwd=ROOT, stdout=subprocess.PIPE, stderr=log, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
    log.close()
    jobs[job_id]['process'] = process
    threading.Thread(target=watch, args=(job_id, process), daemon=True).start()

@app.before_request
def local_only():
    host = urlsplit('http://' + request.host).hostname
    origin = request.headers.get('Origin')
    allowed = {'http://127.0.0.1:8765', 'http://localhost:8765', 'http://127.0.0.1:5173', 'http://localhost:5173'}
    if host not in ('127.0.0.1', 'localhost') or (origin and origin not in allowed):
        return jsonify(error='Only the local application may access this service.'), 403

@app.errorhandler(RequestEntityTooLarge)
def too_large(_):
    return jsonify(error='File exceeds the size limit (maximum 100 MB).'), 413

@app.get('/')
def index():
    return send_file(ROOT / 'dist/index.html')

@app.get('/api/health')
def health():
    piano_names = ['A0'] + [f'{note}{octave}' for octave in range(1,8) for note in ('C','Ds','Fs','A')] + ['C8']
    required = [('ffmpeg', FFMPEG), ('ffprobe', FFPROBE), ('separation model', ROOT / 'models/mdx.onnx'), ('separation configuration', ROOT / 'models/mdx-config.json'), ('enhanced vocal model', ROOT / 'models/demucs-vocals.onnx')]
    missing = [name for name, path in required if not path.is_file()]
    try:
        from .game import model_directory
        model_directory()
    except RuntimeError:missing.append('GAME model (run setup-game.ps1)')
    if any(not (ROOT / f'dist/piano/{note}.mp3').is_file() for note in piano_names):
        missing.append('piano samples')
    from .texture_model import available
    try:
        catalog=json.loads((ROOT/'dist/instruments/manifest.json').read_text(encoding='utf-8'))
        if any(not (ROOT/'dist/instruments'/instrument/name).is_file() for instrument,bank in catalog['instruments'].items() for name in bank['files']):missing.append('instrument samples')
    except (OSError,ValueError,KeyError):missing.append('instrument samples')
    return jsonify(ready=not missing, missing=missing,engine='game',scoreVersion=15,appVersion='0.3.1',textureReady=available())

@app.post('/api/jobs')
def upload():
    client = request.headers.get('X-Client-Session', '')
    try:
        sequence = int(request.headers.get('X-Upload-Sequence', '0'))
    except ValueError:
        return jsonify(error='Invalid upload sequence.'), 400
    files = list(request.files.values())
    if not files:
        return jsonify(error='Please select an MP3 or FLAC file.'), 400
    upload_file = files[0]
    mode = request.form.get('separationMode', 'enhanced')
    if mode not in ('enhanced', 'original'):
        return jsonify(error='Unknown vocal separation mode.'), 400
    name = re.split(r'[/\\]', upload_file.filename or '')[-1]
    name = ''.join(c for c in name if ord(c) >= 32)
    extension = Path(name).suffix.lower()
    if extension not in ('.mp3', '.flac'):
        return jsonify(error='Only MP3 and FLAC files are supported.'), 400
    job_id = uuid.uuid4().hex
    directory = owned_dir(job_id)
    directory.mkdir(parents=True)
    original = directory / ('input' + extension)
    upload_file.save(original)
    if original.stat().st_size == 0 or original.stat().st_size > MAX_BYTES:
        message = 'The selected file is empty. Please choose another file.' if original.stat().st_size == 0 else 'File exceeds the size limit (maximum 100 MB).'
        shutil.rmtree(directory)
        return jsonify(error=message), 400
    try:
        from .audio import probe
        probe(original)
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        shutil.rmtree(directory)
        return jsonify(error=str(error)),400
    with lock:
        if client and sequence < client_sequences.get(client, 0):
            shutil.rmtree(directory)
            return jsonify(error='This upload was replaced by a newer selection.'), 409
        if client:
            client_sequences[client] = sequence
        previous=[old_id for old_id,j in jobs.items() if j.get('client','')==client]
        jobs[job_id] = {'id': job_id, 'client': client, 'separationMode': mode, 'name': name, 'downloadName': name if extension == '.mp3' else name[:-len(extension)] + '.mp3', 'size': original.stat().st_size, 'stage': 'validating', 'progress': 0, 'playbackReady': extension == '.mp3', 'analysisReady': False, 'createdAt': time.time()}
        try:launch(job_id)
        except OSError as error:
            cancel(job_id)
            return jsonify(error=str(error)),500
        for old_id in previous:cancel(old_id)
    return jsonify(id=job_id), 202

@app.post('/api/reset')
def reset():
    payload = request.get_json(silent=True) or {}
    client = str(payload.get('client', ''))[:100]
    try:
        sequence = int(payload.get('sequence', 0))
    except (ValueError, TypeError):
        return jsonify(error='Invalid upload sequence.'), 400
    with lock:
        if sequence < client_sequences.get(client, 0):
            return '', 204
        client_sequences[client] = sequence
        for job_id in list(jobs):
            # Page-close beacons from an old tab must not cancel a newer tab's task.
            if jobs[job_id].get('client','') == client:
                cancel(job_id)
    return '', 204

@app.get('/api/jobs/<job_id>')
def status(job_id):
    with lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify(error='This task is no longer active.'), 404
        return jsonify(public_job(job))

@app.delete('/api/jobs/<job_id>')
def clear(job_id):
    cancel(job_id)
    return '', 204

@app.post('/api/jobs/<job_id>/retry')
def retry(job_id):
    with lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify(error='This task is no longer active.'), 404
        if job.get('restored'):return jsonify(error='Link the original audio and upload it again to rerun recognition.'),409
        if job.get('process') and job['process'].poll() is None:
            return jsonify(error='Analysis is still running.'), 409
        mode = (request.get_json(silent=True) or {}).get('separationMode', job.get('separationMode', 'enhanced'))
        if mode not in ('enhanced', 'original'):
            return jsonify(error='Unknown vocal separation mode.'), 400
        job['separationMode'] = mode
        cached = owned_dir(job_id) / f'analysis-{mode}.json'
        from .game import signature
        cache_result=json.loads(cached.read_text(encoding='utf-8')) if cached.is_file() else None
        try:current_signature=signature()
        except RuntimeError as error:return jsonify(error=str(error)),400
        if cache_result and cache_result.get('engine')=='game' and cache_result.get('engineSignature')==current_signature and (owned_dir(job_id) / f'vocals-{mode}.wav').is_file():
            shutil.copy2(cached, owned_dir(job_id) / 'analysis.json')
            result = json.loads(cached.read_text(encoding='utf-8'))
            job.update(stage='ready', progress=1, analysisReady=True, engine='game',rhythmAvailable=bool(result.get('rhythm')), analysisSeconds=result['analysisSeconds'])
            job.update(summary={'noteCount':len(result['notes'])}, noVocal=not result['notes'], fromCache=True)
            job.pop('analysisError', None); job.pop('error', None)
            return '', 202
        job.update(stage='validating', progress=0, analysisReady=False)
        job['fromCache'] = False
        job.pop('analysisError', None)
        job.pop('error', None)
        launch(job_id)
    return '', 202

@app.get('/api/jobs/<job_id>/vocals')
def vocals(job_id):
    with lock:
        job = jobs.get(job_id)
        if not job or not job.get('analysisReady'):
            return jsonify(error='Vocals are not ready yet.'), 404
        mode = job.get('separationMode', 'enhanced')
        preview = owned_dir(job_id) / f'vocals-{mode}.wav'
        if not preview.is_file():
            return jsonify(error='Vocal preview is unavailable. Please rerun the analysis.'), 404
        return send_file(preview, mimetype='audio/wav', conditional=True)

@app.get('/api/jobs/<job_id>/audio')
def audio(job_id):
    with lock:
        job = jobs.get(job_id)
        if not job or not job.get('playbackReady'):
            return jsonify(error='Audio is not ready yet.'), 404
        directory = owned_dir(job_id)
        path = directory / 'audio.mp3' if (directory / 'audio.mp3').is_file() else next(directory.glob('input.*'))
        return send_file(path, mimetype='audio/mpeg', conditional=True, as_attachment=request.args.get('download') == '1', download_name=job['downloadName'])

@app.get('/api/jobs/<job_id>/score')
def score(job_id):
    with lock:
        job = jobs.get(job_id)
        if not job or not job.get('analysisReady'):
            return jsonify(error='Score is not ready yet.'), 404
        directory = owned_dir(job_id)
        try:
            result = json.loads((directory / 'analysis.json').read_text(encoding='utf-8'))
            from .melody_score import generate_melody_score
            if result.get('engine')!='game':return jsonify(error='Please rerun analysis with GAME to create the melody-only score.'),409
            score=generate_melody_score(result,request.args.get('bpm'),request.args.get('meter'),request.args.get('key'),request.args.get('anchorNoteId'))
            score['sourceName']=job['name']
            return jsonify(score)
        except ValueError as error:
            return jsonify(error=str(error)), 400

@app.post('/api/jobs/<job_id>/harmony')
def harmony(job_id):
    if (request.content_length or 0)>4*1024*1024:
        return jsonify(error='Harmony settings are too large.'),413
    body=request.get_json(silent=True)
    if not isinstance(body,dict):return jsonify(error='Invalid harmony settings.'),400
    with lock:
        job=jobs.get(job_id)
        if not job or not job.get('analysisReady'):return jsonify(error='Score is not ready yet.'),404
        result=json.loads((owned_dir(job_id)/'analysis.json').read_text(encoding='utf-8'))
    if result.get('engine')!='game':return jsonify(error='Please rerun analysis with GAME.'),409
    try:
        from .editing import score_for_request
        from .basic_harmony import generate_basic_harmony
        melody=score_for_request(result,body)
        if body.get('sourceFingerprint')!=melody['scoreFingerprint']:
            return jsonify(error='The melody has changed. Reload the score before generating chords.'),409
        return jsonify(generate_basic_harmony(melody,body.get('locks'),body.get('phraseStarts'),body.get('chordOffsetMs',0)))
    except (ValueError,TypeError) as error:
        return jsonify(error=str(error)),400

@app.post('/api/jobs/<job_id>/texture')
def texture(job_id):
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or (request.content_length or 0)>4*1024*1024:return jsonify(error='Invalid accompaniment settings.'),400
    with lock:
        job=jobs.get(job_id)
        if not job or not job.get('analysisReady'):return jsonify(error='Score is not ready yet.'),404
        result=json.loads((owned_dir(job_id)/'analysis.json').read_text(encoding='utf-8'))
    if result.get('engine')!='game':return jsonify(error='Please rerun analysis with GAME.'),409
    try:
        from .editing import score_for_request
        from .basic_harmony import generate_basic_harmony
        melody=score_for_request(result,body)
        if body.get('sourceFingerprint')!=melody['scoreFingerprint']:return jsonify(error='The melody has changed. Reload the score.'),409
        harmony=generate_basic_harmony(melody,body.get('locks'),body.get('phraseStarts'),body.get('chordOffsetMs',0))
        if body.get('harmonyFingerprint')!=harmony['fingerprint']:return jsonify(error='The harmony has changed. Generate the accompaniment again.'),409
        return jsonify(run_texture(job_id,body,melody,harmony))
    except (ValueError,TypeError) as error:return jsonify(error=str(error)),400

@app.post('/api/jobs/<job_id>/rebar')
def rebar(job_id):
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or (request.content_length or 0)>4*1024*1024:return jsonify(error='Invalid downbeat settings.'),400
    with lock:
        job=jobs.get(job_id)
        if not job or not job.get('analysisReady'):return jsonify(error='Score is not ready yet.'),404
        result=json.loads((owned_dir(job_id)/'analysis.json').read_text(encoding='utf-8'));name=job['name']
    if result.get('engine')!='game':return jsonify(error='Please rerun analysis with GAME.'),409
    try:
        from .editing import score_for_request
        original=score_for_request(result,body,anchor=False)
        if body.get('sourceFingerprint')!=original['scoreFingerprint']:return jsonify(error='The melody has changed. Reload the score.'),409
        if not body.get('anchorNoteId'):raise ValueError('Please select a melody note onset as the downbeat.')
        rebuilt=score_for_request(result,body)
        rebuilt['sourceName']=name
        harmony=None
        if body.get('includeHarmony'):
            from .basic_harmony import generate_basic_harmony
            harmony=generate_basic_harmony(rebuilt)
        return jsonify(score=rebuilt,harmony=harmony)
    except (ValueError,TypeError) as error:return jsonify(error=str(error)),400

@app.post('/api/jobs/<job_id>/edit')
def edit(job_id):
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or (request.content_length or 0)>4*1024*1024:return jsonify(error='Invalid melody edit.'),400
    with lock:
        job=jobs.get(job_id)
        if not job or not job.get('analysisReady'):return jsonify(error='Score is not ready yet.'),404
        source=json.loads((owned_dir(job_id)/'analysis.json').read_text(encoding='utf-8'));name=job['name']
    try:
        from .editing import edit_score
        result=edit_score(source,body);result['score']['sourceName']=name
        return jsonify(result)
    except (ValueError,TypeError,KeyError) as error:return jsonify(error=str(error)),400

@app.post('/api/projects/open')
def open_project():
    from .project import normalize_project, PROJECT_LIMIT
    if (request.content_length or 0)>PROJECT_LIMIT:return jsonify(error='Project exceeds the size limit (32 MB).'),413
    try:
        original,root,workspace=normalize_project(request.get_json(silent=True))
        client=request.headers.get('X-Client-Session','');sequence=int(request.headers.get('X-Upload-Sequence','0'))
    except (ValueError,TypeError,KeyError,OverflowError) as error:return jsonify(error=str(error)),400
    identifier=uuid.uuid4().hex
    with lock:
        if sequence<client_sequences.get(client,0):return jsonify(error='This project was replaced by a newer selection.'),409
        directory=owned_dir(identifier);directory.mkdir(parents=True)
        (directory/'analysis.json').write_text(json.dumps(original,allow_nan=False),encoding='utf-8')
        job={'id':identifier,'client':client,'name':root['sourceName'],'size':0,'downloadName':Path(root['sourceName']).stem+'.mp3','stage':'ready','progress':1,'playbackReady':False,'analysisReady':True,'restored':True,'info':{'duration':root['duration'],'format':'PROJECT'}}
        for old in list(jobs):
            if jobs[old].get('client','')==client:cancel(old)
        client_sequences[client]=sequence;jobs[identifier]=job
    return jsonify(job=job,score=root,workspace=workspace)

@app.post('/api/jobs/<job_id>/source')
def link_source(job_id):
    """Associate the exact original bytes without rerunning or replacing GF."""
    with lock:
        job=jobs.get(job_id)
        if not job or not job.get('restored'):return jsonify(error='Open a saved project before linking its source.'),400
        source=json.loads((owned_dir(job_id)/'analysis.json').read_text(encoding='utf-8'))
    file=request.files.get('file')
    if file is None:return jsonify(error='Please select the original MP3 or FLAC file.'),400
    extension=Path(file.filename or '').suffix.lower()
    if extension not in ('.mp3','.flac'):return jsonify(error='Only MP3 and FLAC files are supported.'),400
    try:
        with tempfile.TemporaryDirectory(prefix='local-audio-source-') as temporary:
            original=Path(temporary)/('input'+extension);file.save(original)
            if not 0<original.stat().st_size<=MAX_BYTES:raise ValueError('File exceeds the size limit or is empty (maximum 100 MB).')
            with original.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            if digest!=source['sourceSha256']:raise ValueError('This is not the original audio used by this project. Please choose the exact original file.')
            from .audio import probe,convert
            info=probe(original);playable=original
            if extension=='.flac':
                playable=Path(temporary)/'audio.mp3';convert(original,playable,info)
            with lock:
                if jobs.get(job_id) is not job:return jsonify(error='This task is no longer active.'),409
                shutil.copy2(playable,owned_dir(job_id)/'audio.mp3')
                job.update(playbackReady=True,size=original.stat().st_size,info=info)
    except (ValueError,OSError,subprocess.SubprocessError) as error:return jsonify(error=str(error)),400
    return jsonify(public_job(job))

def shutdown():
    for job_id in list(jobs):
        cancel(job_id)

atexit.register(shutdown)

class LoopbackServer(ThreadedWSGIServer):
    allow_reuse_address = False

    def server_bind(self):
        if sys.platform == 'win32':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

def main():
    # Reserve the port before touching runtime data; a second launch must not erase an active task.
    try:
        existing = socket.create_connection(('127.0.0.1', 8765), timeout=1)
    except OSError:
        existing = None
    if existing is not None:
        existing.close()
        print('Port 8765 is already in use. Open the running app or stop it before starting another instance.', flush=True)
        return
    http_server = LoopbackServer('127.0.0.1', 8765, app)
    RUNTIME.mkdir(exist_ok=True)
    # Only this app's generated hex task folders are eligible for startup cleanup.
    for directory in RUNTIME.iterdir():
        if directory.is_dir() and re.fullmatch(r'[a-f0-9]{32}', directory.name):
            threading.Thread(target=cleanup_directory, args=(directory,), daemon=True).start()
    print('Local Audio running at http://127.0.0.1:8765', flush=True)
    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
        http_server.server_close()

if __name__ == '__main__':
    main()
