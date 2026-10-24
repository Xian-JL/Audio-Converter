import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { OpenSheetMusicDisplay } from 'opensheetmusicdisplay';
import type { ScoreData, BasicHarmony as Harmony, AccompanimentData } from './lib/api';
import BasicHarmony from './BasicHarmony';
import Accompaniment from './Accompaniment';
import MelodyEditor from './MelodyEditor';
import EnsembleEditor from './EnsembleEditor';
import {legacyEnsembles,ensembleSummary} from './lib/ensemble';
import type {Ensembles,EnsembleLayer} from './lib/ensemble';
import {packProject} from './lib/project';
import type {Workspace,ScoreVersion,LoopSettings} from './lib/project';
import { api } from './lib/api';
import { ScorePlayback } from './lib/playback';

import { PAGE_WIDTH, pageFileName, pagePng, saveBlob, songTitle } from './lib/scorePages';
import { zipFiles } from './lib/zip';

const words={
  en:{title:'Score',play:'Play score',pause:'Pause',stop:'Stop',measure:'Measure / time',from:'Play from measure',seek:'Playback position',melody:'Melody',chords:'Chords',loading:'Drawing score…',error:'Unable to draw or play the score. Please retry.',anchor:'Locate measure downbeat',anchorHint:'Select a melody note onset that you know is beat 1.',selected:'Downbeat reference',rebuild:'Rebuild score',rebuilding:'Rebuilding…',cancel:'Cancel selection',preview:'Hear nearby melody',restore:'Restore last downbeat',versions:'Score version',original:'Original score',rebuilt:'Rebuilt',tie:'Select a note onset, not a tied continuation.',rebarError:'Unable to rebuild. Please select another note onset and retry.',pickup:'Pickup',regenerate:'Chords will be regenerated. The original score and its settings are retained.'},
  zh:{title:'乐谱',play:'播放乐谱',pause:'暂停',stop:'停止',measure:'小节 / 时间',from:'从此小节播放',seek:'播放位置',melody:'旋律',chords:'和弦',loading:'正在绘制乐谱…',error:'无法绘制或播放乐谱，请重试。',anchor:'定位小节第一拍',anchorHint:'请点选一个确定落在第一拍上的旋律起音。',selected:'第一拍参考',rebuild:'重构乐谱',rebuilding:'正在重构…',cancel:'取消定位',preview:'试听附近旋律',restore:'恢复上次定位',versions:'查看版本',original:'原始乐谱',rebuilt:'重构',tie:'这是延音片段，请选择音符的真实起音。',rebarError:'无法重构，请重新选择起音后重试。',pickup:'弱起',regenerate:'重构将重新配置和弦；原谱及其设置仍会保留。'},
};
const time=(value:number)=>{const ticks=Math.round(value*100);return `${Math.floor(ticks/6000)}:${(ticks%6000/100).toFixed(2).padStart(5,'0')}`;};

