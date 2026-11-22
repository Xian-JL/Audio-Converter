"""Prepare pinned inference-only instrument resources, without TensorFlow or training data."""
from pathlib import Path
import hashlib
import json
import subprocess
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PACKAGES={'transkun':'2.0.1','basic-pitch':'0.4.0'}
WHEEL_HASHES={'transkun':'7d7f5bf88b0d21f7da0415b089cff3bcbcbdda04e1a3c9719964947942c859fe','basic-pitch':'738adb503aae7fdfc7d1e1511aa0ce35052315f260a19531ef4c356708425db0'}


def prepare():
    directory=ROOT/'models/instrument-transcription';directory.mkdir(exist_ok=True)
    if (ROOT/'models/instrument-models-manifest.json').is_file():
        import sys
        sys.path.insert(0,str(ROOT))
        from server.instrument_runtime import available,verify
        if all(available(k) for k in ('piano','guzheng')):
            verify('transkun');verify('basic-pitch');print('Reusing verified instrument resources.');return
    manifest={}
    for name,version in PACKAGES.items():
        # The published artifact digest is recorded with the extracted resource manifest.
        with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as response:metadata=json.load(response)
        entry=next(x for x in metadata['urls'] if x['filename'].endswith('.whl'));wheel=directory/entry['filename']
        if entry['digests']['sha256']!=WHEEL_HASHES[name]:raise ValueError('Published artifact differs from the pinned wheel: '+name)
        if not wheel.is_file() or wheel.stat().st_size!=entry['size']:
            subprocess.run(['curl.exe','-fL','-C','-','--connect-timeout','30','--retry','3','-o',str(wheel),entry['url']],check=True)
        if hashlib.sha256(wheel.read_bytes()).hexdigest()!=entry['digests']['sha256']:raise ValueError('Downloaded wheel checksum mismatch: '+name)
        base=ROOT/'vendor'/name;files={}
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.namelist():
                path=Path(member)
                target=None
                if name=='transkun':
                    if member.endswith('.py') and member.startswith('transkun/'):target=base/path
                    elif member.endswith('/2.0.pt'):target=directory/'transkun-2.0.pt'
                    elif member.endswith('/2.0.conf'):target=directory/'transkun-2.0.conf'
                else:
                    if member in ('basic_pitch/constants.py','basic_pitch/note_creation.py'):target=base/path
                    elif member.endswith('/nmp.onnx'):target=directory/'basic-pitch.onnx'
                if '.dist-info/' in member and path.name.upper().startswith(('LICENSE','NOTICE','COPYING')):target=base/path.name
                if target is None:continue
                if not target.resolve().is_relative_to(ROOT):raise ValueError('Unsafe archive member.')
                raw=archive.read(member)
                if target.exists():
                    if target.read_bytes()!=raw:raise ValueError('Existing resource differs: '+str(target))
                else:
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                files[target.relative_to(ROOT).as_posix()]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        provenance={'package':name,'version':version,'wheelUrl':entry['url'],'wheelSha256':entry['digests']['sha256'],'files':files}
        (base/'SOURCE.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8');manifest[name]=provenance
    (ROOT/'models/instrument-models-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Piano and guzheng inference resources prepared and verified.',flush=True)


if __name__=='__main__':prepare()
