"""Verify downloaded archives and prepare selected inference weights without loading pickle."""
from pathlib import Path
import hashlib
import gzip
import json
import shutil
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def install_stream(stream, target, expected):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.preparing')
    if temporary.exists():
        raise ValueError(f'Preparation file already exists; inspect before retrying: {temporary}')
    with temporary.open('xb') as output:
        shutil.copyfileobj(stream, output, 4 * 1024 * 1024)
    if temporary.stat().st_size != expected:
        raise ValueError(f'Extracted file size differs: {temporary}')
    sha = digest(temporary)
    if target.exists():
        if target.stat().st_size != expected or digest(target) != sha:
            raise ValueError(f'Existing file differs; both copies are preserved: {target}')
        temporary.unlink()
    else:
        temporary.rename(target)
    print(f'Prepared: {target.relative_to(ROOT)} ({expected} bytes)', flush=True)
    return {'path': str(target.relative_to(ROOT)).replace('\\', '/'), 'bytes': expected, 'sha256': sha}


def prepare():
    midi_root = ROOT / 'models/midi-emotion'
    emo_root = ROOT / 'models/emo-disentanger'
    midi_archive = midi_root / 'continuous_concat.tar.gz'
    emo_archive = emo_root / 'best_weight.zip'
    for path, size in ((midi_archive, 538669483), (emo_archive, 2236506726)):
        if not path.is_file() or path.stat().st_size != size:
            raise ValueError(f'Archive is missing or has an unexpected size: {path}')
    midi_files = []
    required = {'continuous_concat/model.pt', 'continuous_concat/model_config.pt', 'continuous_concat/mappings.pt'}
    with gzip.open(midi_archive, 'rb') as raw, tarfile.open(fileobj=raw, mode='r|') as archive:
        seen = set()
        for member in archive:
            name = member.name.removeprefix('./')
            if name not in required:
                continue
            if not member.isfile() or name in seen:
                raise ValueError(f'Unexpected archive member: {name}')
            seen.add(name)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f'Cannot read archive member: {name}')
            with stream:
                midi_files.append(install_stream(stream, midi_root / name, member.size))
        # Consume the gzip footer too, to verify the gzip checksum.
        while raw.read(4 * 1024 * 1024):
            pass
        if seen != required:
            raise ValueError('Required midi-emotion files are missing.')
    emo_files = []
    selected = (
        'best_weight/Functional-two/emopia_lead_sheet_finetune/ep016_loss0.685_params.pt',
        'best_weight/Functional-two/emopia_acccompaniment_finetune_gpt2/ep300_loss0.120_params.pt',
    )
    with zipfile.ZipFile(emo_archive) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            with archive.open(entry) as stream:
                while stream.read(4 * 1024 * 1024):
                    pass
        print('EMO archive: all member CRC checks passed.', flush=True)
        for name in selected:
            entry = archive.getinfo(name)
            with archive.open(entry) as stream:
                emo_files.append(install_stream(stream, emo_root / name, entry.file_size))
    for directory, path, files in ((midi_root, midi_archive, midi_files), (emo_root, emo_archive, emo_files)):
        receipt = {'version': 1, 'archive': path.name, 'archiveBytes': path.stat().st_size,
                   'archiveSha256': digest(path), 'files': files,
                   'note': 'Local integrity receipt; SHA-256 is not an independently published upstream checksum. Inference has not been activated.'}
        (directory / 'resource-manifest.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'midiEmotionSelectedBytes': sum(f['bytes'] for f in midi_files),
                      'emoSelectedBytes': sum(f['bytes'] for f in emo_files),
                      'archivesPreserved': True, 'applicationModelChanged': False}), flush=True)


if __name__ == '__main__':
    prepare()
