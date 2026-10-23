import { useEffect, useMemo, useRef, useState } from 'react';
import type { OpenSheetMusicDisplay } from 'opensheetmusicdisplay';
import type { ScoreData, BasicHarmony as Harmony, AccompanimentData } from './lib/api';
import BasicHarmony from './BasicHarmony';
import Accompaniment from './Accompaniment';
import { api } from './lib/api';
import { ScorePlayback } from './lib/playback';
import { instruments } from './lib/instruments';
import type { InstrumentId } from './lib/instruments';
import { PAGE_WIDTH, pageFileName, pagePng, saveBlob, songTitle } from './lib/scorePages';
import { zipFiles } from './lib/zip';

const words={
  en:{title:'Score',play:'Play score',pause:'Pause',stop:'Stop',measure:'Measure / time',from:'Play from measure',seek:'Playback position',melody:'Melody',chords:'Chords',loading:'Drawing score…',error:'Unable to draw or play the score. Please retry.',anchor:'Locate measure downbeat',anchorHint:'Select a melody note onset that you know is beat 1.',selected:'Downbeat reference',rebuild:'Rebuild score',rebuilding:'Rebuilding…',cancel:'Cancel selection',preview:'Hear nearby melody',restore:'Restore last downbeat',versions:'Score version',original:'Original score',rebuilt:'Rebuilt',tie:'Select a note onset, not a tied continuation.',rebarError:'Unable to rebuild. Please select another note onset and retry.',pickup:'Pickup',regenerate:'Chords will be regenerated. The original score and its settings are retained.'},
  zh:{title:'乐谱',play:'播放乐谱',pause:'暂停',stop:'停止',measure:'小节 / 时间',from:'从此小节播放',seek:'播放位置',melody:'旋律',chords:'和弦',loading:'正在绘制乐谱…',error:'无法绘制或播放乐谱，请重试。',anchor:'定位小节第一拍',anchorHint:'请点选一个确定落在第一拍上的旋律起音。',selected:'第一拍参考',rebuild:'重构乐谱',rebuilding:'正在重构…',cancel:'取消定位',preview:'试听附近旋律',restore:'恢复上次定位',versions:'查看版本',original:'原始乐谱',rebuilt:'重构',tie:'这是延音片段，请选择音符的真实起音。',rebarError:'无法重构，请重新选择起音后重试。',pickup:'弱起',regenerate:'重构将重新配置和弦；原谱及其设置仍会保留。'},
};
const time=(value:number)=>{const ticks=Math.round(value*100);return `${Math.floor(ticks/6000)}:${(ticks%6000/100).toFixed(2).padStart(5,'0')}`;};

