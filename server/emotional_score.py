"""Explicit affect conditions and context-led, bounded CPU instrumental generation."""
import math
import time
from .arrangement import TONICS
from .instrumental import reference_motif

DEFAULT={'engine':'emo','feeling':'sad','contour':'rising'}
ENGINES={'emo','midi-emotion'}
FEELINGS={'sad','calm','tense','bright'}
CONTOURS={'rising','steady','falling'}
ROMANS=['I','I#','II','II#','III','IV','IV#','V','V#','VI','VI#','VII']
MINOR_OFFSETS={'I':0,'I#':1,'II':2,'II#':3,'III':3,'IV':5,'IV#':6,'V':7,'V#':8,'VI':8,'VI#':9,'VII':10}


def checked(value=None):
    if value is None:return DEFAULT.copy()
    if not isinstance(value,dict) or set(value)!=set(DEFAULT) or any(type(x)!=str for x in value.values()) or value['engine'] not in ENGINES or value['feeling'] not in FEELINGS or value['contour'] not in CONTOURS:raise ValueError('Invalid instrumental emotion settings.')
    return value.copy()


def condition(settings,position):
    feeling=settings['feeling'];valence=-.7 if feeling in ('sad','tense') else .65
    low,high={'sad':(-.25,.75),'calm':(-.8,-.1),'tense':(.15,.85),'bright':(.05,.8)}[feeling]
    if settings['contour']=='steady':position=.5
    elif settings['contour']=='falling':position=1-position
    return valence,low+(high-low)*max(0,min(1,position))


def quadrant(values):
    v,a=values
    return 'Q1' if v>=0 and a>=0 else 'Q4' if v>=0 else 'Q2' if a>=0 else 'Q3'


def draw(logits,allowed,generator,temperature=.95,top_p=.9,bias=None):
    import torch
    indices=torch.tensor(sorted(allowed),dtype=torch.long)
    if not len(indices):raise ValueError('The instrumental decoder has no valid next event.')
    scores=logits[indices].float()
    if bias:scores=scores+torch.tensor([bias.get(int(i),0.) for i in indices],dtype=scores.dtype)
    scores=scores/temperature
    probabilities=torch.softmax(scores,-1)
    order=torch.argsort(probabilities,descending=True);probs=probabilities[order]
    keep=probs.cumsum(0)-probs<top_p;probs=probs*keep;probs/=probs.sum()
    return int(indices[order[torch.multinomial(probs,1,generator=generator)]].item())


def pitch_for(key,octave,roman):
    tonic,mode=key.split();offset=ROMANS.index(roman) if mode=='major' else MINOR_OFFSETS[roman]
    return octave*12+TONICS[tonic]+offset


def pitch_tokens(key,pitch):
    tonic,mode=key.split();relative=(pitch-TONICS[tonic])%12;octave=(pitch-relative-TONICS[tonic])//12
    if mode=='major':roman=ROMANS[relative]
    else:roman={v:k for k,v in MINOR_OFFSETS.items()}.get(relative,'III' if relative==4 else 'VII')
    return [f'Note_Octave_{max(1,min(9,octave))}',f'Note_Degree_{roman}']


def reference_bar(score,harmony,region):
    motif=reference_motif(score,region['start'],region['end']);first=motif[0]
    bar=next(b for b in harmony['bars'] if b['startTick']<=first['startTick']<b['endTick'])
    length=bar['endTick']-bar['startTick'];events={}
    for n in score['notes']:
        if not bar['startTick']<=n['startTick']<bar['endTick']:continue
        beat=min(15,round((n['startTick']-bar['startTick'])*16/length));duration=max(1,min(16,round((n['endTick']-n['startTick'])*16/length)))
        events.setdefault(beat,[]).extend(pitch_tokens(score['key'],n['midi'])+[f'Note_Duration_{duration*120}'])
    result=['Bar_None']
    for beat,notes in sorted(events.items()):result += [f'Beat_{beat}']+notes
    return result


def emit_notes(notes,bar_index,region_bars,beat,duration,pitch,velocity):
    if not 21<=pitch<=108:raise ValueError('A generated piano pitch is outside its vocabulary.')
    bar=region_bars[bar_index];start=bar['playStart']+(bar['playEnd']-bar['playStart'])*beat/16
    end_position=bar_index+(beat+duration)/16
    last=min(len(region_bars)-1,int(end_position));fraction=end_position-last
    end=region_bars[-1]['playEnd'] if end_position>=len(region_bars) else region_bars[last]['playStart']+(region_bars[last]['playEnd']-region_bars[last]['playStart'])*fraction
    if end>start:notes.append({'start':round(start,6),'end':round(end,6),'midi':pitch,'velocity':round(max(.05,min(1,velocity)),5)})


