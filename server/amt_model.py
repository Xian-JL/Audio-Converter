"""AMT Medium CPU generation with upstream tokens and cache-equivalent sampling.

Melody is an immutable control track, piano is the only generated instrument.
Musical pitches/durations are never folded, thinned or snapped after decoding.
"""
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'models/amt-medium'
MODEL_VERSION='amt-medium-v1'
MELODY_PROGRAM=53
PREFIX=5.
MAX_CHUNK_SECONDS=28.


def available():
    return (ROOT/'models/amt-medium-manifest.json').is_file() and all((DIRECTORY/name).is_file() for name in ('config.json','pytorch_model.bin')) and importlib.util.find_spec('torch') is not None and importlib.util.find_spec('transformers') is not None


@lru_cache(maxsize=1)
def runtime():
    if not available():raise ValueError('AMT resources are missing. Run SetupTexture.cmd and restart.')
    os.environ['USE_TF']='0';os.environ['USE_FLAX']='0';os.environ['HF_HUB_OFFLINE']='1'
    from transformers import GPT2Config,GPT2LMHeadModel
    import torch
    manifest=json.loads((ROOT/'models/amt-medium-manifest.json').read_text(encoding='utf-8'))
    for name in ('config.json','pytorch_model.bin'):
        with (DIRECTORY/name).open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
        if sha!=manifest['files'][name]['sha256']:raise ValueError('AMT resources are damaged. Run SetupTexture.cmd again.')
    source=ROOT/'vendor/anticipation';provenance=json.loads((source/'SOURCE.json').read_text(encoding='utf-8'))
    for name,expected in provenance['files'].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=expected:raise ValueError('AMT sampling resources are damaged.')
    if str(source) not in sys.path:sys.path.insert(0,str(source))
    from anticipation import ops,sample,vocab
    torch.set_num_threads(4)
    config=GPT2Config.from_pretrained(DIRECTORY,local_files_only=True);config.architectures=['GPT2LMHeadModel']
    model=GPT2LMHeadModel.from_pretrained(DIRECTORY,config=config,local_files_only=True,attn_implementation='sdpa').eval()
    for p in model.parameters():p.requires_grad_(False)
    return model,ops,sample,vocab,manifest,provenance


class CachedLogits:
    """Reuse a KV prefix only when tokens and rebased positions match exactly."""
    def __init__(self,model):self.model=model;self.tokens=[];self.cache=None;self.last=None;self.stream=None;self.window_start=0

    def __call__(self,tokens,cached=True):
        import torch
        append=cached and self.cache is not None and len(tokens)>=len(self.tokens) and tokens[:len(self.tokens)]==self.tokens
        if append and len(tokens)==len(self.tokens):return self.last.clone()
        delta=tokens[len(self.tokens):] if append else tokens
        with torch.inference_mode():
            result=self.model(torch.tensor([delta],dtype=torch.long),past_key_values=self.cache if append else None,use_cache=cached,logits_to_keep=1)
        self.tokens=tokens.copy();self.cache=result.past_key_values if cached else None;self.last=result.logits[0,-1].float().clone()
        return self.last.clone()


def cached_add_token(logits,sample,ops,vocab,generator,tokens,top_p,current_time):
    import torch
    if logits.stream is not tokens:logits.stream=tokens;logits.window_start=0
    # Roll in blocks, retaining >=169 events, so a long CPU sequence does not
    # invalidate and re-prefill a 1024-token cache on every single note.
    if len(tokens)-logits.window_start>1017:logits.window_start=max(0,len(tokens)-507)
    history=tokens[logits.window_start:].copy();offset=ops.min_time(history,seconds=False)
    history[::3]=[t-offset for t in history[::3]]
    new=[]
    for i in range(3):
        values=sample.safe_logits(logits([vocab.ANTICIPATE]+history+new),len(history)+i)
        if i==0:
            recent=[t for t,n in zip(tokens[::3],tokens[2::3]) if n<vocab.CONTROL_OFFSET][-16:]
            lower=max(current_time,recent[0]+25) if len(recent)==16 else current_time
            # A single piano cannot require unlimited new events at one instant.
            # This only activates above 16 sampled events per quarter-second.
            values=sample.future_logits(values,lower-offset)
        elif i==2:
            # Piano-only generation is a sampling condition, not output rewriting.
            values[vocab.NOTE_OFFSET+128:vocab.REST]=-float('inf')
        values=sample.nucleus(values,top_p)
        new.append(int(torch.multinomial(values.softmax(-1),1,generator=generator)))
    new[0]+=offset
    return new


