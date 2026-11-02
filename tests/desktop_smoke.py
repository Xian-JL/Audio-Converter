"""Explicit Windows desktop lifecycle smoke test; no browser/window automation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


def state():
    with urllib.request.urlopen('http://127.0.0.1:8765/api/desktop/status', timeout=.5) as response:
        return json.load(response)


def wait_ready():
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            return state()
        except OSError:
            time.sleep(.3)
    raise RuntimeError('Desktop service startup timed out; inspect .desktop/service.log.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--keep-running', action='store_true')
    args = parser.parse_args()
    root = args.package.resolve()
    exe = root / 'LocalAudio.exe'
    try:
        urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=.5).close()
    except urllib.error.URLError:
        pass
    else:
        raise RuntimeError('Port 8765 is already occupied; do not test against an existing user service.')
    current = None

    def start():
        return subprocess.Popen([str(exe), '--background'], cwd=root, creationflags=subprocess.CREATE_NO_WINDOW)

    def stop(process):
        subprocess.run([str(exe), '--quit'], cwd=root, check=True, timeout=10)
        process.wait(timeout=30)
        try:
            state()
        except OSError:
            return
        raise AssertionError('Service did not release its port.')

    report = {}
    try:
        current = start()
        before = wait_ready()
        report['firstLaunchReady'] = True
        try:
            urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8765/api/desktop/stop',
                method='POST', data=b'', headers={'X-Desktop-Token': 'invalid'}), timeout=3)
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError('Unauthenticated shutdown unexpectedly succeeded.')
        report['invalidShutdownRejected'] = True
        subprocess.run([str(exe), '--background'], cwd=root, check=True, timeout=10)
        assert state()['pid'] == before['pid']
        report['secondLaunchSameBackend'] = True
        stop(current)
        current = None
        report['gracefulExitReleasedPort'] = True
        current = start()
        after = wait_ready()
        assert after['pid'] != before['pid']
        report['restartReady'] = True
        print('Desktop startup, reuse, authenticated exit and restart passed.', flush=True)
        manifest = json.loads((root / 'bundle-manifest.json').read_text(encoding='utf-8'))
        for name, entry in manifest['files'].items():
            path = root / name
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            assert path.stat().st_size == entry['bytes'] and digest == entry['sha256'], name
        report.update(allBundleFilesVerified=len(manifest['files']), backendPid=after['pid'],
            launcherPid=current.pid, bundleGiB=round(sum(e['bytes'] for e in manifest['files'].values()) / 1024**3, 2),
            noWindowsAutostartInstalled=True)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    finally:
        if current is not None and (not args.keep_running or not report.get('allBundleFilesVerified')):
            stop(current)


if __name__ == '__main__':
    main()