def lead_notes(bar,key):
    beat=0;octave=4;pitch=None;result=[]
    for token in bar:
        if token.startswith('Beat_'):beat=int(token.split('_')[1])
        elif token.startswith('Note_Octave_'):octave=int(token.split('_')[-1])
        elif token.startswith('Note_Degree_'):pitch=pitch_for(key,octave,token.split('_')[-1])
        elif token.startswith('Note_Duration_') and pitch is not None:result.append((beat,int(token.split('_')[-1])/120,pitch))
    return result


def lead_bar(step,tokens,vocab,key,generator,anchor=None,history=(),role='statement',center=None,arrival_pcs=(),rhythm_history=()):
    from .phrase_development import pitch_penalty
    e2i={v:i for i,v in enumerate(vocab)};bar=['Bar_None','Beat_0'];tokens += [e2i['Bar_None'],e2i['Beat_0']]
    if anchor and anchor in e2i:
        bar.append(anchor);tokens.append(e2i[anchor])
    beat=0;state='top';octave=4;attacks=0;end=0;played=False;chord_seen=bool(anchor);melody=list(history);rhythm=list(rhythm_history);pitch=None
    for _ in range(192):
        if state=='degree':allowed={i for i,v in enumerate(vocab) if v.startswith('Note_Degree_') and 21<=pitch_for(key,octave,v.split('_')[-1])<=108}
        elif state=='duration':allowed={i for i,v in enumerate(vocab) if v.startswith('Note_Duration_') and (role!='resolution' or int(v.split('_')[-1])/120<=16-beat)}
        else:allowed={i for i,v in enumerate(vocab) if v.startswith('Chord_') and not chord_seen or v.startswith('Note_Octave_') and not played or v.startswith('Beat_') and int(v.split('_')[1])>=max(beat+1,end) or attacks and v in ('Bar_None','EOS_None')}
        bias={i:-pitch_penalty(pitch_for(key,octave,vocab[i].split('_')[-1]),melody,role,center,arrival_pcs if beat>=8 else ()) for i in allowed} if state=='degree' else None
        if state=='duration':
            bias={}
            for i in allowed:
                length=int(vocab[i].split('_')[-1])/120;penalty=0.
                if role=='development' and rhythm[-8:].count(length)>=4:penalty+=1.5
                if role=='development' and len(rhythm)>=2 and rhythm[-1]==rhythm[-2]==length:penalty+=.8
                if role=='resolution' and beat>=8:penalty-=.15*min(length,16-beat)
                bias[i]=-penalty
        word=draw(step(tokens),allowed,generator,bias=bias);name=vocab[word]
        if name in ('Bar_None','EOS_None'):return bar
        tokens.append(word);bar.append(name)
        if name.startswith('Beat_'):beat=int(name.split('_')[1]);played=False;chord_seen=False
        if name.startswith('Chord_'):chord_seen=True
        if state=='degree':pitch=pitch_for(key,octave,name.split('_')[-1]);state='duration'
        elif state=='duration':state='top';attacks+=1;end=beat+int(name.split('_')[-1])/120;played=True;melody.append(pitch);rhythm.append(int(name.split('_')[-1])/120)
        elif name.startswith('Note_Octave_'):octave=int(name.split('_')[-1]);state='degree'
        if attacks>48:raise ValueError('Generated lead sheet became too dense. Retry this section.')
    raise ValueError('Generated lead sheet did not finish a bar. Retry this section.')