export default function MelodyScore({data:originalData,language,onStartScore,originalPlaying,originalTime,jobId,initialWorkspace,toolsHost,onShowScore}:{onShowScore:()=>void;toolsHost:HTMLDivElement|null;initialWorkspace?:Workspace;jobId:string;data:ScoreData;language:'en'|'zh';onStartScore:()=>void;originalPlaying:boolean;originalTime:number}){
  const text=words[language];
  const [versions,setVersions]=useState<ScoreVersion[]>(()=>initialWorkspace?.versions||[{score:originalData,harmony:null,kind:'original'}]);
  const [activeVersion,setActiveVersion]=useState(initialWorkspace?.activeVersion||0);
  const data=versions[activeVersion].score,harmony=versions[activeVersion].harmony;
  const setHarmony=(next:Harmony)=>setVersions(previous=>previous.map((v,i)=>i===activeVersion&&v.score.scoreFingerprint===next.sourceFingerprint?{...v,harmony:next}:v));
  const [picking,setPicking]=useState(false),[candidateId,setCandidateId]=useState<string|null>(null),[rebarBusy,setRebarBusy]=useState(false),[anchorMessage,setAnchorMessage]=useState('');
  const anchorStorage='score-downbeat-v1:'+originalData.scoreFingerprint;
  const [savedAnchor,setSavedAnchor]=useState<string|null>(()=>{try{const value=JSON.parse(localStorage.getItem(anchorStorage)||'{}').noteId;return originalData.notes?.some(n=>n.id===value)?value:null;}catch{return null;}});
  const rebuildRequest=useRef<AbortController|null>(null);
  useEffect(()=>()=>rebuildRequest.current?.abort(),[]);
  const candidate=data.notes?.find(n=>n.id===candidateId);
  const [melodyEnabled,setMelodyEnabled]=useState(initialWorkspace?.voices[0]??true),[chordsEnabled,setChordsEnabled]=useState(initialWorkspace?.voices[1]??true);
  const [ensembles,setEnsembles]=useState<Ensembles>(()=>initialWorkspace?.ensembles||legacyEnsembles(initialWorkspace?.instruments||['piano','piano']));
  const [scoreLayout,setScoreLayout]=useState<'compact'|'standard'>(initialWorkspace?.scoreLayout||'compact');
  const stage=useRef<HTMLDivElement>(null);
  const [currentPage,setCurrentPage]=useState(1),[pageCount,setPageCount]=useState(0),[exporting,setExporting]=useState(false),[exportProgress,setExportProgress]=useState(0);
  const exportCancelled=useRef(false);const [exportFirst,setExportFirst]=useState(1),[exportLast,setExportLast]=useState(1);
  const [levels,setLevels]=useState<[number,number]>(initialWorkspace?.levels||[60,40]);
  const pages=useRef<SVGSVGElement[]>([]),measurePages=useRef(new Map<number,number>()),pageShell=useRef<HTMLDivElement>(null);
  const [position,setPosition]=useState(initialWorkspace?.position||0),[playing,setPlaying]=useState(false),[loading,setLoading]=useState(false),[renderingState,setRendering]=useState(true),[renderedXml,setRenderedXml]=useState(''),[renderedLayout,setRenderedLayout]=useState(''),[error,setError]=useState('');
  const [mapped,setMapped]=useState(0);
  const host=useRef<HTMLDivElement>(null),player=useRef<ScorePlayback|null>(null),endAt=useRef(data.duration),requestId=useRef(0);
  const measureElements=useRef(new Map<number,SVGElement[]>()),highlighted=useRef(0);
  const textureKey=`${activeVersion}:${harmony?.fingerprint||''}`;
  const [textureSets,setTextureSets]=useState<Record<string,{items:AccompanimentData[];active:number}>>(initialWorkspace?.textureSets||{});
  const [editing,setEditing]=useState(false),[editId,setEditId]=useState<string|null>(null);
  const [loop,setLoop]=useState<LoopSettings>(initialWorkspace?.loop||{enabled:false,startMeasure:1,endMeasure:1});
  const [textureBusy,setTextureBusy]=useState(false);
  const textureSet=textureSets[textureKey]||{items:[],active:-1};
  const texture=textureSet.items[textureSet.active]||null;
  const displayedXml=texture?.xml||harmony?.xml||data.xml;
  const rendering=renderingState||renderedXml!==displayedXml||renderedLayout!==`${scoreLayout}:${language}`;
  const activeNotes=useMemo(()=>({...data,events:[...data.events,...(texture?.events||harmony?.events||[])].sort((a,b)=>a.start-b.start)}),[data,harmony,texture]);
  const measures=useMemo(()=>data.measures.map((bar,index)=>({...bar,playStart:harmony?.bars[index]?.playStart??bar.start,playEnd:harmony?.bars[index]?.playEnd??bar.end})),[data,harmony]);
  useEffect(()=>{setLoop(previous=>({...previous,startMeasure:Math.min(previous.startMeasure,measures.length),endMeasure:Math.min(previous.endMeasure,measures.length)}));},[measures.length]);
  const displayTime=originalPlaying?originalTime:position;
  const currentMeasure=measures.find(b=>displayTime>=b.playStart&&displayTime<b.playEnd)?.number||(displayTime<(measures[0]?.playStart||0)?1:measures.at(-1)?.number)||1;
  const pause=()=>{requestId.current++;const at=playing?(player.current?.position()??position):position;player.current?.pause();setPosition(at);setPlaying(false);setLoading(false);};
  useEffect(()=>{
    const instance=new ScorePlayback(activeNotes,setPosition,()=>{setPlaying(false);setPosition(endAt.current);});player.current=instance;
    return()=>{requestId.current++;instance.dispose();if(player.current===instance)player.current=null;};
  },[activeNotes]);
  useEffect(()=>{player.current?.setLevels(...levels);},[levels,activeNotes]);
  useEffect(()=>{player.current?.setEnsembles(ensembles);},[ensembles,activeNotes]);
  useEffect(()=>{if(originalPlaying)pause();},[originalPlaying]);
  useEffect(()=>{
    for(const element of measureElements.current.get(highlighted.current)||[])element.classList.remove('measure-current');
    for(const element of measureElements.current.get(currentMeasure)||[])element.classList.add('measure-current');
    highlighted.current=currentMeasure;
  },[currentMeasure,rendering]);
  useEffect(()=>{const page=measurePages.current.get(currentMeasure);if(page&&!rendering)setCurrentPage(page);},[currentMeasure,rendering]);
  useEffect(()=>{
    pages.current.forEach((svg,index)=>{const container=svg.parentElement;if(container)container.hidden=index+1!==currentPage;});

  },[currentPage,pageCount,rendering,playing,originalPlaying]);
  useEffect(()=>{
    let disposed=false,sheet:OpenSheetMusicDisplay|undefined,staging:HTMLDivElement|undefined;
    setRendering(true);setError('');
    const attach=(display:OpenSheetMusicDisplay,renderHost:HTMLDivElement)=>{
      measureElements.current.clear();measurePages.current.clear();const ids=new Set<string>();
      const svgs=[...renderHost.querySelectorAll<SVGSVGElement>('svg')];pages.current=svgs;
      svgs.forEach((svg,index)=>{const parent=svg.parentElement!;parent.classList.add('score-page');parent.dataset.page=String(index+1);parent.hidden=false;svg.dataset.page=String(index+1);if(!svg.hasAttribute('viewBox'))svg.setAttribute('viewBox',`0 0 ${parseFloat(svg.getAttribute('width')||'840')} ${parseFloat(svg.getAttribute('height')||'1188')}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',`${songTitle(data.sourceName)} · Page ${index+1}`);});
      const byTick=new Map((data.fragments||[]).map(f=>[f.startTick,f.noteId]));
      const cursor=display.cursor;cursor.reset();cursor.SkipInvisibleNotes=false;let safe=0;
      while(!cursor.Iterator.EndReached&&safe++<200000){
        const number=cursor.Iterator.CurrentMeasureIndex+1;
        for(const note of cursor.GNotesUnderCursor()){
          const svgNote=note as typeof note & {getSVGGElement():SVGGElement;getNoteheadSVGs():HTMLElement[]};
          const element=svgNote.getSVGGElement();if(!element||element.dataset.measure)continue;
          const staff=note.sourceNote.ParentVoiceEntry.ParentVoice.VoiceId===1?1:2;
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
      for(const label of renderHost.querySelectorAll('svg text')||[]){
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
      host.current.replaceChildren();const layout=document.createElement('div');layout.className='score-layout';layout.style.width=`${PAGE_WIDTH}px`;layout.style.maxWidth='none';staging=document.createElement('div');Object.assign(staging.style,{position:'fixed',left:'-100000px',top:'0',width:`${PAGE_WIDTH}px`,height:'1px',overflow:'hidden',visibility:'hidden',pointerEvents:'none'});staging.appendChild(layout);document.body.appendChild(staging);
      sheet=new OpenSheetMusicDisplay(layout,{autoResize:false,backend:'svg',autoBeam:true,drawTitle:false,drawComposer:false,drawPartNames:false,drawMeasureNumbers:false,drawMetronomeMarks:false,fillEmptyMeasuresWithWholeRest:0,pageFormat:'A4_P',followCursor:false});
      sheet.EngravingRules.PageBottomMargin=13;
      await sheet.load(displayedXml);if(disposed)return;sheet.Zoom=scoreLayout==='compact'?.8:1;sheet.render();attach(sheet,layout);host.current.replaceChildren(layout);staging.remove();staging=undefined;layout.style.width='100%';layout.style.maxWidth='100%';setRenderedLayout(`${scoreLayout}:${language}`);setRenderedXml(displayedXml);setRendering(false);
    }catch(cause){staging?.remove();console.error(cause);if(!disposed){setPageCount(0);setRenderedLayout(`${scoreLayout}:${language}`);setRenderedXml(displayedXml);setRendering(false);setError(text.error);}}})();
    return()=>{disposed=true;staging?.remove();sheet?.clear();measureElements.current.clear();measurePages.current.clear();pages.current=[];};
  },[displayedXml,language,scoreLayout]);
  useEffect(()=>{
    const container=stage.current;if(!container)return;
    let frame=0;
    const fit=()=>{
      const svg=pages.current[currentPage-1];if(!svg||!pageShell.current)return;
      const box=svg.viewBox.baseVal,ratio=box.width/box.height;
      const style=getComputedStyle(pageShell.current),caption=pageShell.current.querySelector('.page-caption')?.getBoundingClientRect().height||0;
      const horizontal=parseFloat(style.paddingLeft)+parseFloat(style.paddingRight)+parseFloat(style.borderLeftWidth)+parseFloat(style.borderRightWidth);
      const vertical=caption+parseFloat(style.paddingTop)+parseFloat(style.paddingBottom)+parseFloat(style.borderTopWidth)+parseFloat(style.borderBottomWidth);
      const buttons=[...container.querySelectorAll<HTMLElement>('.score-page-turn')].reduce((sum,button)=>sum+button.getBoundingClientRect().width,0),gap=parseFloat(getComputedStyle(container).columnGap)||0;
      const width=Math.max(12,Math.floor(Math.min(container.clientWidth-buttons-2*gap,(container.clientHeight-vertical)*ratio+horizontal)));
      container.style.setProperty('--page-display-width',`${width}px`);
    };
    const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(fit);};
    const observer=typeof ResizeObserver!=='undefined'?new ResizeObserver(schedule):null;observer?.observe(container);window.addEventListener('resize',schedule);schedule();
    return()=>{cancelAnimationFrame(frame);observer?.disconnect();window.removeEventListener('resize',schedule);};
  },[currentPage,rendering,renderedXml,language,scoreLayout]);
  const play=async(at=originalPlaying?originalTime:position,until=data.duration,solo=false,allowLoop=true)=>{
    const current=++requestId.current;onStartScore();setPlaying(false);setPosition(at);setLoading(true);setError('');endAt.current=until;const instance=player.current;
    try{instance?.setLoop(allowLoop&&!solo&&loop.enabled?{start:measures[loop.startMeasure-1].playStart,end:measures[loop.endMeasure-1].playEnd}:null);instance?.setVoices(solo||melodyEnabled,!solo&&chordsEnabled);const started=await instance?.play(at,until);if(current===requestId.current&&instance===player.current&&started)setPlaying(true);}
    catch{if(current===requestId.current)setError(language==='zh'?'无法加载或播放所选音色，请重试或切换乐器。':'Unable to load or play the selected instrument. Retry or choose another instrument.');}
    finally{if(current===requestId.current)setLoading(false);}
  };
  const playMeasure=(number:number,only=false)=>{const bar=measures.find(b=>b.number===number);if(bar){const outside=loop.enabled&&(number<loop.startMeasure||number>loop.endMeasure);if(outside)setLoop(previous=>({...previous,enabled:false}));setCurrentPage(measurePages.current.get(number)||1);void play(bar.playStart,only?bar.playEnd:data.duration,false,!only&&!outside);}};
  useEffect(()=>{for(const element of host.current?.querySelectorAll<SVGElement>('[data-anchor-onset="true"]')||[])element.classList.toggle('anchor-selected',picking&&element.dataset.noteId===candidateId);},[picking,candidateId,rendering]);
  const selectAnchor=(target:Element)=>{
    const note=target.closest<SVGElement>('[data-note-id]');
    if(!note||note.dataset.anchorOnset!=='true'){setAnchorMessage(text.tie);return;}
    setCandidateId(note.dataset.noteId!);setAnchorMessage('');
  };
  const rebuild=async(id=candidateId)=>{
    if(!id)return;pause();onStartScore();rebuildRequest.current?.abort();const controller=new AbortController();rebuildRequest.current=controller;setRebarBusy(true);setAnchorMessage('');
    try{
      const result=await api<{score:ScoreData;harmony:Harmony|null}>(`/api/jobs/${jobId}/rebar`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({bpm:data.bpm,meter:data.meter,key:data.key,editedNotes:data.editedNotes,identityNotesJson:data.identityNotesJson,sourceFingerprint:data.baseFingerprint||data.scoreFingerprint,anchorNoteId:id,includeHarmony:!!harmony})});
      if(controller.signal.aborted)return;
      if(result.score.baseFingerprint!==(data.baseFingerprint||data.scoreFingerprint)||result.score.downbeat?.noteId!==id)throw Error('Wrong score version');
      if(versions.length>=32)throw Error('Maximum 32 score versions');setVersions(previous=>[...previous,{...result,kind:'rebar'}]);setActiveVersion(versions.length);setPosition(result.score.downbeat.time);setPicking(false);setEditing(false);setCandidateId(null);setSavedAnchor(id);onShowScore();
      try{localStorage.setItem(anchorStorage,JSON.stringify({noteId:id,time:result.score.downbeat.time}));}catch{/* The current session still retains every score version. */}
    }catch{if(!controller.signal.aborted)setAnchorMessage(text.rebarError);}
    finally{if(!controller.signal.aborted)setRebarBusy(false);}
  };
  const switchVersion=(index:number)=>{pause();onStartScore();setActiveVersion(index);setPosition(0);setCandidateId(null);setPicking(false);setEditId(null);};
  const revision=(next:ScoreVersion,id:string|null)=>{
    if(versions.length>=32){setError(language==='zh'?'最多保留 32 个版本，请另存工程。':'Maximum 32 versions. Save a project before starting a new one.');return;}
    pause();setVersions(v=>[...v,next]);setActiveVersion(versions.length);setEditId(id);setPosition(next.score.notes?.find(n=>n.id===id)?.start||0);onShowScore();
  };
  const saveProject=()=>{
    try{const snapshot:Workspace={versions,activeVersion,textureSets,instruments:[ensembles[0][0].instrument,ensembles[1][0].instrument],voices:[melodyEnabled,chordsEnabled],position:playing?(player.current?.position()??position):position,loop,levels,ensembles,scoreLayout};const blob=new Blob([JSON.stringify(packProject(originalData,snapshot))],{type:'application/json'});if(blob.size>32*1024*1024)throw Error();saveBlob(blob,`${songTitle(originalData.sourceName).replace(/[<>:"/\\|?*]/g,'_')}.acproject.json`);}
    catch{setError(language==='zh'?'工程保存失败或超过 32 MB 限制，请减少版本后重试。':'Unable to save project (maximum 32 MB).');}
  };
  const changeLoop=(next:LoopSettings)=>{pause();setLoop(next);};
  useEffect(()=>{for(const element of host.current?.querySelectorAll<SVGElement>('[data-note-id]')||[])element.classList.toggle('note-edit-selected',editing&&element.dataset.noteId===editId);},[editing,editId,rendering]);
  const download=async(all=false,range=false,print=false)=>{
    if(exporting||rendering)return;setExporting(true);exportCancelled.current=false;setExportProgress(0);setError('');
    const popup=print?window.open('','_blank'):null;if(print&&!popup){setExporting(false);setError(language==='zh'?'请允许打印窗口打开后重试。':'Allow the print window and retry.');return;}
    if(popup){popup.document.title=songTitle(data.sourceName);popup.document.body.textContent=language==='zh'?'正在准备打印页面…':'Preparing print pages…';}
    const title=songTitle(data.sourceName),snapshot=[...pages.current],numbers=all?snapshot.map((_,i)=>i+1):range?Array.from({length:Math.max(0,Math.min(snapshot.length,exportLast)-exportFirst+1)},(_,i)=>exportFirst+i):[currentPage];
    const subtitle=`${data.bpm} BPM · ${data.meter} · ${data.key}`;
    const instrumentation:[string,string]=[ensembleSummary(ensembles[0],language),ensembleSummary(ensembles[1],language)];
    try{const files=[];for(const number of numbers){if(exportCancelled.current){popup?.close();return;}const image=await pagePng(snapshot[number-1],title,subtitle,number,snapshot.length,instrumentation);files.push({name:pageFileName(title,number),data:image});setExportProgress(files.length/numbers.length);await new Promise(r=>setTimeout(r,0));}
      if(exportCancelled.current){popup?.close();return;}
      if(popup){const style=popup.document.createElement('style');style.textContent='@page{size:A4 portrait;margin:0}body{margin:0;background:white}img{width:210mm;height:297mm;display:block;break-after:page;page-break-after:always}img:last-child{break-after:auto;page-break-after:auto}@media screen{img{margin:12px auto;box-shadow:0 0 2px #888}button{position:fixed;top:12px;left:12px}}@media print{button{display:none}}';popup.document.head.append(style);popup.document.body.replaceChildren();const button=popup.document.createElement('button');button.textContent=language==='zh'?'打印 / 保存为 PDF':'Print / Save as PDF';button.onclick=()=>popup.print();popup.document.body.append(button);for(const file of files){const image=popup.document.createElement('img');image.alt=file.name;const blobUrl=URL.createObjectURL(new Blob([file.data],{type:'image/png'}));image.src=blobUrl;popup.document.body.append(image);await image.decode();URL.revokeObjectURL(blobUrl);}popup.focus();popup.print();}
      else if(all||range)saveBlob(zipFiles(files),`《${title.replace(/[<>:"/\\|?*]/g,'_')}》.zip`);else saveBlob(new Blob([files[0].data],{type:'image/png'}),files[0].name);
    }catch{popup?.close();setError(language==='zh'?'图片导出失败，请重试。':'Image export failed. Please retry.');}finally{setExporting(false);}
  };
  const changeEnsemble=(staff:number,layers:EnsembleLayer[])=>{
    const at=playing?(player.current?.position()??position):position,resume=playing;pause();setPosition(at);
    const next:Ensembles=staff===0?[layers,ensembles[1]]:[ensembles[0],layers];setEnsembles(next);player.current?.setEnsembles(next);if(resume)void play(at);
  };
  const controls=<div className="score-tools" data-picking={picking} data-editing={editing}>
    <details className="navigation-settings"><summary>{language==='zh'?'谱面与播放':'Page & playback'}</summary><div className="navigation-content">
<span className="score-settings-summary">{data.bpm} BPM · {data.meter} · {language==='zh'?data.key.replace(/ major$/,' 大调').replace(/ minor$/,' 小调'):data.key}</span>
    <div className="page-toolbar"><div className="page-navigation"><label>{language==='zh'?'乐谱页码':'Score page'}<select aria-label={language==='zh'?'乐谱页码':'Score page'} value={currentPage} disabled={rendering||playing||originalPlaying} onChange={e=>{setCurrentPage(Number(e.target.value));onShowScore();}}>{Array.from({length:pageCount},(_,i)=><option key={i+1} value={i+1}>{i+1} / {pageCount}</option>)}</select></label><label>{language==='zh'?'页面密度':'Page density'}<select aria-label={language==='zh'?'页面密度':'Page density'} value={scoreLayout} disabled={rendering||exporting} onChange={e=>{pause();onStartScore();setScoreLayout(e.target.value as typeof scoreLayout);onShowScore();}}><option value="compact">{language==='zh'?'紧凑':'Compact'}</option><option value="standard">{language==='zh'?'标准':'Standard'}</option></select></label>{(playing||originalPlaying)&&<span role="status" className="follow-indicator">{language==='zh'?'跟随播放':'Following playback'}</span>}</div></div>
<label className="measure-quick">{text.measure}<select aria-label={text.measure} value={currentMeasure} disabled={rendering} onChange={e=>{onShowScore();playMeasure(Number(e.target.value));}}>{measures.map(bar=><option key={bar.number} value={bar.number}>{bar.pickup?text.pickup:bar.displayNumber??bar.number} · {time(bar.playStart)}</option>)}</select></label>
      <div className="loop-controls"><label className="voice-toggle"><input type="checkbox" aria-label={language==='zh'?'循环播放':'Loop playback'} checked={loop.enabled} onChange={e=>changeLoop({...loop,enabled:e.target.checked})}/>{language==='zh'?'循环播放':'Loop playback'}</label><label>{language==='zh'?'起始小节':'First measure'}<select aria-label={language==='zh'?'循环起始小节':'Loop first measure'} value={loop.startMeasure} onChange={e=>{const startMeasure=Number(e.target.value);changeLoop({...loop,startMeasure,endMeasure:Math.max(startMeasure,loop.endMeasure)});}}>{measures.map(b=><option key={b.number} value={b.number}>{b.pickup?text.pickup:b.displayNumber??b.number}</option>)}</select></label><span aria-hidden="true">—</span><label>{language==='zh'?'结束小节':'Last measure'}<select aria-label={language==='zh'?'循环结束小节':'Loop last measure'} value={loop.endMeasure} onChange={e=>changeLoop({...loop,endMeasure:Number(e.target.value)})}>{measures.filter(b=>b.number>=loop.startMeasure).map(b=><option key={b.number} value={b.number}>{b.pickup?text.pickup:b.displayNumber??b.number}</option>)}</select></label></div>    </div></details>
    <section className="tools-instruments" aria-label={language==='zh'?'乐器与音量':'Instruments & levels'}><h3>{language==='zh'?'乐器与音量':'Instruments & levels'}</h3>
      <EnsembleEditor value={ensembles} language={language} enabled={[melodyEnabled,chordsEnabled]} levels={levels} busy={loading} onChange={changeEnsemble} onEnabled={(staff,value)=>{pause();if(staff===0)setMelodyEnabled(value);else setChordsEnabled(value);}} onLevels={setLevels}/>

    </section>
    <div className="workspace-actions"><span className="score-note-count">{data.noteCount} {language==='zh'?'个旋律音符':'melody notes'}</span><button className="primary-button" disabled={rebarBusy||textureBusy} onClick={saveProject}>{language==='zh'?'保存工程':'Save project'}</button><button aria-pressed={editing} disabled={rendering||rebarBusy||textureBusy} onClick={()=>{pause();onStartScore();setPicking(false);if(!editing)onShowScore();setEditing(!editing);setEditId(data.notes?.find(n=>n.start>=position)?.id||data.notes?.[0]?.id||null);}}>{language==='zh'?(editing?'结束编辑':'编辑旋律'):(editing?'Finish editing':'Edit melody')}</button><button disabled={activeVersion===0||rebarBusy||textureBusy} onClick={()=>switchVersion(activeVersion-1)}>{language==='zh'?'撤销':'Undo'}</button><button disabled={activeVersion>=versions.length-1||rebarBusy||textureBusy} onClick={()=>switchVersion(activeVersion+1)}>{language==='zh'?'重做':'Redo'}</button></div>
    {editing&&<MelodyEditor key={activeVersion} score={data} jobId={jobId} language={language} selectedId={editId} onRevision={revision} onBeforeChange={()=>{pause();onStartScore();}} busy={rendering||rebarBusy||textureBusy||versions.length>=32} onPreview={(start,end)=>void play(start,end,true)}/>}
    <section className={`downbeat-tools ${picking?'selecting':''}`} aria-label={text.anchor}>
      <div className="gf-review-row"><button aria-pressed={picking} disabled={rendering||rebarBusy||textureBusy} onClick={()=>{pause();onStartScore();setEditing(false);if(!picking)onShowScore();setPicking(!picking);setCandidateId(null);setAnchorMessage('');}}>{text.anchor}</button>{savedAnchor&&<button disabled={rebarBusy||rendering||textureBusy} onClick={()=>void rebuild(savedAnchor)}>{text.restore}</button>}
      {versions.length>1&&<label>{text.versions}<select aria-label={text.versions} disabled={rebarBusy||textureBusy} value={activeVersion} onChange={e=>{pause();onStartScore();setActiveVersion(Number(e.target.value));setPosition(0);setEditing(false);setEditId(null);setPicking(false);setCandidateId(null);setAnchorMessage('');}}>{versions.map((v,i)=><option key={i} value={i}>{i===0?text.original:`${v.kind==='edit'?(language==='zh'?'修订':'Edited'):text.rebuilt} ${i}${v.score.downbeat?' · '+time(v.score.downbeat.time):''}`}</option>)}</select></label>}</div>
      {picking&&<><p>{text.anchorHint}</p>{candidate&&<p className="anchor-reference">{text.selected}: {time(candidate.start)}</p>}<div className="gf-review-row"><button disabled={!candidate||rebarBusy} onClick={()=>candidate&&void play(Math.max(0,candidate.start-2),Math.min(data.duration,candidate.start+3),true)}>{text.preview}</button><button className="primary-button" disabled={!candidate||rebarBusy||rendering} onClick={()=>void rebuild()}>{rebarBusy?text.rebuilding:text.rebuild}</button><button onClick={()=>{rebuildRequest.current?.abort();setRebarBusy(false);setPicking(false);setCandidateId(null);setAnchorMessage('');}}>{text.cancel}</button></div>{harmony&&<p>{text.regenerate}</p>}</>}
      {!picking&&data.downbeat&&<p>{text.selected}: {time(data.downbeat.time)}</p>}{anchorMessage&&<p role="status">{anchorMessage}</p>}
    </section>
    <details className="score-settings"><summary>{language==='zh'?'和弦与编配':'Chords & arrangement'}<span>{language==='zh'?(harmony?'调整伴奏':'生成伴奏'):(harmony?'Edit accompaniment':'Add accompaniment')}</span></summary><div className="settings-content">
    <BasicHarmony key={`${activeVersion}:${data.scoreFingerprint}`} data={data} jobId={jobId} language={language} value={harmony} onBeforeChange={()=>{pause();onStartScore();}} onChange={next=>{pause();setHarmony(next);}} onPlay={number=>playMeasure(number,true)} onPlayFrom={number=>playMeasure(number)} busy={rendering||loading||rebarBusy||picking||editing||textureBusy}/>
    {harmony&&<Accompaniment key={textureKey} score={data} harmony={harmony} jobId={jobId} language={language} items={textureSet.items} active={textureSet.active} onBusyChange={setTextureBusy} onBeforeChange={()=>{pause();onStartScore();}} busy={rendering||loading||rebarBusy||picking||editing} onGenerated={next=>{
      pause();if(next.harmonyFingerprint!==harmony.fingerprint)return;setTextureSets(previous=>{const current=previous[textureKey]||{items:[],active:-1};const existing=current.items.findIndex(v=>v.fingerprint===next.fingerprint);return {...previous,[textureKey]:existing>=0?{...current,active:existing}:{items:[...current.items.slice(-11),next],active:Math.min(current.items.length,11)}};});
    }} onSelect={index=>{pause();onStartScore();setTextureSets(previous=>({...previous,[textureKey]:{...textureSet,active:index}}));}}/>}
    </div></details>
    <section className="tools-export" aria-label={language==='zh'?'乐谱导出':'Score export'}><h3>{language==='zh'?'乐谱导出':'Score export'}</h3>
<div className="page-export"><button disabled={rendering||exporting||textureBusy||!pageCount} onClick={()=>void download(false)}>{language==='zh'?'下载此页 PNG':'Download page PNG'}</button><button className="primary-button" disabled={rendering||exporting||textureBusy||!pageCount} onClick={()=>void download(true)}>{exporting?`${language==='zh'?'正在导出':'Exporting'} ${Math.round(exportProgress*100)}%`:(language==='zh'?'导出全部页':'Export all pages')}</button></div>
    <details className="export-options"><summary>{language==='zh'?'打印与导出选项':'Print & export options'}</summary><div className="export-range"><label>{language==='zh'?'从页':'From page'}<input type="number" min="1" max={pageCount} value={Math.min(exportFirst,pageCount||1)} onChange={e=>{const first=Math.max(1,Math.min(pageCount,Number(e.target.value)||1));setExportFirst(first);setExportLast(last=>Math.max(first,last));}}/></label><label>{language==='zh'?'到页':'To page'}<input type="number" min={exportFirst} max={pageCount} value={Math.min(exportLast,pageCount||1)} onChange={e=>setExportLast(Math.max(exportFirst,Math.min(pageCount,Number(e.target.value)||1)))}/></label><button disabled={rendering||exporting||!pageCount||exportLast<exportFirst} onClick={()=>void download(false,true)}>{language==='zh'?'导出页码范围':'Export page range'}</button><button disabled={rendering||exporting||!pageCount} onClick={()=>{pause();void download(true,false,true);}}>{language==='zh'?'打印 / 保存为 PDF':'Print / Save as PDF'}</button></div></details>
    {exporting&&<div className="export-progress" role="status"><progress max="1" value={exportProgress}/><button onClick={()=>{exportCancelled.current=true;}}>{language==='zh'?'取消导出':'Cancel export'}</button></div>}
    </section>
    <p className="sound-credits"><a href="/piano/LICENSE.txt" target="_blank" rel="noreferrer">Salamander Yamaha C5</a> · <a href="/instruments/LICENSE.md" target="_blank" rel="noreferrer">Tone.js instruments · CC BY 3.0</a></p>
  </div>;
  return <div className="gf-score" data-score-fingerprint={data.scoreFingerprint} data-rendering={rendering} data-playback-version={texture?.fingerprint||harmony?.fingerprint||data.scoreFingerprint} data-mapped-notes={mapped} data-current-measure={currentMeasure} data-current-page={currentPage} data-page-count={pageCount} data-looping={loop.enabled} data-editing={editing} data-playing={playing} data-picking={picking} data-active-version={activeVersion} data-score-layout={scoreLayout}>
    <div className="score-console">
      <div className="gf-transport"><button className="primary-button" disabled={rendering||loading||exporting} onClick={()=>playing?pause():void play()}>{loading?(language==='zh'?'正在加载音色…':'Loading instrument…'):playing?text.pause:text.play}</button><button onClick={()=>{pause();player.current?.stop();setPosition(0);}}>{text.stop}</button><span className="transport-time">{time(displayTime)} / {time(data.duration)}</span><input className="gf-seek" aria-label={text.seek} type="range" min="0" max={data.duration} step=".01" value={Math.min(displayTime,data.duration)} onChange={e=>{onStartScore();pause();setPosition(Number(e.target.value));}} />{loop.enabled&&<span className="loop-badge" role="status">{language==='zh'?'循环中':'Loop'}</span>}</div>



    </div>
    {error&&<p role="alert" className="score-inline-error">{error}</p>}
    <div ref={stage} className="score-page-stage"><button className="score-page-turn previous-page" aria-label={language==='zh'?'上一页':'Previous page'} disabled={currentPage<=1||rendering||playing||originalPlaying} onClick={()=>setCurrentPage(p=>p-1)}><svg aria-hidden="true" viewBox="0 0 24 36" width="20" height="30"><path d="M19 5 6 18l13 13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg></button>
    <div ref={pageShell} className="staff-wrapper paged-staff" onClick={e=>{const target=e.target as Element;if(editing){const id=target.closest<SVGElement>('[data-note-id]')?.dataset.noteId;if(id)setEditId(id);return;}if(picking){if(!rebarBusy)selectAnchor(target);return;}const hit=[...(host.current?.querySelectorAll<SVGElement>('.measure-hitbox')||[])].find(rect=>{const box=rect.getBoundingClientRect();return e.clientX>=box.left&&e.clientX<=box.right&&e.clientY>=box.top&&e.clientY<=box.bottom;});const bar=target.closest<SVGElement>('[data-measure]')?.dataset.measure||hit?.dataset.measure;if(bar&&!rendering)playMeasure(Number(bar));}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){if(editing){e.preventDefault();const id=(e.target as Element).closest<SVGElement>('[data-note-id]')?.dataset.noteId;if(id)setEditId(id);return;}if(picking){e.preventDefault();if(!rebarBusy)selectAnchor(e.target as Element);return;}const bar=(e.target as Element).closest<SVGElement>('[data-measure]')?.dataset.measure;if(bar){e.preventDefault();playMeasure(Number(bar));}}}}>
      <div className="page-caption"><strong title={songTitle(data.sourceName)}>{songTitle(data.sourceName)}</strong><span>Page {currentPage} / {pageCount||1}</span></div>{rendering&&<p role="status">{text.loading}</p>}<div ref={host} className="staff continuous-staff"/>
    </div><button className="score-page-turn next-page" aria-label={language==='zh'?'下一页':'Next page'} disabled={currentPage>=pageCount||rendering||playing||originalPlaying} onClick={()=>setCurrentPage(p=>p+1)}><svg aria-hidden="true" viewBox="0 0 24 36" width="20" height="30"><path d="m5 5 13 13L5 31" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg></button></div>
    {toolsHost&&createPortal(controls,toolsHost)}
  </div>;
}
