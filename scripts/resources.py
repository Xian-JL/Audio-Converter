"""Download only absent local resources; user audio never passes through this script."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'models'
TOOLS = ROOT / 'tools'
PIANO = ROOT / 'public/piano'
PIANO_REVISION = 'efd8296360f9526e379bfbe5c1698ff54d6a1d34'
PIANO_FILES = ['A0'] + [f'{note}{octave}' for octave in range(1, 8) for note in ('C', 'Ds', 'Fs', 'A')] + ['C8']
SOURCES = {
    'mdx.onnx': 'https://huggingface.co/seanghay/uvr_models/resolve/main/UVR-MDX-NET-Inst_HQ_3.onnx',
    'mdx-metadata.json': 'https://raw.githubusercontent.com/Anjok07/ultimatevocalremovergui/master/models/MDX_Net_Models/model_data/model_data.json',
    'demucs-vocals.onnx': 'https://huggingface.co/StemSplitio/htdemucs-ft-vocals-onnx/resolve/2ef0d757d3e226d0da85fb8c71514f464fcabdd0/htdemucs_ft_vocals_fp16weights.onnx',
    'demucs-LICENSE.txt': 'https://raw.githubusercontent.com/facebookresearch/demucs/main/LICENSE',
    'demucs-onnx-LICENSE.txt': 'https://raw.githubusercontent.com/StemSplit/demucs-onnx/main/LICENSE',
}

def download(url, destination):
    if destination.is_file() and destination.stat().st_size > 0:
        print(f'Reuse {destination.name}', flush=True)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': 'LocalAudioConverter/4.0'})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open('wb') as output:
        shutil.copyfileobj(response, output, 1024 * 1024)
    partial.replace(destination)
    print(f'Downloaded {destination.name}: {destination.stat().st_size / 1048576:.1f} MiB', flush=True)

def usable_ffmpeg(path):
    try:
        result = subprocess.run([str(path), '-hide_banner', '-encoders'], capture_output=True, text=True, timeout=10)
        return result.returncode == 0 and 'libmp3lame' in result.stdout and 'flac' in result.stdout
    except (OSError, subprocess.SubprocessError):
        return False

def provision_ffmpeg():
    TOOLS.mkdir(exist_ok=True)
    local = TOOLS / 'ffmpeg.exe'
    candidates = [local, shutil.which('ffmpeg'), Path.home() / 'AppData/Local/ms-playwright/ffmpeg-1011/ffmpeg-win64.exe']
    for candidate in filter(None, candidates):
        if usable_ffmpeg(candidate):
            probes = [TOOLS / 'ffprobe.exe', shutil.which('ffprobe'), Path(candidate).with_name('ffprobe.exe')]
            probe = next((Path(p) for p in probes if p and Path(p).is_file()), None)
            if probe is None:
                continue
            try:
                if subprocess.run([str(probe), '-version'], capture_output=True, timeout=10).returncode:
                    continue
            except (OSError, subprocess.SubprocessError):
                continue
            if Path(candidate).resolve() != local.resolve():
                shutil.copy2(candidate, local)
            if probe.resolve() != (TOOLS / 'ffprobe.exe').resolve():
                shutil.copy2(probe, TOOLS / 'ffprobe.exe')
            print('Reuse compatible FFmpeg', flush=True)
            return
    archive = TOOLS / 'ffmpeg-essentials.zip'
    download('https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip', archive)
    with zipfile.ZipFile(archive) as zipped:
        for name in ('ffmpeg.exe', 'ffprobe.exe'):
            member = next(item for item in zipped.namelist() if item.endswith('/bin/' + name))
            with zipped.open(member) as source, (TOOLS / name).open('wb') as output:
                shutil.copyfileobj(source, output)
        for name in zipped.namelist():
            if name.endswith('/LICENSE') or name.endswith('/LICENSE.txt'):
                (TOOLS / 'FFmpeg-LICENSE.txt').write_bytes(zipped.read(name))
    archive.unlink()
    if not usable_ffmpeg(local):
        raise RuntimeError('FFmpeg build must include libmp3lame and FLAC support.')

def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(download, url, MODELS / name) for name, url in SOURCES.items()]
        jobs.append(pool.submit(provision_ffmpeg))
        for name in PIANO_FILES:
            jobs.append(pool.submit(download, f'https://raw.githubusercontent.com/Tonejs/audio/{PIANO_REVISION}/salamander/{name}.mp3', PIANO / f'{name}.mp3'))
        jobs.append(pool.submit(download, f'https://raw.githubusercontent.com/Tonejs/audio/{PIANO_REVISION}/salamander/README', PIANO / 'UPSTREAM-NOTICE.txt'))
        for job in jobs:
            job.result()
    manifest = {}
    for name, url in SOURCES.items():
        path = MODELS / name
        manifest[name] = {'source': url, 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    mdx = (MODELS / 'mdx.onnx').read_bytes()
    if hashlib.sha256(mdx).hexdigest() != '317554b07fe1ea5279a77f2b1520a41ea4b93432560c4ffd08792c30fddf9adc':
        raise RuntimeError('MDX model SHA-256 does not match the published model.')
    # GF no longer needs the legacy RMVPE model. Existing files are retained,
    # but fresh setups do not download the unused 345 MiB checkpoint.
    metadata_hash = hashlib.md5(mdx[-10000 * 1024:]).hexdigest()
    data = json.loads((MODELS / 'mdx-metadata.json').read_text())
    if metadata_hash not in data:
        raise RuntimeError(f'MDX model metadata missing for {metadata_hash}')
    (MODELS / 'mdx-config.json').write_text(json.dumps(data[metadata_hash], indent=2))
    if manifest['demucs-vocals.onnx']['sha256'] != '0cbe651f535415c9d26a7bb614f7d322dd5a080fa0298f2e50f478030a994dce':
        raise RuntimeError('Demucs vocal model SHA-256 does not match the tested export.')
    (MODELS / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    piano_manifest = {'revision': PIANO_REVISION, 'author': 'Alexander Holm', 'instrument': 'Yamaha C5 Salamander Grand Piano', 'license': 'CC BY 3.0', 'samples': {}}
    for name in PIANO_FILES:
        path = PIANO / f'{name}.mp3'
        piano_manifest['samples'][name] = {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (PIANO / 'manifest.json').write_text(json.dumps(piano_manifest, indent=2))
    (PIANO / 'LICENSE.txt').write_text('Salamander Grand Piano recordings by Alexander Holm, Yamaha C5.\nLicense: Creative Commons Attribution 3.0\nhttps://creativecommons.org/licenses/by/3.0/\nSource: Tonejs/audio salamander folder, revision ' + PIANO_REVISION + '\nThe local bank uses 30 compressed single-layer anchor samples; Tone.Sampler repitches intervening keys.\nSee UPSTREAM-NOTICE.txt for the original collection notice.\n', encoding='utf-8')
    print('All resources ready; checksums recorded in models/manifest.json', flush=True)

if __name__ == '__main__':
    main()