def tokens_for(notes,origin,program,vocab,controls=False):
    result=[]
    for n in notes:
        start=max(0,round((n['start']-origin)*100));end=round((n['end']-origin)*100)
        if end<=start:continue
        # Long controls are split solely to fit the official 10-second token.
        while start<end:
            length=min(999,end-start)
            event=[start,vocab.DUR_OFFSET+length,vocab.NOTE_OFFSET+program*128+n['midi']]
            result.extend([t+vocab.CONTROL_OFFSET for t in event] if controls else event)
            start+=length
    return result


class DenseGeneration(ValueError):pass


def sample_window(stepper,sample,ops,vocab,generator,tokens,pending,origin,right,clip_end,report_position):
    """An entire pathological candidate is rejected; accepted notes stay intact."""
    tokens=tokens.copy();pending=pending.copy();current=500;end=round((right-origin)*100)
    generated=0;stalled=0;attacks=[];notes=[];steps=[]
    while current<end:
        while pending and current>=pending[0]-vocab.ATIME_OFFSET-500:
            tokens+=pending[:3];pending=pending[3:]
        new=cached_add_token(stepper,sample,ops,vocab,generator,tokens,.95,current)
        at=new[0]
        if at>=end:break
        steps.append(at)
        if len(steps)>=32 and at-steps[-32]<10:raise DenseGeneration('AMT generation stopped advancing.')
        stalled=stalled+1 if at==current else 0
        if stalled>64 or generated>max(128,(end-500)*.32):raise DenseGeneration('AMT generation became too dense.')
        tokens+=new;current=at;generated+=1
        if new[2]!=vocab.REST:
            duration=(new[1]-vocab.DUR_OFFSET)/100
            if duration>0:
                attacks=[t for t in attacks if t>at-25];attacks.append(at)
                if len(attacks)>32:raise DenseGeneration('AMT generation became too dense.')
                notes.append({'start':round(origin+at/100,6),'end':round(min(clip_end,origin+at/100+duration),6),'midi':new[2]-vocab.NOTE_OFFSET})
        report_position(current)
    return notes,generated


def chunks(score,harmony,selection=None):
    """Four-bar segments bounded by real source time; silent sections are skipped."""
    sections=[];bars=harmony['bars'];index=0
    if selection:bars=[b for b in bars if selection['firstMeasure']<=b['number']<=selection['lastMeasure']]
    while index<len(bars):
        first=index;left=bars[first]['playStart'];index+=1
        while index<len(bars) and index-first<4 and bars[index]['playEnd']-left<=MAX_CHUNK_SECONDS:index+=1
        right=min(score['duration'],bars[index-1]['playEnd'])
        if right>left and any(n['start']<right and n['end']>left for n in score['notes']):sections.append({'firstMeasure':bars[first]['number'],'lastMeasure':bars[index-1]['number'],'start':left,'end':right})
    return sections