def performance_bar(step,base_tokens,base_segments,vocab,key,generator,index,bars,settings,history,role,lead,arrival_pcs):
    from .phrase_development import pitch_penalty
    from statistics import median
    e2i={v:i for i,v in enumerate(vocab)};tokens=base_tokens.copy();segments=base_segments.copy();notes=[]
    tempo=min((x for x in vocab if x.startswith('Tempo_') and x!='Tempo_Conti'),key=lambda x:abs(int(x.split('_')[1])-settings['bpm']))
    tokens += [e2i['Bar_None'],e2i['Beat_0'],e2i[tempo]];segments += [1,1,1]
    beat=0;state='top';octave=4;pitch=60;duration=1;attacks=0;onsets={};chord_seen=False;melody=list(history);melody_indices={}
    center=median(melody[-12:]) if melody else None
    # A contextual register is applied while sampling, never by folding generated notes.
    lower=max(21,min(p for _,_,p in lead)-36);upper=min(108,max(p for _,_,p in lead)+12)
    for _ in range(384):
        played=onsets.get(beat,set());bias={}
        if state=='degree':
            allowed={j for j,v in enumerate(vocab) if v.startswith('Note_Degree_') and lower<=pitch_for(key,octave,v.split('_')[-1])<=upper and pitch_for(key,octave,v.split('_')[-1]) not in played}
            expected=next((p for at,length,p in reversed(lead) if at<=beat<at+length),None)
            for j in allowed:
                candidate=pitch_for(key,octave,vocab[j].split('_')[-1])
                absolute_time=bars[index]['playStart']+(bars[index]['playEnd']-bars[index]['playStart'])*beat/16
                under_sustain=any(n['midi']>candidate and n['end']>absolute_time+1e-6 for n in notes)
                if candidate>=55 and not under_sustain:
                    bias[j]=-pitch_penalty(candidate,melody,role,center,arrival_pcs if beat>=8 else ())
                    if expected is not None and candidate%12!=expected%12:bias[j]-=1.
        elif state=='duration':allowed={j for j,v in enumerate(vocab) if v.startswith('Note_Duration_')}
        elif state=='velocity':allowed={j for j,v in enumerate(vocab) if v.startswith('Note_Velocity_')}
        else:
            allowed=set()
            for j,v in enumerate(vocab):
                if v.startswith('Chord_') and not chord_seen:allowed.add(j)
                elif v.startswith('Note_Octave_'):
                    octv=int(v.split('_')[-1])
                    if any(lower<=pitch_for(key,octv,r)<=upper and pitch_for(key,octv,r) not in played for r in ROMANS):
                        allowed.add(j);bias[j]=-.7*max(0,len(played)-4)
                elif v.startswith('Beat_') and int(v.split('_')[1])>beat:allowed.add(j)
                elif attacks and v in ('Track_LeadSheet','EOS_None'):allowed.add(j)
        word=draw(step(tokens,segments),allowed,generator,bias=bias);name=vocab[word]
        if name in ('Track_LeadSheet','EOS_None'):
            if state!='top':raise ValueError('Generated performance ended inside a note.')
            return notes,tokens,segments
        tokens.append(word);segments.append(1)
        if name.startswith('Beat_'):beat=int(name.split('_')[1]);chord_seen=False
        if name.startswith('Chord_'):chord_seen=True
        if state=='degree':pitch=pitch_for(key,octave,name.split('_')[-1]);state='duration'
        elif state=='duration':duration=int(name.split('_')[-1])/120;state='velocity'
        elif state=='velocity':
            velocity=int(name.split('_')[-1])/127
            envelope=.75+.25*(index/max(1,len(bars)-1)) if settings['contour']=='rising' else 1-.25*index/max(1,len(bars)-1) if settings['contour']=='falling' else 1
            emit_notes(notes,index,bars,beat,duration,pitch,velocity*envelope);state='top';attacks+=1;onsets.setdefault(beat,set()).add(pitch)
            absolute_time=bars[index]['playStart']+(bars[index]['playEnd']-bars[index]['playStart'])*beat/16
            under_sustain=any(n['midi']>pitch and n['end']>absolute_time+1e-6 for n in notes)
            if pitch>=55 and pitch==max(onsets[beat]) and not under_sustain:
                if beat in melody_indices:melody[melody_indices[beat]]=pitch
                else:melody_indices[beat]=len(melody);melody.append(pitch)
        elif name.startswith('Note_Octave_'):octave=int(name.split('_')[-1]);state='degree'
        if attacks>64:raise ValueError('Generated performance became too dense. Retry this section.')
    raise ValueError('Generated performance did not finish a bar. Retry this section.')


