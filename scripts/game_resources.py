"""Provision absent GAME resources only. Never reads user audio."""
from pathlib import Path
import hashlib
import json
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
SHA='00ba0c64115b6b874d9ea4afd3e6cf822abda2a04e52569233b0a044fd40e4e8'
URL='https://github.com/openvpi/GAME/releases/download/v1.0.3/GAME-1.0.3-small-onnx.zip'
NAMES=('config.json','encoder.onnx','segmenter.onnx','estimator.onnx','dur2bd.onnx','bd2dur.onnx')

def main():
    from server.game import model_directory
    try:
        print('Reuse GAME:',model_directory());return
    except RuntimeError:pass
    archive=ROOT/'models/GAME-1.0.3-small-onnx.zip'
    if not archive.is_file():
        archive.parent.mkdir(parents=True,exist_ok=True)
        request=urllib.request.Request(URL,headers={'User-Agent':'LocalAudioConverter/8.0'})
        with urllib.request.urlopen(request,timeout=120) as response,archive.with_suffix('.part').open('wb') as stream:
            while block:=response.read(1024*1024):stream.write(block)
        archive.with_suffix('.part').replace(archive)
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==SHA,'GAME checkpoint checksum mismatch.'
    destination=ROOT/'models/game-small';destination.mkdir(parents=True,exist_ok=True)
    assert destination.resolve().is_relative_to((ROOT/'models').resolve())
    with zipfile.ZipFile(archive) as source:
        assert source.testzip() is None
        for name in NAMES:
            target=destination/name
            target.with_suffix('.part').write_bytes(source.read('GAME-1.0.3-small-onnx/'+name))
            target.with_suffix('.part').replace(target)
    print('GAME ready:',model_directory())
    archive.unlink(missing_ok=True)

if __name__=='__main__':main()