def infer(score,harmony,seed,on_progress=None,selection=None,base_notes=None):
    import torch
    report=on_progress or (lambda *args:None)
    sections=chunks(score,harmony,selection);output=[];references=[]
    if not sections:raise ValueError('No melody is available in the selected measures.')
    report({'stage':'loading','progress':0.,'completed':0,'total':len(sections)})
    model,ops,sample,vocab,manifest,provenance=runtime()
    boundary=None
    if selection:
        boundary=(harmony['bars'][selection['firstMeasure']-1]['playStart'],harmony['bars'][selection['lastMeasure']-1]['playEnd'])
        output=[n.copy() for n in base_notes or [] if n['start']<boundary[0] or n['start']>=boundary[1]]
    generator=torch.Generator(device='cpu').manual_seed(seed);stepper=CachedLogits(model)
    total=sum(s['end']-s['start'] for s in sections);done=0.;clock=time.monotonic();last_report=0.;created=0
    for number,section in enumerate(sections):
        left,right=section['start'],section['end'];origin=left-PREFIX
        previous=[{'start':max(origin,n['start']),'end':n['end'],'midi':n['midi']} for n in output if n['start']<left and n['end']>origin]
        previous+= [{'start':max(origin,n['start']),'end':n['end'],'midi':n['midi'],'program':MELODY_PROGRAM} for n in score['notes'] if n['start']<left and n['end']>origin]
        history=[]
        for n in previous:history+=tokens_for([n],origin,n.get('program',0),vocab)
        if not any(n.get('program',0)==0 for n in previous):
            first=next((b for b in harmony['bars'] if b['pitches'] and b['playStart']<right and b['playEnd']>left),None)
            if first:
                # An inaudible five-second piano prompt establishes the target track.
                # It precedes the source window; none of these notes enter output.
                bar_length=60/score['bpm']*4
                for start in (PREFIX-2*bar_length,PREFIX-bar_length):
                    if start>=0:history+=tokens_for([{'start':origin+start,'end':origin+min(PREFIX-.05,start+bar_length*.9),'midi':m} for m in first['pitches']],origin,0,vocab)
                if not history:history=tokens_for([{'start':origin+1,'end':origin+4.5,'midi':m} for m in first['pitches']],origin,0,vocab)
        history=ops.sort(history)
        controls=tokens_for([n for n in score['notes'] if left<=n['start']<=right+PREFIX],origin,MELODY_PROGRAM,vocab,True)
        if boundary:controls+=tokens_for([n for n in output if boundary[1]<=n['start']<=right+PREFIX],origin,0,vocab,True)
        controls=ops.sort(controls)
        prompt=ops.pad(history,round(PREFIX*100));tokens,pending=ops.anticipate(prompt,controls)
        def position(current):
            nonlocal last_report
            if time.monotonic()-last_report>=.5:
                report({'stage':'generating','progress':min(.98,(done+min(right-left,max(0,origin+current/100-left)))/max(total,1e-8)),'completed':number,'total':len(sections),'elapsedSeconds':round(time.monotonic()-clock,1)})
                last_report=time.monotonic()
        for attempt in range(3):
            if attempt:
                generator.manual_seed((seed+number*1009+attempt*9176)&0xffffffff)
                report({'stage':'retrying','progress':done/max(total,1e-8),'completed':number,'total':len(sections)})
            if attempt==2:
                first=next((b for b in harmony['bars'] if b['pitches'] and b['playStart']<right and b['playEnd']>left),None)
                clean=tokens_for([{'start':origin+1,'end':origin+4.5,'midi':m} for m in first['pitches']],origin,0,vocab) if first else []
                tokens,pending=ops.anticipate(ops.pad(clean,500),controls)
            try:
                notes,generated=sample_window(stepper,sample,ops,vocab,generator,tokens,pending,origin,right,min(score['duration'],boundary[1]) if boundary else score['duration'],position)
                break
            except DenseGeneration:
                if attempt==2:raise ValueError('AMT generation became too dense. Please regenerate or choose a shorter range.') from None
        output.extend(notes);created+=len(notes)

        done+=right-left;references.append({**section,'notes':generated,'retries':attempt})
        report({'stage':'generating','progress':done/max(total,1e-8),'completed':number+1,'total':len(sections),'elapsedSeconds':round(time.monotonic()-clock,1)})
    if not created:raise ValueError('AMT did not generate playable accompaniment. Please regenerate or choose a longer range.')
    return sorted(output,key=lambda n:(n['start'],n['midi'],n['end'])),references,{'files':manifest['files'],'commit':provenance['commit'],'revision':manifest['revision']}