def infer_emo(score,harmony,regions,seed,settings,report):
    import torch
    from statistics import median
    from .emotion_runtime import emo_models,EmoLeadLogits,EmoPerformanceLogits
    from .phrase_development import VERSION,roles,boundary_harmonies,lead_signature,note_signature,repeated_bar,diagnostics
    report({'stage':'loading','progress':0})
    first,second,vocabs,provenance=emo_models();v1,v2=vocabs;e1={v:i for i,v in enumerate(v1)};e2={v:i for i,v in enumerate(v2)}
    provenance={**provenance,'version':'emo-cpu-v2','development':VERSION}
    generator=torch.Generator().manual_seed(seed);output=[];references=[];total=sum(r['lastMeasure']-r['firstMeasure']+1 for r in regions);done=0
    tonic,mode=score['key'].split();names=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];keyname=names[TONICS[tonic]];key_token='Key_'+(keyname if mode=='major' else keyname.lower())
    for region in regions:
        bars=harmony['bars'][region['firstMeasure']-1:region['lastMeasure']];reference=reference_bar(score,harmony,region);plan=roles(len(bars))
        outgoing,arriving=boundary_harmonies(harmony,region);arrival_pcs=tuple(p%12 for p in arriving['pitches']) if arriving else ()
        lead_tokens=[e1['Emotion_Negative' if settings['feeling'] in ('sad','tense') else 'Emotion_Positive'],e1[key_token]]+[e1[x] for x in reference]
        lead_step=EmoLeadLogits(first);leads=[];lead_shapes=[];lead_history=[];rhythm_history=[];center=None;phrases=[]
        for i,bar in enumerate(bars):
            neighbor=outgoing if i==0 else arriving if i==len(bars)-1 else None
            anchor=None
            if neighbor:
                quality={'major':'M','minor':'m','dim':'o','7':'7','maj7':'M7','min7':'m7','dim7':'o7','half-dim7':'/o7'}[neighbor['quality']]
                anchor=f"Chord_{ROMANS[(neighbor['root']-TONICS[tonic])%12]}_{quality}"
            base=lead_tokens.copy()
            for attempt in range(3):
                candidate_tokens=base.copy()
                trial=lead_bar(lead_step,candidate_tokens,v1,score['key'],generator,anchor,lead_history,plan[i],center,arrival_pcs,rhythm_history)
                parsed=lead_notes(trial,score['key']);signature=lead_signature(parsed)
                if not repeated_bar(signature,lead_shapes):break
            else:raise ValueError('EMO repeated a complete melody bar. Please regenerate this section.')
            lead_tokens=candidate_tokens;leads.append(trial);lead_shapes.append(signature);lead_history += [p for _,_,p in parsed];rhythm_history += [d for _,d,_ in parsed]
            if center is None and parsed:center=median(p for _,_,p in parsed)
            phrases.append({'measure':bar['number'],'role':plan[i],'lead':parsed,'leadRetries':attempt,'anchor':anchor})
            report({'stage':'composing','progress':(done+i*.25)/total,'completed':done+i,'total':total})
        blocks=[];performance_step=EmoPerformanceLogits(second);section_count=len(output);melody_history=[];performance_shapes=[]
        for i,lead in enumerate(leads):
            values=condition(settings,i/max(1,len(leads)-1));prefix=[e2['Emotion_'+quadrant(values)],e2[key_token]]
            while blocks and sum(len(b) for b in blocks)>1300:blocks.pop(0)
            base_tokens=prefix+[v for b in blocks for v in b]+[e2['Track_LeadSheet']]+[e2[x] for x in lead]+[e2['Track_Full']]
            base_segments=[0,0]+[s for b in blocks for s in b.segments]+[0]*(len(lead)+1)+[1]
            start=len(base_tokens)
            for attempt in range(3):
                bar_notes,tokens,segments=performance_bar(performance_step,base_tokens,base_segments,v2,score['key'],generator,i,bars,{**settings,'bpm':score['bpm']},melody_history,plan[i],phrases[i]['lead'],arrival_pcs)
                signature=note_signature(bar_notes,bars[i]['playStart'],bars[i]['playEnd'])
                if not repeated_bar(signature,performance_shapes):break
            else:raise ValueError('EMO repeated a complete performance bar. Please regenerate this section.')
            output+=bar_notes;performance_shapes.append(signature);melody_history += [p for _,_,p in signature]
            phrases[i]['performanceRetries']=attempt
            block=TokenBlock(tokens[start-len(lead)-2:]);block.segments=segments[start-len(lead)-2:];blocks.append(block)
            done+=1;report({'stage':'performing','progress':done/total,'completed':done,'total':total})
        if len(output)==section_count:raise ValueError('EMO generated an empty section. Retry this section.')
        references.append({**region,'notes':len(output)-section_count,'emotion':settings.copy(),'phrases':phrases,'melodyDevelopment':diagnostics(performance_shapes),
                           'conditionCurve':[{'measure':b['number'],'valence':condition(settings,j/max(1,len(bars)-1))[0],'arousal':condition(settings,j/max(1,len(bars)-1))[1],'quadrant':quadrant(condition(settings,j/max(1,len(bars)-1)))} for j,b in enumerate(bars)]})
    return output,references,provenance


