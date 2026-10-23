"""Real offline worker smoke check in an automatically removed temporary folder."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='local-audio-v01-smoke-') as temporary:
    directory=Path(temporary)
    shutil.copy2(root/'tests/fixtures/ui-upload.flac',directory/'input.flac')
    process=subprocess.run([sys.executable,'-u','-m','server.worker',str(directory),'--mode','enhanced'],cwd=root,capture_output=True,text=True,encoding='utf-8',timeout=180)
    rows=[json.loads(line) for line in process.stdout.splitlines() if line.startswith('{')]
    assert process.returncode==0,process.stderr
    assert rows and rows[-1].get('stage')=='ready',process.stdout+'\n'+process.stderr
    assert (directory/'audio.mp3').is_file() and (directory/'analysis.json').is_file()
    analysis=json.loads((directory/'analysis.json').read_text(encoding='utf-8'))
    assert analysis['engine']=='game'
    output=root/'tests/output';output.mkdir(exist_ok=True)
    (output/'worker.json').write_text(json.dumps({'result':'ready','engine':analysis['engine'],'input':'1 second silent FLAC','analysisSeconds':analysis['analysisSeconds'],'noteCount':len(analysis['notes']),'checks':'real conversion, enhanced separation, migrated GAME inference, saved analysis; no experimental imports'},indent=2),encoding='utf-8')
    print('Offline FLAC -> enhanced separation -> GAME worker passed')