def instrumental_prompt(score,harmony,left,right,origin,output,vocab):
    """Song-derived, inaudible piano context, with the original phrase rhythm intact."""
    from .instrumental import reference_motif
    previous=[{'start':max(origin+.05,n['start']),'end':min(left,n['end']),'midi':n['midi']} for n in output if n['start']<left and n['end']>origin+.05]
    if previous:return tokens_for(previous,origin,0,vocab)
    motif=reference_motif(score,left,right);edge=max(n['end'] for n in motif)
    history=[]
    for n in motif:
        end=left-.3+n['end']-edge;start=max(origin+.25,left-.3+n['start']-edge)
        if end>start:history.append({'start':start,'end':end,'midi':n['midi']})
    # A chord from a neighboring sung phrase establishes the song's harmonic color.
    neighbor=min((s for s in harmony.get('segments',harmony['bars']) if s['pitches']),key=lambda s:min(abs(s['start']-left),abs(s['end']-right)),default=None)
    if neighbor:
        history += [{'start':origin+.05,'end':origin+.5,'midi':p} for p in neighbor['pitches']]
    return tokens_for(history,origin,0,vocab)


def infer_instrumental(score,harmony,regions,seed,on_progress=None):
    """Compose piano phrases only in validated empty sections; the vocal track is immutable."""
    import torch
    report=on_progress or (lambda *args:None);windows=[]
    for region in regions:
        bars=harmony['bars'][region['firstMeasure']-1:region['lastMeasure']];index=0
        while index<len(bars):
            first=index;left=bars[first]['playStart'];index+=1
            while index<len(bars) and index-first<4 and bars[index]['playEnd']-left<=MAX_CHUNK_SECONDS:index+=1
            windows.append({'firstMeasure':bars[first]['number'],'lastMeasure':bars[index-1]['number'],'start':left,'end':bars[index-1]['playEnd'],'kind':region['kind']})
    if not windows:raise ValueError('No instrumental sections are selected.')
    report({'stage':'loading','progress':0.,'completed':0,'total':len(windows)})
    model,ops,sample,vocab,manifest,provenance=runtime();stepper=CachedLogits(model)
    generator=torch.Generator(device='cpu').manual_seed(seed);output=[];references=[]
    total=sum(w['end']-w['start'] for w in windows);done=0.;last_report=0.;clock=time.monotonic()
    for index,window in enumerate(windows):
        left,right=window['start'],window['end'];origin=left-PREFIX
        history=ops.sort(instrumental_prompt(score,harmony,left,right,origin,output,vocab))
        # Only the arriving original vocal phrase is a future condition. No generated
        # vocal melody or model accompaniment is permitted in the sung section.
        controls=ops.sort(tokens_for([n for n in score['notes'] if right<=n['start']<=right+PREFIX],origin,MELODY_PROGRAM,vocab,True))
        def position(current):
            nonlocal last_report
            if time.monotonic()-last_report>=.5:
                report({'stage':'generating','progress':min(.98,(done+min(right-left,max(0,origin+current/100-left)))/max(total,1e-8)),'completed':index,'total':len(windows),'elapsedSeconds':round(time.monotonic()-clock,1)})
                last_report=time.monotonic()
        for attempt in range(3):
            if attempt:
                generator.manual_seed((seed+index*1009+attempt*9176)&0xffffffff)
                report({'stage':'retrying','progress':done/max(total,1e-8),'completed':index,'total':len(windows)})
            tokens,pending=ops.anticipate(ops.pad(history,500),controls)
            try:
                notes,generated=sample_window(stepper,sample,ops,vocab,generator,tokens,pending,origin,right,right,position)
                if not notes:raise DenseGeneration('No instrumental melody was generated.')
                if any(n['start']<left or n['end']>right+1e-7 for n in notes):raise DenseGeneration('Instrumental notes crossed their section.')
                break
            except DenseGeneration:
                if attempt==2:raise ValueError('Unable to compose this instrumental section. Retry or shorten its range.') from None
        output.extend(notes);done+=right-left;references.append({**window,'notes':generated,'retries':attempt})
        report({'stage':'generating','progress':done/max(total,1e-8),'completed':index+1,'total':len(windows),'elapsedSeconds':round(time.monotonic()-clock,1)})
    return sorted(output,key=lambda n:(n['start'],n['midi'],n['end'])),references,{'version':'amt-instrumental-v1','files':manifest['files'],'commit':provenance['commit'],'revision':manifest['revision']}
