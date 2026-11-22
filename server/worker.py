"""One cancellable local job. JSON lines carry progress to the web service."""
import os
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '4')
os.environ.setdefault('NUMBA_NUM_THREADS', '4')
import argparse
from pathlib import Path
import json
import sys
import time
import traceback
import hashlib
from .audio import probe, convert, decode

def emit(**data):
    print(json.dumps(data, ensure_ascii=True, allow_nan=False), flush=True)

def run(directory, excerpt_start=None, excerpt_duration=None, mode='enhanced', source_kind='vocal'):
    started = time.perf_counter()
    original = next(directory.glob('input.*'))
    emit(stage='validating', progress=0)
    info = probe(original)
    emit(info=info)
    if info['format'] == 'FLAC' and not (directory / 'audio.mp3').is_file():
        emit(stage='converting', progress=0)
        convert(original, directory / 'audio.mp3', info, lambda p: emit(stage='converting', progress=p))
    else:
        # Validate the entire MP3 during PCM decoding below; it remains available for playback.
        pass
    emit(playbackReady=True, conversionSeconds=round(time.perf_counter() - started, 2))
    try:
        emit(stage='decoding', progress=0)
        decode(original, directory / 'source.wav', excerpt_start, excerpt_duration, verified_pcm=info.get('verifiedPCM', False))
        import soundfile as sf
        if source_kind in ('piano','guzheng'):
            from .instrument_runtime import transcribe
            emit(stage='instrumentLoading',progress=0)
            result=transcribe(directory/'source.wav',source_kind,lambda p:emit(stage='instrumentTranscription',progress=p))
            result.update(sourceKind=source_kind,sourceSha256=hashlib.sha256(original.read_bytes()).hexdigest(),analysisSeconds=round(time.perf_counter()-started,2))
            (directory/'analysis.json').write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
            emit(stage='ready',progress=1,analysisReady=True,engine=result['engine'],summary={'noteCount':len(result['notes'])})
            return
        from .separation import separate
        from .game import GameTranscriber
        mixture, rate = sf.read(directory / 'source.wav', dtype='float32', always_2d=True)
        mixture = mixture.T
        emit(stage='separating', progress=0)
        vocals, backing = separate(mixture, lambda p: emit(stage='separating', progress=p), mode=mode)
        del backing
        sf.write(directory / 'vocals.wav', vocals.T, rate, subtype='FLOAT')
        sf.write(directory / f'vocals-{mode}.wav', vocals.T, rate, subtype='PCM_16')
        emit(stage='melody', progress=0)
        # Match the reviewed GF input representation; never run the old same-pitch cleanup.
        sf.write(directory/'vocals-game.flac',vocals.T,rate,subtype='PCM_24')
        game_wave,_=sf.read(directory/'vocals-game.flac',dtype='float32',always_2d=True)
        result=GameTranscriber().transcribe(game_wave,rate,lambda p:emit(stage='melody',progress=p))
        result.update(separationMode=mode,analysisSeconds=round(time.perf_counter()-started,2),excerptOffset=excerpt_start or 0,
                      sourceSha256=hashlib.sha256(original.read_bytes()).hexdigest(),rhythm=None,rhythmError=None)
        (directory / 'analysis.json').write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
        (directory / f'analysis-{mode}.json').write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
        emit(stage='ready', progress=1, analysisReady=True, engine='game',vocalReady=True,rhythmAvailable=False,analysisSeconds=result['analysisSeconds'], summary={'noteCount':len(result['notes'])}, noVocal=not result['notes'])
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        emit(stage='error', analysisError=str(error))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--start', type=float)
    parser.add_argument('--duration', type=float)
    parser.add_argument('--mode', choices=['enhanced', 'original'], default='enhanced')
    parser.add_argument('--source-kind',choices=['vocal','piano','guzheng'],default='vocal')
    options = parser.parse_args()
    try:
        run(options.directory.resolve(), options.start, options.duration, options.mode, options.source_kind)
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        emit(stage='error', error=str(error))
        sys.exit(1)

if __name__ == '__main__':
    main()
