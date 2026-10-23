"""Independent local audio validation, conversion and decoding."""
from pathlib import Path
import json
import hashlib
import tempfile
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / 'tools/ffmpeg.exe'
FFPROBE = ROOT / 'tools/ffprobe.exe'
MAX_BYTES = 100 * 1024 * 1024

class AudioError(ValueError):
    pass

def probe(path):
    if not FFMPEG.is_file() or not FFPROBE.is_file():
        raise AudioError('Local audio tools are missing. Run setup.ps1 first.')
    run = subprocess.run([str(FFPROBE), '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_streams', '-show_format', '-of', 'json', str(path)], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    if run.returncode:
        raise AudioError('Unable to decode this audio file. Please confirm the file is not damaged.')
    data = json.loads(run.stdout)
    streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
    if not streams:
        raise AudioError('Unable to decode this audio file. Please confirm the file is not damaged.')
    stream = streams[0]
    codec = stream.get('codec_name')
    if codec not in ('mp3', 'flac'):
        raise AudioError('Only MP3 and FLAC files are supported.')
    duration = float(stream.get('duration') or data.get('format', {}).get('duration') or 0)
    if duration <= 0:
        raise AudioError('The selected audio file is empty or damaged.')
    info = {'duration': duration, 'sampleRate': int(stream['sample_rate']), 'channels': int(stream['channels']), 'format': codec.upper()}
    if codec == 'flac':
        bits = int(stream.get('bits_per_raw_sample') or 0)
        with Path(path).open('rb') as source:
            header = source.read(42)
        # STREAMINFO's lossless PCM checksum distinguishes harmless trailing junk from damaged audio.
        if header[:4] == b'fLaC' and (header[4] & 127) == 0 and bits in (16, 24) and any(header[26:42]):
            pcm_format = f's{bits}le'
            with tempfile.TemporaryFile() as error_log:
                process = subprocess.Popen([str(FFMPEG), '-v', 'error', '-protocol_whitelist', 'file,pipe', '-i', str(path), '-map', '0:a:0', '-f', pcm_format, '-c:a', 'pcm_' + pcm_format, 'pipe:1'], stdout=subprocess.PIPE, stderr=error_log)
                digest = hashlib.md5()
                with process.stdout as pipe:
                    while block := pipe.read(1024 * 1024):
                        digest.update(block)
                code = process.wait()
                error_log.seek(0)
                warnings = error_log.read(1024)
                if code or digest.digest() != header[26:42]:
                    raise AudioError('Unable to decode this audio file. Please confirm the file is not damaged.')
            info['verifiedPCM'] = True
            info['ignoredTrailingData'] = bool(warnings)
    return info

def convert(path, destination, info, progress=lambda value: None):
    rate = info['sampleRate'] if info['sampleRate'] in (32000, 44100, 48000) else 44100
    command = [str(FFMPEG), '-hide_banner', '-v', 'error']
    if not info.get('verifiedPCM'):
        command.append('-xerror')
    command += ['-y', '-protocol_whitelist', 'file,pipe', '-i', str(path), '-map', '0:a:0', '-vn', '-map_metadata', '-1', '-c:a', 'libmp3lame', '-b:a', '320k', '-ar', str(rate), '-ac', str(min(2, info['channels'])), '-progress', 'pipe:1', '-nostats', str(destination)]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace') as process:
        for line in process.stdout:
            match = re.match(r'out_time_us=(\d+)', line)
            if match:
                progress(min(0.99, int(match[1]) / (info['duration'] * 1_000_000)))
        error = process.stderr.read()
        if process.wait() != 0 or not destination.is_file() or destination.stat().st_size == 0:
            raise AudioError('Conversion failed. Please retry or choose another file. ' + error[-250:])
    progress(1)

def decode(path, destination, start=None, duration=None, verified_pcm=False):
    command = [str(FFMPEG), '-v', 'error', '-y']
    if not verified_pcm:
        command.append('-xerror')
    if start is not None:
        command += ['-ss', str(start)]
    command += ['-protocol_whitelist', 'file,pipe', '-i', str(path)]
    if duration is not None:
        command += ['-t', str(duration)]
    command += ['-map', '0:a:0', '-vn', '-ar', '44100', '-ac', '2', '-c:a', 'pcm_f32le', str(destination)]
    result = subprocess.run(command, capture_output=True, timeout=180)
    if result.returncode:
        raise AudioError('Unable to decode this audio file. Please confirm the file is not damaged.')
