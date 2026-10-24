import { useEffect, useRef, useState } from 'react';
import { api } from './lib/api';
import {translatedError,en,zh as chinese} from './lib/i18n';
import type { ScoreData } from './lib/api';
import type { ScoreVersion } from './lib/project';

export default function MelodyEditor({score,jobId,language,selectedId,onRevision,onBeforeChange,busy,onPreview}:{score:ScoreData;jobId:string;language:'en'|'zh';selectedId:string|null;onRevision:(v:ScoreVersion,selected:string|null)=>void;onBeforeChange:()=>void;busy:boolean;onPreview:(start:number,end:number)=>void}){
  const zh=language==='zh',note=score.notes?.find(n=>n.id===selectedId);
  const [midi,setMidi]=useState('60'),[start,setStart]=useState('0'),[end,setEnd]=useState('1'),[split,setSplit]=useState('0.5'),[working,setWorking]=useState(false),[error,setError]=useState('');
  const request=useRef<AbortController|null>(null);
  useEffect(()=>()=>request.current?.abort(),[]);
  useEffect(()=>{setError('');if(note){setMidi(String(note.midi));setStart(String(note.start));setEnd(String(note.end));setSplit(((note.start+note.end)/2).toFixed(3));}},[note]);
  const submit=async(kind:string)=>{
    if(busy||working)return;onBeforeChange();setWorking(true);setError('');const controller=new AbortController();request.current=controller;
    try{
      const result=await api<ScoreVersion&{selectedNoteId:string|null}>(`/api/jobs/${jobId}/edit`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({bpm:score.bpm,meter:score.meter,key:score.key,anchorNoteId:score.downbeat?.noteId,editedNotes:score.editedNotes,identityNotesJson:score.identityNotesJson,sourceFingerprint:score.scoreFingerprint,operation:{kind,id:selectedId,midi:Number(midi),start:Number(start),end:Number(end),time:Number(split)}})});
      if(!controller.signal.aborted)onRevision(result,result.selectedNoteId);
    }catch(cause){if(!controller.signal.aborted)setError(translatedError(String((cause as Error).message),zh?chinese:en));}
    finally{if(!controller.signal.aborted)setWorking(false);}
  };
  const valid=[start,end,midi].every(v=>v.trim()!==''&&Number.isFinite(Number(v)))&&Number(start)>=0&&Number(end)>Number(start)&&Number(end)<=score.duration&&Number.isInteger(Number(midi))&&Number(midi)>=0&&Number(midi)<=127;
  const names=['C','C♯','D','D♯','E','F','F♯','G','G♯','A','A♯','B'];
  const pitch=Number(midi);const name=Number.isInteger(pitch)&&pitch>=0&&pitch<=127?`${names[pitch%12]}${Math.floor(pitch/12)-1}`:'—';
  return <section className="melody-editor" aria-label={zh?'旋律音符编辑':'Melody note editor'}>
    <p>{zh?'点击高音谱表中的音符进行修改。时间以原音频秒数计；音高使用实际试听音高。修改后请重新生成和弦。':'Select a treble note to edit. Times use original-audio seconds; pitch is the sounding pitch. Regenerate chords after editing.'}</p>
    <div className="note-fields"><label>{zh?'音高 MIDI':'Pitch MIDI'}<input aria-label={zh?'音高 MIDI':'Pitch MIDI'} type="number" min="0" max="127" step="1" value={midi} onChange={e=>setMidi(e.target.value)}/><small>{name}</small></label><label>{zh?'起音（秒）':'Start (seconds)'}<input aria-label={zh?'起音（秒）':'Start (seconds)'} type="number" min="0" max={score.duration} step=".01" value={start} onChange={e=>setStart(e.target.value)}/></label><label>{zh?'结束（秒）':'End (seconds)'}<input aria-label={zh?'结束（秒）':'End (seconds)'} type="number" min="0" max={score.duration} step=".01" value={end} onChange={e=>setEnd(e.target.value)}/></label></div>
    <div className="gf-review-row"><button className="primary-button" disabled={!note||!valid||working||busy} onClick={()=>void submit('update')}>{working?(zh?'保存中…':'Saving…'):(zh?'应用修改':'Apply edit')}</button><button disabled={!valid||working||busy} onClick={()=>void submit('insert')}>{zh?'插入为新音':'Insert new note'}</button><button disabled={!note||working||busy} onClick={()=>void submit('delete')}>{zh?'删除选中音':'Delete selected'}</button><button disabled={!note||working||busy} onClick={()=>note&&onPreview(Math.max(0,note.start-1),Math.min(score.duration,note.end+1))}>{zh?'试听附近':'Preview nearby'}</button></div>
    {note&&<div className="gf-review-row"><label>{zh?'拆分位置（秒）':'Split at (seconds)'}<input aria-label={zh?'拆分位置（秒）':'Split at (seconds)'} type="number" step=".01" min={note.start} max={note.end} value={split} onChange={e=>setSplit(e.target.value)}/></label><button disabled={working||busy||Number(split)<=note.start||Number(split)>=note.end||!split.trim()} onClick={()=>void submit('split')}>{zh?'拆分音符':'Split note'}</button><button disabled={working||busy} onClick={()=>void submit('merge')}>{zh?'合并下一个同音':'Merge next equal pitch'}</button></div>}
    {error&&<p role="alert" className="score-inline-error">{error}</p>}
  </section>;
}
