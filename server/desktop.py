"""Hidden desktop service with installation identity and authenticated graceful exit."""
from pathlib import Path
import hashlib
import hmac
import os
import sys
import threading


def main():
    root = Path(__file__).resolve().parents[1]
    logs = root / '.desktop'
    logs.mkdir(exist_ok=True)
    log = (logs / 'service.log').open('a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = log
    from flask import jsonify, request
    from . import app as service

    token = os.environ.pop('LOCAL_AUDIO_DESKTOP_TOKEN', '')
    if len(token) < 32:
        raise RuntimeError('Start this service using LocalAudio.exe.')
    identity = hashlib.sha256(str(root).lower().encode('utf-8')).hexdigest()
    server = service.LoopbackServer('127.0.0.1', 8765, service.app)

    @service.app.get('/api/desktop/status')
    def desktop_status():
        return jsonify(installation=identity, pid=os.getpid(), version=service.APP_VERSION)

    @service.app.post('/api/desktop/stop')
    def desktop_stop():
        if not hmac.compare_digest(request.headers.get('X-Desktop-Token', ''), token):
            return jsonify(error='Invalid desktop session.'), 403
        threading.Thread(target=server.shutdown, daemon=True).start()
        return '', 204

    service.RUNTIME.mkdir(exist_ok=True)
    # Reuse the normal service's narrowly scoped startup cleanup.
    for directory in service.RUNTIME.iterdir():
        if directory.is_dir() and service.re.fullmatch(r'[a-f0-9]{32}', directory.name):
            threading.Thread(target=service.cleanup_directory, args=(directory,), daemon=True).start()
    try:
        print('Desktop service ready', service.APP_VERSION, os.getpid(), flush=True)
        server.serve_forever()
    finally:
        service.shutdown()
        server.server_close()
        log.flush()


if __name__ == '__main__':
    main()
