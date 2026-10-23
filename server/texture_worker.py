"""Disposable CPU arrangement worker: cancellation terminates real inference."""
import json
from pathlib import Path
import sys
from .accompaniment import generate_accompaniment

if __name__=='__main__':
    path=Path(sys.argv[1]);body=json.loads(path.read_text(encoding='utf-8'))
    try:
        result=generate_accompaniment(body['score'],body['harmony'],body['style'],body['density'],body['variant'],body['voicing'])
        value={'result':result}
    except Exception as error:
        value={'error':str(error)}
    path.with_suffix('.result').write_text(json.dumps(value,allow_nan=False),encoding='utf-8')
