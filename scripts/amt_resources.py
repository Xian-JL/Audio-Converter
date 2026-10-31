"""Verify/download pinned official AMT Medium assets, never user audio."""
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'models/amt-medium'
REVISION='93b6eb7e09bad33be6cb2ebd50ce5279cbfde7f6'
WEIGHT_SHA='7af65dbabb2f6b7df9df03c2ea5b1909b74043591ba578fb663d80fcf82241ad'
WEIGHT_BYTES=1438866529


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def prepare():
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    expected=json.loads((ROOT/'models/amt-medium-manifest.json').read_text(encoding='utf-8'))['files'];files={}
    for name in ('config.json','pytorch_model.bin','README.md'):
        path=DIRECTORY/name
        url=f'https://huggingface.co/stanford-crfm/music-medium-800k/resolve/{REVISION}/{name}'
        if not path.is_file():
            part=path.with_suffix(path.suffix+'.part')
            with urllib.request.urlopen(url,timeout=60) as response,part.open('wb') as output:
                while block:=response.read(4*1024*1024):output.write(block)
            if name=='pytorch_model.bin' and (part.stat().st_size!=WEIGHT_BYTES or digest(part)!=WEIGHT_SHA):raise RuntimeError('AMT checkpoint checksum mismatch.')
            part.replace(path)
        sha=digest(path)
        if sha!=expected[name]['sha256'] or path.stat().st_size!=expected[name]['bytes']:raise RuntimeError('AMT resource is damaged: '+name+'. Move it aside and rerun SetupTexture.cmd.')
        files[name]={'bytes':path.stat().st_size,'sha256':sha,'url':url}
    manifest={'version':1,'repository':'https://huggingface.co/stanford-crfm/music-medium-800k','revision':REVISION,'license':'Apache-2.0','files':files}
    (DIRECTORY/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('AMT Medium resources verified; existing weights reused.',flush=True)
    return manifest


if __name__=='__main__':prepare()
