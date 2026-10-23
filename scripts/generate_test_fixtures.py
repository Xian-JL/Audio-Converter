"""Create synthetic public regression data; never overwrite private listening data."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server.melody_score import generate_melody_score

def analysis(count,duration,first=0.1):
    step=(duration-first-.5)/count;notes=[]
    for i in range(count):
        start=round(first+i*step,3);midi=60+(0,2,4,7,9)[(i*7+i//5)%5]
        notes.append({'id':f'gf-{i+1:06d}','start':start,'end':round(start+step*(.65,.85,.95)[i%3],3),'midi':midi,'midiFloat':float(midi)})
    manifest=json.loads((ROOT/'models/game-manifest.json').read_text(encoding='utf-8'))
    return {'duration':duration,'engine':'game','notes':notes,'engineSignature':manifest['signature'],'sourceSha256':hashlib.sha256(f'synthetic:{count}:{duration}:{first}'.encode()).hexdigest(),'fixtureKind':'synthetic; not a song transcription'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'tests/fixtures');args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    excerpt=analysis(122,71);score=generate_melody_score(excerpt,68,'4/4','C major');score['sourceName']='Synthetic excerpt.flac';score['fixtureKind']='synthetic'
    values={'ember-score.json':score,'ember-full-analysis.json':analysis(430,287,15.37)}
    for case,count,duration in [('unsaid',169,90),('the-ember',118,71)]:
        raw=analysis(count,duration);values[case+'-gf.json']={'duration':duration,'vocalFileSha256':raw['sourceSha256'],'events':[{'start':n['start'],'end':n['end'],'pitches':[n['midi']],'staff':1} for n in raw['notes']],'fixtureKind':'synthetic'}
    for name,value in values.items():
        path=args.output/name
        if path.exists():print('Keep existing fixture:',name)
        else:path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');print('Created synthetic fixture:',name)

if __name__=='__main__':main()