export default function MelodyScore({data:originalData,language,onStartScore,originalPlaying,originalTime,jobId}:{jobId:string;data:ScoreData;language:'en'|'zh';onStartScore:()=>void;originalPlaying:boolean;originalTime:number}){
  const text=words[language];
  const [versions,setVersions]=useState<{score:ScoreData;harmony:Harmony|null}[]>(()=>[{score:originalData,harmony:null}]);
  const [activeVersion,setActiveVersion]=useState(0);
  const data=versions[activeVersion].score,harmony=versions[activeVersion].harmony;
  const setHarmony=(next:Harmony)=>setVersions(previous=>previous.map((v,i)=>i===activeVersion&&v.score.scoreFingerprint===next.sourceFingerprint?{...v,harmony:next}:v));
  const [picking,setPicking]=useState(false),[candidateId,setCandidateId]=useState<string|null>(null),[rebarBusy,setRebarBusy]=useState(false),[anchorMessage,setAnchorMessage]=useState('');
  const anchorStorage='score-downbeat-v1:'+originalData.scoreFingerprint;
  const [savedAnchor,setSavedAnchor]=useState<string|null>(()=>{try{const value=JSON.parse(localStorage.getItem(anchorStorage)||'{}').noteId;return originalData.notes?.some(n=>n.id===value)?value:null;}catch{return null;}});
  const rebuildRequest=useRef<AbortController|null>(null);
  useEffect(()=>()=>rebuildRequest.current?.abort(),[]);
  const candidate=data.notes?.find(n=>n.id===candidateId);
  const [melodyEnabled,setMelodyEnabled]=useState(true),[chordsEnabled,setChordsEnabled]=useState(true);
  const [melodyInstrument,setMelodyInstrument]=useState<InstrumentId>('piano'),[chordInstrument,setChordInstrument]=useState<InstrumentId>('piano');
  const [currentPage,setCurrentPage]=useState(1),[pageCount,setPageCount]=useState(0),[exporting,setExporting]=useState(false),[exportProgress,setExportProgress]=useState(0);
  const pages=useRef<SVGSVGElement[]>([]),measurePages=useRef(new Map<number,number>()),pageShell=useRef<HTMLDivElement>(null),previousPage=useRef(1);
  const [position,setPosition]=useState(0),[playing,setPlaying]=useState(false),[loading,setLoading]=useState(false),[renderingState,setRendering]=useState(true),[renderedXml,setRenderedXml]=useState(''),[error,setError]=useState('');
  const [mapped,setMapped]=useState(0);
  const host=useRef<HTMLDivElement>(null),player=useRef<ScorePlayback|null>(null),endAt=useRef(data.duration),requestId=useRef(0);
  const measureElements=useRef(new Map<number,SVGElement[]>()),highlighted=useRef(0);
  const textureKey=`${activeVersion}:${harmony?.fingerprint||''}`;
  const [textureSets,setTextureSets]=useState<Record<string,{items:AccompanimentData[];active:number}>>({});
  const [textureBusy,setTextureBusy]=useState(false);
  const textureSet=textureSets[textureKey]||{items:[],active:-1};
  const texture=textureSet.items[textureSet.active]||null;
  const displayedXml=texture?.xml||harmony?.xml||data.xml;
  const rendering=renderingState||renderedXml!==displayedXml;
  const activeNotes=useMemo(()=>({...data,events:[...data.events,...(texture?.events||harmony?.events||[])].sort((a,b)=>a.start-b.start)}),[data,harmony,texture]);
  const measures=useMemo(()=>data.measures.map((bar,index)=>({...bar,playStart:harmony?.bars[index]?.playStart??bar.start,playEnd:harmony?.bars[index]?.playEnd??bar.end})),[data,harmony]);
  const displayTime=originalPlaying?originalTime:position;
  const currentMeasure=measures.find(b=>displayTime>=b.playStart&&displayTime<b.playEnd)?.number||(displayTime<(measures[0]?.playStart||0)?1:measures.at(-1)?.number)||1;
  const pause=()=>{requestId.current++;setPosition(player.current?.pause()||0);setPlaying(false);setLoading(false);};
  useEffect(()=>{
    const instance=new ScorePlayback(activeNotes,setPosition,()=>{setPlaying(false);setPosition(endAt.current);});player.current=instance;
    return()=>{requestId.current++;instance.dispose();if(player.current===instance)player.current=null;};
  },[activeNotes]);
  useEffect(()=>{player.current?.setInstruments(melodyInstrument,chordInstrument);},[melodyInstrument,chordInstrument,activeNotes]);
  useEffect(()=>{if(originalPlaying)pause();},[originalPlaying]);
  useEffect(()=>{
    for(const element of measureElements.current.get(highlighted.current)||[])element.classList.remove('measure-current');
    for(const element of measureElements.current.get(currentMeasure)||[])element.classList.add('measure-current');
    highlighted.current=currentMeasure;
  },[currentMeasure,rendering]);
  useEffect(()=>{const page=measurePages.current.get(currentMeasure);if(page&&!rendering)setCurrentPage(page);},[currentMeasure,rendering]);
  useEffect(()=>{
    pages.current.forEach((svg,index)=>{const container=svg.parentElement;if(container)container.hidden=index+1!==currentPage;});
    if(currentPage!==previousPage.current&&(playing||originalPlaying))pageShell.current?.scrollIntoView({block:'start',behavior:'auto'});
    previousPage.current=currentPage;
  },[currentPage,pageCount,rendering,playing,originalPlaying]);
  useEffect(()=>{
    let disposed=false,sheet:OpenSheetMusicDisplay|undefined;
    setRendering(true);setError('');
    const attach=(display:OpenSheetMusicDisplay)=>{
      measureElements.current.clear();measurePages.current.clear();const ids=new Set<string>();
      const svgs=[...host.current!.querySelectorAll<SVGSVGElement>('svg')];pages.current=svgs;
      svgs.forEach((svg,index)=>{const parent=svg.parentElement!;parent.classList.add('score-page');parent.dataset.page=String(index+1);parent.hidden=false;svg.dataset.page=String(index+1);if(!svg.hasAttribute('viewBox'))svg.setAttribute('viewBox',`0 0 ${parseFloat(svg.getAttribute('width')||'840')} ${parseFloat(svg.getAttribute('height')||'1188')}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',`${songTitle(data.sourceName)} · Page ${index+1}`);});
      const byTick=new Map((data.fragments||[]).map(f=>[f.startTick,f.noteId]));
      const cursor=display.cursor;cursor.reset();cursor.SkipInvisibleNotes=false;let safe=0;
      while(!cursor.Iterator.EndReached&&safe++<200000){
        const number=cursor.Iterator.CurrentMeasureIndex+1;
        for(const note of cursor.GNotesUnderCursor()){
          const svgNote=note as typeof note & {getSVGGElement():SVGGElement;getNoteheadSVGs():HTMLElement[]};
          const element=svgNote.getSVGGElement();if(!element||element.dataset.measure)continue;
          const staff=note.sourceNote.ParentVoiceEntry.ParentVoice.VoiceId===2?2:1;
          element.dataset.measure=String(number);element.dataset.page=element.closest('svg')?.dataset.page||'1';element.dataset.staff=String(staff);element.classList.add('score-note');element.setAttribute('role','button');element.setAttribute('tabindex','0');element.setAttribute('aria-label',`${text.from} ${data.measures[number-1]?.displayNumber??number}`);
          if(staff===1&&!note.sourceNote.isRest()){
            const tick=Math.round(note.sourceNote.getAbsoluteTimestamp().RealValue*4*(data.divisions||32));const id=byTick.get(tick);
            if(id){element.dataset.noteId=id;ids.add(id);element.dataset.anchorOnset=String(data.notes?.find(n=>n.id===id)?.startTick===tick);}
          }
          try{const head=svgNote.getNoteheadSVGs()[0] as unknown as SVGGraphicsElement|undefined;const box=(head||element).getBBox();
            const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');rect.setAttribute('x',String(box.x-5));rect.setAttribute('y',String(box.y-5));rect.setAttribute('width',String(Math.max(20,box.width+10)));rect.setAttribute('height',String(Math.max(20,box.height+10)));rect.classList.add('score-hitbox');element.insertBefore(rect,element.firstChild);
          }catch{/* Hidden rests need no additional pointer target. */}
        }
        cursor.next();
      }
      cursor.reset();cursor.hide();setMapped(ids.size);
      if(ids.size!==data.noteCount)throw Error('Incomplete melody rendering');
      for(const label of host.current?.querySelectorAll('svg text')||[]){
        const match=label.textContent?.match(/^(\d+)\s*·\s*\d+:/);if(!match)continue;
        const logical=data.measures.find(m=>(m.displayNumber??m.number)===Number(match[1]));if(!logical)continue;
        label.setAttribute('data-measure',String(logical.number));label.setAttribute('role','button');label.setAttribute('tabindex','0');label.setAttribute('aria-label',`${text.from} ${match[1]}`);label.classList.add('measure-link');
      }
      const layers=svgs.map(svg=>{const layer=document.createElementNS('http://www.w3.org/2000/svg','g');layer.classList.add('measure-hit-layer');const root=svg.querySelector('g');if(root)root.insertBefore(layer,root.firstChild);return layer;});
        for(const [index,staves] of display.GraphicSheet.MeasureList.entries()){
          if(!staves.length)continue;
          const page=staves[0].ParentMusicSystem.Parent;const pageIndex=display.GraphicSheet.MusicPages.indexOf(page);const layer=layers[pageIndex];if(!layer)throw Error('Unmapped score page');
          measurePages.current.set(index+1,pageIndex+1);
          const origin=page.PositionAndShape.AbsolutePosition;
          const boxes=staves.map(s=>s.PositionAndShape),left=Math.min(...boxes.map(b=>(b.AbsolutePosition.x+b.BorderLeft)*10)),right=Math.max(...boxes.map(b=>(b.AbsolutePosition.x+b.BorderRight)*10));
          const top=Math.min(...boxes.map(b=>b.AbsolutePosition.y*10))-9,bottom=Math.max(...boxes.map(b=>b.AbsolutePosition.y*10))+49;
          const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');rect.setAttribute('x',String(left-origin.x*10));rect.setAttribute('y',String(top-origin.y*10));rect.setAttribute('width',String(right-left));rect.setAttribute('height',String(bottom-top));rect.dataset.measure=String(index+1);rect.dataset.page=String(pageIndex+1);rect.classList.add('measure-hitbox');if(index+1===highlighted.current)rect.classList.add('measure-current');layer.appendChild(rect);measureElements.current.set(index+1,[rect]);
        }
      setPageCount(svgs.length);setCurrentPage(p=>Math.min(Math.max(p,1),svgs.length));
    };
    void(async()=>{try{
      const {OpenSheetMusicDisplay}=await import('opensheetmusicdisplay');if(disposed||!host.current)return;
      host.current.replaceChildren();const layout=document.createElement('div');layout.className='score-layout';layout.style.width=`${PAGE_WIDTH}px`;host.current.appendChild(layout);
      sheet=new OpenSheetMusicDisplay(layout,{autoResize:false,backend:'svg',autoBeam:true,drawTitle:false,drawComposer:false,drawPartNames:false,drawMeasureNumbers:false,drawMetronomeMarks:false,fillEmptyMeasuresWithWholeRest:0,pageFormat:'A4_P',followCursor:false});
      sheet.EngravingRules.PageBottomMargin=13;
      sheet.Zoom=1;await sheet.load(displayedXml);if(disposed)return;sheet.render();attach(sheet);layout.style.width='100%';setRenderedXml(displayedXml);setRendering(false);
    }catch(cause){console.error(cause);if(!disposed){setPageCount(0);setRenderedXml(displayedXml);setRendering(false);setError(text.error);}}})();
    return()=>{disposed=true;sheet?.clear();measureElements.current.clear();measurePages.current.clear();pages.current=[];};
  },[displayedXml,language]);
  const play=async(at=originalPlaying?originalTime:position,until=data.duration,solo=false)=>{
    const current=++requestId.current;onStartScore();setPlaying(false);setPosition(at);setLoading(true);setError('');endAt.current=until;const instance=player.current;
    try{instance?.setVoices(solo||melodyEnabled,!solo&&chordsEnabled);const started=await instance?.play(at,until);if(current===requestId.current&&instance===player.current&&started)setPlaying(true);}
    catch{if(current===requestId.current)setError(language==='zh'?'无法加载或播放所选音色，请重试或切换乐器。':'Unable to load or play the selected instrument. Retry or choose another instrument.');}
    finally{if(current===requestId.current)setLoading(false);}
  };
  const playMeasure=(number:number,only=false)=>{const bar=measures.find(b=>b.number===number);if(bar){setCurrentPage(measurePages.current.get(number)||1);void play(bar.playStart,only?bar.playEnd:data.duration);}};
  useEffect(()=>{for(const element of host.current?.querySelectorAll<SVGElement>('[data-anchor-onset="true"]')||[])element.classList.toggle('anchor-selected',picking&&element.dataset.noteId===candidateId);},[picking,candidateId,rendering]);
  const selectAnchor=(target:Element)=>{
    const note=target.closest<SVGElement>('[data-note-id]');
    if(!note||note.dataset.anchorOnset!=='true'){setAnchorMessage(text.tie);return;}
    setCandidateId(note.dataset.noteId!);setAnchorMessage('');
  };
  const rebuild=async(id=candidateId)=>{
    if(!id)return;pause();onStartScore();rebuildRequest.current?.abort();const controller=new AbortController();rebuildRequest.current=controller;setRebarBusy(true);setAnchorMessage('');
    try{
      const result=await api<{score:ScoreData;harmony:Harmony|null}>(`/api/jobs/${jobId}/rebar`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({bpm:originalData.bpm,meter:originalData.meter,key:originalData.key,sourceFingerprint:originalData.scoreFingerprint,anchorNoteId:id,includeHarmony:!!harmony})});
      if(controller.signal.aborted)return;
      if(result.score.baseFingerprint!==originalData.scoreFingerprint||result.score.downbeat?.noteId!==id)throw Error('Wrong score version');
      setVersions(previous=>[...previous,result]);setActiveVersion(versions.length);setPosition(result.score.downbeat.time);setPicking(false);setCandidateId(null);setSavedAnchor(id);
      try{localStorage.setItem(anchorStorage,JSON.stringify({noteId:id,time:result.score.downbeat.time}));}catch{/* The current session still retains every score version. */}
    }catch{if(!controller.signal.aborted)setAnchorMessage(text.rebarError);}
    finally{if(!controller.signal.aborted)setRebarBusy(false);}
  };
  const download=async(all=false)=>{
    if(exporting||rendering)return;setExporting(true);setExportProgress(0);setError('');
    const title=songTitle(data.sourceName),snapshot=[...pages.current],numbers=all?snapshot.map((_,i)=>i+1):[currentPage];
    const subtitle=`${data.bpm} BPM · ${data.meter} · ${data.key} · ${instruments.find(i=>i.id===melodyInstrument)![language]} / ${instruments.find(i=>i.id===chordInstrument)![language]}`;
    try{const files=[];for(const number of numbers){const image=await pagePng(snapshot[number-1],title,subtitle,number,snapshot.length);files.push({name:pageFileName(title,number),data:image});setExportProgress(files.length/numbers.length);await new Promise(r=>setTimeout(r,0));}
      if(all)saveBlob(zipFiles(files),`《${title.replace(/[<>:"/\\|?*]/g,'_')}》.zip`);else saveBlob(new Blob([files[0].data],{type:'image/png'}),files[0].name);
    }catch{setError(language==='zh'?'图片导出失败，请重试。':'Image export failed. Please retry.');}finally{setExporting(false);}
  };
  const changeInstrument=(staff:number,id:InstrumentId)=>{const at=player.current?.position()??position,resume=playing;pause();const right=staff===1?id:melodyInstrument,left=staff===2?id:chordInstrument;setMelodyInstrument(right);setChordInstrument(left);player.current?.setInstruments(right,left);if(resume)void play(at);};
  return <div className="gf-score" data-score-fingerprint={data.scoreFingerprint} data-rendering={rendering} data-playback-version={texture?.fingerprint||harmony?.fingerprint||data.scoreFingerprint} data-mapped-notes={mapped} data-current-measure={currentMeasure} data-current-page={currentPage} data-page-count={pageCount} data-playing={playing} data-picking={picking} data-active-version={activeVersion}>
    <div className="score-console">
      <div className="gf-transport"><button className="primary-button" disabled={rendering||loading||exporting} onClick={()=>playing?pause():void play()}>{loading?(language==='zh'?'正在加载音色…':'Loading instrument…'):playing?text.pause:text.play}</button><button onClick={()=>{pause();player.current?.stop();setPosition(0);}}>{text.stop}</button><span>{time(displayTime)} / {time(data.duration)}</span><label className="measure-quick">{text.measure}<select aria-label={text.measure} value={currentMeasure} disabled={rendering} onChange={e=>playMeasure(Number(e.target.value))}>{measures.map(bar=><option key={bar.number} value={bar.number}>{bar.pickup?text.pickup:bar.displayNumber??bar.number} · {time(bar.playStart)}</option>)}</select></label></div>
      <input className="gf-seek" aria-label={text.seek} type="range" min="0" max={data.duration} step=".01" value={Math.min(displayTime,data.duration)} onChange={e=>{onStartScore();pause();setPosition(Number(e.target.value));}} />
      <div className="staff-instruments">{([{staff:1,value:melodyInstrument,enabled:melodyEnabled},{staff:2,value:chordInstrument,enabled:chordsEnabled}] as const).map(item=><div key={item.staff} className={`instrument-strip ${item.staff===2?'bass-strip':''}`}><label className="voice-toggle"><input type="checkbox" checked={item.enabled} aria-label={item.staff===1?text.melody:text.chords} onChange={e=>{pause();if(item.staff===1)setMelodyEnabled(e.target.checked);else setChordsEnabled(e.target.checked);}}/><span>{language==='zh'?(item.staff===1?'高音 · 旋律':'低音 · 伴奏'):(item.staff===1?'Treble · melody':'Bass · accompaniment')}</span></label><select aria-label={language==='zh'?(item.staff===1?'高音谱表音色':'低音谱表音色'):(item.staff===1?'Treble instrument':'Bass instrument')} value={item.value} disabled={loading} onChange={e=>changeInstrument(item.staff,e.target.value as InstrumentId)}>{instruments.map(i=><option key={i.id} value={i.id}>{i[language]}</option>)}</select><small>{item.staff===1?'60%':'40%'}</small></div>)}</div>
    </div>
    <section className={`downbeat-tools ${picking?'selecting':''}`} aria-label={text.anchor}>
      <div className="gf-review-row"><button aria-pressed={picking} disabled={rendering||rebarBusy||textureBusy} onClick={()=>{pause();onStartScore();setPicking(!picking);setCandidateId(null);setAnchorMessage('');}}>{text.anchor}</button>{savedAnchor&&<button disabled={rebarBusy||rendering||textureBusy} onClick={()=>void rebuild(savedAnchor)}>{text.restore}</button>}
      {versions.length>1&&<label>{text.versions}<select aria-label={text.versions} disabled={rebarBusy||textureBusy} value={activeVersion} onChange={e=>{pause();onStartScore();setActiveVersion(Number(e.target.value));setPosition(0);setPicking(false);setCandidateId(null);setAnchorMessage('');}}>{versions.map((v,i)=><option key={i} value={i}>{i===0?text.original:`${text.rebuilt} ${i} · ${time(v.score.downbeat!.time)}`}</option>)}</select></label>}</div>
      {picking&&<><p>{text.anchorHint}</p>{candidate&&<p className="anchor-reference">{text.selected}: {time(candidate.start)}</p>}<div className="gf-review-row"><button disabled={!candidate||rebarBusy} onClick={()=>candidate&&void play(Math.max(0,candidate.start-2),Math.min(data.duration,candidate.start+3),true)}>{text.preview}</button><button className="primary-button" disabled={!candidate||rebarBusy||rendering} onClick={()=>void rebuild()}>{rebarBusy?text.rebuilding:text.rebuild}</button><button onClick={()=>{rebuildRequest.current?.abort();setRebarBusy(false);setPicking(false);setCandidateId(null);setAnchorMessage('');}}>{text.cancel}</button></div>{harmony&&<p>{text.regenerate}</p>}</>}
      {!picking&&data.downbeat&&<p>{text.selected}: {time(data.downbeat.time)}</p>}{anchorMessage&&<p role="status">{anchorMessage}</p>}
    </section>
    <details className="score-settings"><summary>{language==='zh'?'和弦与编配':'Chords & arrangement'}<span>{language==='zh'?(harmony?'调整伴奏':'生成伴奏'):(harmony?'Edit accompaniment':'Add accompaniment')}</span></summary><div className="settings-content">
    <BasicHarmony key={`${activeVersion}:${data.scoreFingerprint}`} data={data} jobId={jobId} language={language} value={harmony} onBeforeChange={()=>{pause();onStartScore();}} onChange={next=>{pause();setHarmony(next);}} onPlay={number=>playMeasure(number,true)} onPlayFrom={number=>playMeasure(number)} busy={rendering||loading||rebarBusy||picking||textureBusy}/>
    {harmony&&<Accompaniment key={textureKey} score={data} harmony={harmony} jobId={jobId} language={language} items={textureSet.items} active={textureSet.active} onBusyChange={setTextureBusy} onBeforeChange={()=>{pause();onStartScore();}} busy={rendering||loading||rebarBusy||picking} onGenerated={next=>{
      pause();if(next.harmonyFingerprint!==harmony.fingerprint)return;setTextureSets(previous=>{const current=previous[textureKey]||{items:[],active:-1};const existing=current.items.findIndex(v=>v.fingerprint===next.fingerprint);return {...previous,[textureKey]:existing>=0?{...current,active:existing}:{items:[...current.items,next],active:current.items.length}};});
    }} onSelect={index=>{pause();onStartScore();setTextureSets(previous=>({...previous,[textureKey]:{...textureSet,active:index}}));}}/>}
    </div></details>
    <div className="page-toolbar"><div className="page-navigation"><button aria-label={language==='zh'?'上一页':'Previous page'} disabled={currentPage<=1||rendering||playing||originalPlaying} onClick={()=>setCurrentPage(p=>p-1)}>←</button><label>{language==='zh'?'乐谱页码':'Score page'}<select aria-label={language==='zh'?'乐谱页码':'Score page'} value={currentPage} disabled={rendering||playing||originalPlaying} onChange={e=>setCurrentPage(Number(e.target.value))}>{Array.from({length:pageCount},(_,i)=><option key={i+1} value={i+1}>{i+1} / {pageCount}</option>)}</select></label><button aria-label={language==='zh'?'下一页':'Next page'} disabled={currentPage>=pageCount||rendering||playing||originalPlaying} onClick={()=>setCurrentPage(p=>p+1)}>→</button>{(playing||originalPlaying)&&<span role="status" className="follow-indicator">{language==='zh'?'跟随播放':'Following playback'}</span>}</div><div className="page-export"><button disabled={rendering||exporting||textureBusy||!pageCount} onClick={()=>void download(false)}>{language==='zh'?'下载此页 PNG':'Download page PNG'}</button><button className="primary-button" disabled={rendering||exporting||textureBusy||!pageCount} onClick={()=>void download(true)}>{exporting?`${language==='zh'?'正在导出':'Exporting'} ${Math.round(exportProgress*100)}%`:(language==='zh'?'导出全部页':'Export all pages')}</button></div></div>
    {error&&<p role="alert" className="score-inline-error">{error}</p>}
    <div ref={pageShell} className="staff-wrapper paged-staff" onClick={e=>{const target=e.target as Element;if(picking){if(!rebarBusy)selectAnchor(target);return;}const hit=[...(host.current?.querySelectorAll<SVGElement>('.measure-hitbox')||[])].find(rect=>{const box=rect.getBoundingClientRect();return e.clientX>=box.left&&e.clientX<=box.right&&e.clientY>=box.top&&e.clientY<=box.bottom;});const bar=target.closest<SVGElement>('[data-measure]')?.dataset.measure||hit?.dataset.measure;if(bar&&!rendering)playMeasure(Number(bar));}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){if(picking){e.preventDefault();if(!rebarBusy)selectAnchor(e.target as Element);return;}const bar=(e.target as Element).closest<SVGElement>('[data-measure]')?.dataset.measure;if(bar){e.preventDefault();playMeasure(Number(bar));}}}}>
      <div className="page-caption"><strong>{songTitle(data.sourceName)}</strong><span>Page {currentPage} / {pageCount||1}</span></div>{rendering&&<p role="status">{text.loading}</p>}<div ref={host} className="staff continuous-staff"/>
    </div><p className="sound-credits"><a href="/piano/LICENSE.txt" target="_blank" rel="noreferrer">Salamander Yamaha C5</a> · <a href="/instruments/LICENSE.md" target="_blank" rel="noreferrer">Tone.js instruments · CC BY 3.0</a></p>
  </div>;
}
