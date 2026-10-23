"""Build a relocatable offline Windows bundle from verified local resources.

No user media, development environment, credentials or runtime jobs are copied.
The Python dependency closure is collected from installed distribution RECORDs.
"""
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys
import zipfile
from packaging.requirements import Requirement

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.3.0'

def runtime_file(path):
    """Retain licenses even when they live under an upstream include directory."""
    if '__pycache__' in path.parts or path.suffix=='.pyc' or path.name=='direct_url.json':return False
    if 'licenses' in path.parts or path.name.lower().startswith(('license','copying','notice')):return True
    return not any(part in ('tests','test','include','benchmarks') for part in path.parts) and path.suffix not in ('.h','.hpp','.c','.cpp','.cu','.pyi')

def archive_bundle(destination,archive):
    """Package only current runtime files; leave staging/development files intact."""
    destination=destination.resolve();archive=archive.resolve()
    if archive.exists():raise FileExistsError('Choose a new archive name.')
    old=json.loads((destination/'bundle-manifest.json').read_text(encoding='utf-8'));files=[]
    source_dist={p.relative_to(ROOT).as_posix() for p in (ROOT/'dist').rglob('*') if p.is_file()}
    for path in sorted(destination.rglob('*')):
        if not path.is_file():continue
        relative=path.relative_to(destination)
        if relative.as_posix()=='bundle-manifest.json' or '__pycache__' in relative.parts or '.runtime' in relative.parts:continue
        if relative.parts[0]=='runtime' and not runtime_file(relative):continue
        if relative.parts[0]=='dist' and relative.as_posix() not in source_dist:continue
        files.append((relative.as_posix(),path))
    manifest={**old,'files':{}}
    archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as output:
        for name,path in files:
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            manifest['files'][name]={'bytes':path.stat().st_size,'sha256':digest};output.write(path,destination.name+'/'+name)
        output.writestr(destination.name+'/bundle-manifest.json',json.dumps(manifest,indent=2))
    print(json.dumps({'archive':str(archive),'files':len(files),'MiB':round(archive.stat().st_size/1048576,2),'unpackedMiB':round(sum(f['bytes'] for f in manifest['files'].values())/1048576,2)}),flush=True)

def distributions():
    pending=[]
    for name in ('requirements.txt','requirements-texture.txt'):
        pending.extend(Requirement(line.strip()).name for line in (ROOT/name).read_text().splitlines() if line.strip() and not line.startswith('#'))
    selected={}
    while pending:
        name=pending.pop();dist=metadata.distribution(name);canonical=dist.metadata['Name'].lower().replace('_','-')
        if canonical in selected:continue
        selected[canonical]=dist
        for requirement in dist.requires or []:
            value=Requirement(requirement)
            if value.marker is None or value.marker.evaluate({'extra':''}):pending.append(value.name)
    return selected

def build(destination):
    if sys.platform!='win32':raise RuntimeError('Build the Windows bundle on Windows.')
    destination=destination.resolve()
    if destination.exists():raise FileExistsError('Choose a new output directory; existing files are never overwritten.')
    if not (ROOT/'dist/index.html').is_file():raise RuntimeError('Build the frontend first.')
    from server.game import model_directory
    from server.texture_model import runtime
    from server.audio import FFMPEG,FFPROBE
    model_directory();runtime()
    if not FFMPEG.is_file() or not FFPROBE.is_file():raise RuntimeError('Run Setup.cmd first.')
    installed=distributions();destination.mkdir(parents=True)
    for directory in ('dist','server','vendor','models','tools'):
        shutil.copytree(ROOT/directory,destination/directory,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.part','*.zip','*.log'))
    for name in ('README.md','README.zh-CN.md','THIRD_PARTY.md','SPEC.md','RELEASE.md','requirements.txt','requirements-texture.txt'):
        shutil.copy2(ROOT/name,destination/name)
    base=Path(sys.base_prefix);runtime_dir=destination/'runtime';runtime_dir.mkdir()
    for pattern in ('python*.exe','*.dll','LICENSE*'):
        for file in base.glob(pattern):shutil.copy2(file,runtime_dir/file.name)
    shutil.copytree(base/'DLLs',runtime_dir/'DLLs',ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pdb','tcl*','tk*','_tkinter*'))
    shutil.copytree(base/'Lib',runtime_dir/'Lib',ignore=shutil.ignore_patterns('site-packages','__pycache__','*.pyc','test','tests','tkinter','idlelib','turtledemo','ensurepip'))
    target_site=runtime_dir/'Lib/site-packages';target_site.mkdir()
    for name,dist in installed.items():
        site=Path(dist.locate_file('')).resolve()
        if dist.files is None:raise RuntimeError(f'{name} has no installed file manifest.')
        for record in dist.files:
            source=Path(dist.locate_file(record)).resolve()
            if not source.is_relative_to(site) or not source.is_file() or not runtime_file(source.relative_to(site)):continue
            target=target_site/source.relative_to(site);target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copy2(source,target)
    # Explicit relative search path prevents accidental dependence on the source PC.
    (runtime_dir/f'python{sys.version_info.major}{sys.version_info.minor}._pth').write_text('Lib\nDLLs\nLib/site-packages\n..\nimport site\n',encoding='utf-8')
    (destination/'Start.cmd').write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\n"runtime\\python.exe" -m server.app\r\nif errorlevel 1 pause\r\n')
    (destination/'PORTABLE.txt').write_text('Local Audio v'+VERSION+'\nExtract the entire folder, then run Start.cmd.\nNo Python, Node.js, account or network connection is required.\nOpen http://127.0.0.1:8765 . Keep this window running.\nUser songs and saved projects are not included.\nLicenses: THIRD_PARTY.md and runtime/LICENSE*.\n',encoding='utf-8')
    manifest={'version':VERSION,'python':sys.version,'distributions':{name:dist.version for name,dist in sorted(installed.items())},'files':{}}
    for path in sorted(destination.rglob('*')):
        if path.is_file():
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            manifest['files'][path.relative_to(destination).as_posix()]={'bytes':path.stat().st_size,'sha256':digest}
    (destination/'bundle-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'directory':str(destination),'files':len(manifest['files']),'MiB':round(sum(f['bytes'] for f in manifest['files'].values())/1048576,2),'packages':len(installed)}),flush=True)

if __name__=='__main__':
    sys.path.insert(0,str(ROOT))
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--zip',type=Path);args=parser.parse_args();build(args.output)
    if args.zip:archive_bundle(args.output,args.zip)
