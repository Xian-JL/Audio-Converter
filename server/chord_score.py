"""Engrave aligned block chords below the unchanged right-hand voice."""
import xml.etree.ElementTree as ET
from .melody_score import DURATIONS
from .score import KEYS, spell_pitch, tag

def engrave_block_chords(score,events,choices,title='Melody and block chords'):
    root=ET.fromstring(score['xml']);measures=root.findall('./part/measure')
    root.find('work/work-title').text=title
    root.find('part-list/score-part/part-name').text='Piano'
    divisions=score['divisions'];scale=divisions//32
    durations=DURATIONS if scale==1 else [(n*scale,kind,dotted) for n,kind,dotted in DURATIONS]+[(1,'256th',False)]
    numerator,denominator=map(int,score['meter'].split('/'));bar_ticks=numerator*divisions*4//denominator
    voices=sorted({(e.get('staff',2),e.get('voice',2)) for e in events}) or [(2,2)]
    multi=len(voices)>1
    fifths=KEYS[score['key']];by_id={c['id']:c for c in choices};fragments=[]
    attributes=measures[0].find('attributes');attributes.find('staves').text='2'
    attributes.find('clef').set('number','1')
    clef=tag(attributes,'clef',number=2);tag(clef,'sign','F');tag(clef,'line',4)
    def emit(measure,left,right,event=None,voice=2,staff=2):
        at=left
        while at<right:
            length,kind,dotted=next(d for d in durations if d[0]<=right-at)
            pitches=event['pitches'] if event else [None]
            for index,midi in enumerate(pitches):
                node=tag(measure,'note',**({'id':f"{event['id']}-t{at}-p{midi}"} if event else ({'print-object':'no'} if staff==1 or multi and (staff,voice)!=voices[0] else {})))
                if index:tag(node,'chord')
                if midi is None:tag(node,'rest')
                else:
                    pitch=tag(node,'pitch');step,alter,octave=spell_pitch(midi,fifths);tag(pitch,'step',step)
                    if alter:tag(pitch,'alter',alter)
                    tag(pitch,'octave',octave)
                tag(node,'duration',length)
                stop=event is not None and at>event['startTick'];start=event is not None and at+length<event['endTick']
                if stop:tag(node,'tie',type='stop')
                if start:tag(node,'tie',type='start')
                tag(node,'voice',voice);tag(node,'type',kind)
                if dotted:tag(node,'dot')
                if multi and event:tag(node,'stem','down' if voice==2 else 'up')
                tag(node,'staff',staff)
                if stop or start:
                    nt=tag(node,'notations')
                    if stop:tag(nt,'tied',type='stop')
                    if start:tag(nt,'tied',type='start')
            if event:fragments.append({'id':event['id'],'startTick':at,'endTick':at+length,'pitches':pitches})
            at+=length
    for i,measure in enumerate(measures):
        for old in list(measure.findall('harmony')):measure.remove(old)
        bar=score['measures'][i]
        left=bar.get('startTick',i*bar_ticks);right=bar.get('endTick',left+bar_ticks)
        for staff,voice in voices:
            tag(tag(measure,'backup'),'duration',right-left)
            cursor=left
            for event in events:
                if event.get('voice',2)!=voice or event.get('staff',2)!=staff:continue
                if event['startTick']>=right or event['endTick']<=left:continue
                a=max(left,event['startTick']);b=min(right,event['endTick'])
                if a>cursor:emit(measure,cursor,a,voice=voice,staff=staff)
                if a==event['startTick'] and event.get('showChord',True):
                    c=by_id[event['chordId']];harmony=tag(measure,'harmony',placement='above')
                    pitch=tag(harmony,'root');step,alter,_=spell_pitch(c['root']+60,fifths);tag(pitch,'root-step',step)
                    if alter:tag(pitch,'root-alter',alter)
                    tag(harmony,'kind',{'major':'major','minor':'minor','dim':'diminished','7':'dominant','maj7':'major-seventh','min7':'minor-seventh','dim7':'diminished-seventh','half-dim7':'half-diminished'}[c['quality']],text={'major':'','minor':'m','dim':'dim','7':'7','maj7':'maj7','min7':'m7','dim7':'dim7','half-dim7':'m7b5'}[c['quality']])
                    tag(harmony,'staff',staff)
                emit(measure,a,b,event,voice,staff);cursor=b
            if cursor<right:emit(measure,cursor,right,voice=voice,staff=staff)
    return '<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(root,encoding='unicode'),fragments
