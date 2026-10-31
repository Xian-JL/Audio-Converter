"""Fetch only the official vocabulary members through bounded HTTP byte ranges."""
from pathlib import Path
import io
import json
import hashlib
import pickle
import time
import zipfile
import requests
import argparse

ROOT=Path(__file__).resolve().parents[1]
URL='https://drive.usercontent.google.com/download?id=1NRisx-FpjcsXov1jmtrbAhtFBFBkGRgW&export=download&confirm=t'


class RangeReader(io.RawIOBase):
    def __init__(self,proxy=None):
        self.session=requests.Session()
        if proxy:self.session.proxies.update({'http':proxy,'https':proxy})
        self.position=0;self.fetched=0;self.size=None
        self.read_at(0,1)
    def read_at(self,start,length):
        if length>8*1024*1024:raise ValueError('Refusing a large dataset transfer.')
        for attempt in range(3):
            try:
                with self.session.get(URL,headers={'Range':f'bytes={start}-{start+length-1}','Accept-Encoding':'identity'},timeout=(10,40),stream=True) as response:
                    if response.status_code!=206:raise ValueError(f'Server did not support byte ranges ({response.status_code}).')
                    header=response.headers['Content-Range'];self.size=int(header.split('/')[-1])
                    if not header.startswith(f'bytes {start}-'):raise ValueError('Incorrect response range.')
                    data=response.raw.read(length+1)
                    if len(data)!=length:raise ValueError('Incorrect response length.')
                self.fetched+=len(data);return data
            except Exception:
                if attempt==2:raise
                time.sleep(attempt+1)
    def seek(self,offset,whence=0):
        self.position=offset if whence==0 else self.position+offset if whence==1 else self.size+offset
        return self.position
    def tell(self):return self.position
    def seekable(self):return True
    def read(self,size=-1):
        size=min(size if size>=0 else self.size-self.position,self.size-self.position)
        if size<=0:return b''
        data=self.read_at(self.position,size);self.position+=len(data);return data


class PlainUnpickler(pickle.Unpickler):
    def find_class(self,module,name):raise ValueError('Vocabulary must contain plain data only.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--proxy');args=parser.parse_args()
    destination=ROOT/'models/emo-disentanger';reader=RangeReader(args.proxy);reports=[]
    with zipfile.ZipFile(reader) as archive:
        all_names=archive.namelist()
        for stage,fragment in (('stage1','stage1/emopia_events/lead_sheet_chord11_functional/dictionary.pkl'),('stage2','stage2/emopia_events/full_song_chord11_functional/dictionary.pkl')):
            names=[n for n in all_names if n.endswith(fragment)]
            if len(names)!=1:raise ValueError(f'Expected one official {stage} vocabulary; found {names}')
            info=archive.getinfo(names[0])
            if info.file_size>1024*1024:raise ValueError('Unexpected vocabulary size.')
            data=archive.read(info)
            e2i,i2e=PlainUnpickler(io.BytesIO(data)).load()
            if not isinstance(e2i,dict) or not isinstance(i2e,dict) or any(not isinstance(k,str) or type(v)!=int or i2e.get(v)!=k for k,v in e2i.items()):raise ValueError('Invalid vocabulary mapping.')
            tokens=[i2e[i] for i in range(len(i2e))]
            target=destination/f'{stage}-vocabulary.json';encoded=json.dumps(tokens,ensure_ascii=False,indent=2)+'\n'
            if target.exists() and target.read_text(encoding='utf-8')!=encoded:raise ValueError('Existing vocabulary differs.')
            target.write_text(encoded,encoding='utf-8')
            reports.append({'stage':stage,'member':names[0],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'tokens':len(tokens),'jsonSha256':hashlib.sha256(encoded.encode()).hexdigest()})
            print(json.dumps(reports[-1]),flush=True)
    result={'source':URL,'archiveBytes':reader.size,'downloadedBytes':reader.fetched,'vocabularies':reports}
    (destination/'vocabulary-manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('Downloaded bytes:',reader.fetched,'of',reader.size,flush=True)


if __name__=='__main__':main()