class TokenBlock(list):pass


def infer_midi(score,harmony,regions,seed,settings,report):
    import torch
    from .emotion_runtime import midi_model,MidiLogits
    report({'stage':'loading','progress':0});model,maps,provenance=midi_model();mapping=maps['tuple2idx'];reverse=maps['idx2tuple'];events=maps['event2idx']
    on,off,shift=events['ON_PIANO'],events['OFF_PIANO'],events['TIMESHIFT'];generator=torch.Generator().manual_seed(seed);output=[];references=[];total=sum(r['end']-r['start'] for r in regions);done=0
    for region in regions:
        motif=reference_motif(score,region['start'],region['end']);edge=max(n['end'] for n in motif);begin=edge-4.;schedule=[]
        for n in motif:
            if n['end']<=begin or not 21<=n['midi']<=108:continue
            schedule += [(round(max(0,n['start']-begin)*1000),on,n['midi']),(round((n['end']-begin)*1000),off,n['midi'])]
        tokens=[mapping['<START>']];clock=0
        for at,event,pitch in sorted(schedule,key=lambda x:(x[0],x[1]==on)):
            gap=max(0,round((at-clock)/8)*8)
            while gap>0:
                amount=min(1000,gap);tokens.append(mapping[shift,amount]);clock+=amount;gap-=amount
            tokens.append(mapping[event,pitch])
        origin=clock;active={};step=MidiLogits(model);local=[];last_bar=-1;section_seconds=region['end']-region['start'];bars=harmony['bars'][region['firstMeasure']-1:region['lastMeasure']]
        for count in range(max(1024,int(section_seconds*120))):
            elapsed=(clock-origin)/1000
            if elapsed>=section_seconds:break
            bar_index=next((i for i,b in enumerate(bars) if b['playStart']<=region['start']+elapsed<b['playEnd']),len(bars)-1)
            values=condition(settings,bar_index/max(1,len(bars)-1))
            if bar_index!=last_bar:report({'stage':'composing','progress':(done+elapsed)/total,'completed':bar_index,'total':len(bars)});last_bar=bar_index
            if len(tokens)>1024:tokens=tokens[-768:]
            allowed={idx for symbol,idx in mapping.items() if isinstance(symbol,tuple) and (symbol[0]==shift or symbol[0]==on and symbol[1] not in active and len(active)<16 or symbol[0]==off and symbol[1] in active)}
            word=draw(step(tokens,values),allowed,generator,temperature=1.0);tokens.append(word);event,pitch=reverse[word]
            if event==shift:clock+=pitch
            elif event==on:active[pitch]=elapsed
            else:
                start=active.pop(pitch)
                if elapsed>start:local.append({'start':region['start']+start,'end':min(region['end'],region['start']+elapsed),'midi':pitch,'velocity':.65+.25*max(0,min(1,elapsed/section_seconds)) if settings['contour']=='rising' else .9-.25*max(0,min(1,elapsed/section_seconds)) if settings['contour']=='falling' else .8})
            if len(tokens)>64 and not any(isinstance(reverse.get(t),tuple) and reverse[t][0]==shift for t in tokens[-64:]):raise ValueError('MIDI Emotion stopped advancing. Retry this section.')
        else:raise ValueError('MIDI Emotion exceeded its event budget. Retry this section.')
        for pitch,start in active.items():
            if start<section_seconds:local.append({'start':region['start']+start,'end':region['end'],'midi':pitch,'velocity':.85})
        if not local:raise ValueError('MIDI Emotion generated an empty section. Retry this section.')
        output+=local;references.append({**region,'notes':len(local),'emotion':settings.copy(),'conditionCurve':[{'measure':b['number'],'valence':condition(settings,j/max(1,len(bars)-1))[0],'arousal':condition(settings,j/max(1,len(bars)-1))[1]} for j,b in enumerate(bars)]});done+=section_seconds;report({'stage':'composing','progress':done/total})
    return sorted(output,key=lambda n:(n['start'],n['midi'])),references,provenance


def infer(score,harmony,regions,seed,settings,on_progress=None):
    report=on_progress or (lambda value:None);settings=checked(settings)
    return (infer_emo if settings['engine']=='emo' else infer_midi)(score,harmony,regions,seed,settings,report)
