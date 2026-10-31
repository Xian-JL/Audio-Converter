"""Disposable CPU arrangement worker: cancellation terminates real inference."""
import json
from pathlib import Path
import sys
from .hybrid import generate


def write_progress(path,value):
    if value.get('stage') in ('generating','retrying','composing','performing'):value={**value,'progress':.03+.93*value['progress']}
    part=path.with_suffix('.progress.tmp')
    try:
        part.write_text(json.dumps(value,allow_nan=False),encoding='utf-8');part.replace(path.with_suffix('.progress'))
    except OSError:
        # Windows may briefly lock the old progress file while the UI reads it.
        # Missing one status update must never abort model inference.
        pass


if __name__=='__main__':
    path=Path(sys.argv[1]);body=json.loads(path.read_text(encoding='utf-8'))
    def progress(value):
        write_progress(path,value)
    try:
        result=generate(body['score'],body['harmony'],body['seed'],progress,body.get('sections'),body.get('emotion'))
        value={'result':result}
    except Exception as error:
        value={'error':str(error)}
    path.with_suffix('.result').write_text(json.dumps(value,allow_nan=False),encoding='utf-8')
