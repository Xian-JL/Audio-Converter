import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './lib/api';
import type { SourceKind, Job, ScoreData, MusicSettings as Settings } from './lib/api';
import { en, zh, translatedError } from './lib/i18n';
import MelodyScore from './MelodyScore';
import type { ScoreActions } from './MelodyScore';
import type { OpenProject, Workspace } from './lib/project';
import MusicSettings from './MusicSettings';
import StudioHeader from './StudioHeader';
import './App.css';

const MAX_SIZE = 100 * 1024 * 1024;
const json = {'Content-Type':'application/json'};
type ServiceState = 'checking' | 'ready' | 'offline' | 'incompatible';
type Panel = 'source' | 'score' | 'tools';
type Health = {scoreVersion:number; scoreReady?:boolean; ready:boolean; sourceReady?:Record<string,boolean>; missing?:string[]; desktop?:boolean};
const kinds: SourceKind[]=['vocal','piano','guzheng'];

export default function App() {
  const [language,setLanguage]=useState<'en'|'zh'>(()=> {
    try { const stored=localStorage.getItem('shengjian-language'); if(stored==='en'||stored==='zh')return stored; } catch { /* Preference storage is optional. */ }
    return navigator.language.startsWith('zh')?'zh':'en';
  });
  const chinese=language==='zh',text=chinese?zh:en;
  const tr=(a:string,b:string)=>chinese?a:b;
  const names=chinese?['人声演唱','钢琴独奏','古筝独奏（试验）']:['Singing voice','Solo piano','Solo guzheng (experimental)'];
  const [sourceKind,setSourceKind]=useState<SourceKind>('vocal');
  const [health,setHealth]=useState<Health>();
  const [service,setService]=useState<ServiceState>('checking');
  const [job,setJob]=useState<Job|null>(null);
  const [score,setScore]=useState<ScoreData|null>(null);
  const [workspace,setWorkspace]=useState<Workspace>();
  const [settings,setSettings]=useState<Settings|null>(null);
  const [scoreAttempt,setScoreAttempt]=useState(0);
  const [pending,setPending]=useState('');
  const [dragging,setDragging]=useState(false);
  const [importError,setImportError]=useState('');
  const [taskError,setTaskError]=useState('');
  const [scoreError,setScoreError]=useState('');
  const [correcting,setCorrecting]=useState(false);
  const [pollFailed,setPollFailed]=useState(false);
  const [pollAttempt,setPollAttempt]=useState(0);
  const [mediaUrl,setMediaUrl]=useState('');
  const [originalTime,setOriginalTime]=useState(0);
  const [originalPlaying,setOriginalPlaying]=useState(false);
  const [dirty,setDirty]=useState(false);
  const [notice,setNotice]=useState('');
  const [versionLabel,setVersionLabel]=useState('');
  const [panel,setPanel]=useState<Panel>('score');
  const [toolsHost,setToolsHost]=useState<HTMLDivElement|null>(null);
  const [guardError,setGuardError]=useState(false);
  const [guard,setGuard]=useState<(()=>void)|null>(null);
  const guardDialog=useRef<HTMLDialogElement>(null);
  const scoreActions=useRef<ScoreActions>(null);
  const scorePanel=useRef<HTMLElement>(null);
  const media=useRef<HTMLAudioElement>(null);
  const input=useRef<HTMLInputElement>(null),projectInput=useRef<HTMLInputElement>(null),linkInput=useRef<HTMLInputElement>(null);
  const client=useRef(crypto.randomUUID()), sequence=useRef(0);
  const healthRequest=useRef<AbortController|null>(null);
  const request=useRef<AbortController|null>(null);
  const busy=!!job&&!['ready','error'].includes(job.stage);
  const serviceReady=service==='ready'&&(health?.scoreReady??health?.ready);
  const canImport=!!serviceReady&&(health?.sourceReady?.[sourceKind]??(sourceKind==='vocal'&&health?.ready));
  const checkService=useCallback(async()=>{
    healthRequest.current?.abort();
    const controller=new AbortController();
    healthRequest.current=controller;
    setService('checking');
    try {
      const result=await api<Health>('/api/health',{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(8000)])});
      if(controller.signal.aborted)return;
      setHealth(result);
      setService(result.scoreVersion>=22?'ready':'incompatible');
    } catch { if(!controller.signal.aborted)setService('offline'); }
  },[]);
  useEffect(()=>{
    void checkService();
    const close=(event:PageTransitionEvent)=>{
      if(!event.persisted)navigator.sendBeacon('/api/reset',new Blob([JSON.stringify({client:client.current,sequence:++sequence.current})],{type:'application/json'}));
    };
    window.addEventListener('pagehide',close);
    return ()=>{window.removeEventListener('pagehide',close);healthRequest.current?.abort();request.current?.abort();};
  },[checkService]);
  useEffect(()=>{
    if(!dirty)return;
    const confirm=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};
    window.addEventListener('beforeunload',confirm);
    return ()=>window.removeEventListener('beforeunload',confirm);
  },[dirty]);
  useEffect(()=>{
    document.documentElement.lang=chinese?'zh-CN':'en';
    document.title=chinese?'声笺 · 音频转谱':'Shengjian · Audio to Score';
    try{localStorage.setItem('shengjian-language',language);}catch{/* Preference storage is optional. */}
  },[language,chinese]);
  useEffect(()=>{if(guard&&!guardDialog.current?.open)guardDialog.current?.showModal();},[guard]);
  useEffect(()=>()=>{if(mediaUrl)URL.revokeObjectURL(mediaUrl);},[mediaUrl]);

  useEffect(()=>{
    if(!job?.id||!busy)return;
    const controller=new AbortController();
    let timer:ReturnType<typeof setTimeout>, failures=0;
    const poll=async()=>{
      try {
        const next=await api<Job>(`/api/jobs/${job.id}`,{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(8000)])});
        if(controller.signal.aborted)return;
        failures=0;setPollFailed(false);setJob(old=>old?.id===next.id?next:old);
        if(!['ready','error'].includes(next.stage))timer=setTimeout(poll,800);
      } catch {
        if(controller.signal.aborted)return;
        setPollFailed(true);
        timer=setTimeout(poll,Math.min(12000,1000*2**Math.min(failures++,4)));
      }
    };
    void poll();
    return ()=>{controller.abort();clearTimeout(timer);};
  },[job?.id,busy,pollAttempt]);
  useEffect(()=>{
    if(!job?.analysisReady||!settings||score)return;
    const controller=new AbortController();
    const query=new URLSearchParams({bpm:String(settings.bpm),meter:settings.meter,key:settings.key});
    setCorrecting(true);setScoreError('');
    void api<ScoreData>(`/api/jobs/${job.id}/score?${query}`,{signal:controller.signal})
      .then(next=>{if(!controller.signal.aborted){setScore(next);setPanel('score');}})
      .catch(error=>{if(!controller.signal.aborted)setScoreError(error.message);})
      .finally(()=>{if(!controller.signal.aborted)setCorrecting(false);});
    return ()=>controller.abort();
  },[job?.id,job?.analysisReady,settings,score,scoreAttempt]);

  function protect(action:()=>void){
    if(dirty){setGuardError(false);setGuard(()=>action);}else action();
  }
  function resolveGuard(action:'save'|'discard'|'stay'){
    if(action==='save'&&!scoreActions.current?.save()){setGuardError(true);return;}
    guardDialog.current?.close();setGuard(null);
    if(action!=='stay')guard?.();
  }
  function begin(label:string){
    request.current?.abort();
    const controller=new AbortController();
    request.current=controller;
    setPending(label);setImportError('');setTaskError('');
    const id=++sequence.current;
    return {signal:controller.signal,current:()=>id===sequence.current&&!controller.signal.aborted,headers:{'X-Client-Session':client.current,'X-Upload-Sequence':String(id),'X-Keep-Current-Job':'1'}};
  }
  function accept(next:Job,opened?:OpenProject,file?:File){
    const previous=job?.id;
    media.current?.pause();
    setMediaUrl(file?.name.toLowerCase().endsWith('.mp3')?URL.createObjectURL(file):'');
    setJob(next);setScore(opened?.score??null);setWorkspace(opened?.workspace);
    setSettings(opened?{bpm:opened.score.bpm,meter:opened.score.meter,key:opened.score.key}:null);
    setOriginalTime(0);setOriginalPlaying(false);setDirty(false);setNotice('');setVersionLabel('');
    setPollFailed(false);setScoreError('');setCorrecting(false);setPanel('score');
    if(opened)setSourceKind(opened.score.sourceKind||'vocal');
    if(previous&&previous!==next.id)void api(`/api/jobs/${previous}`,{method:'DELETE',keepalive:true}).catch(()=>{});
  }
  function select(files:FileList|null){
    const file=files?.[0];
    if(!file||!canImport||pending)return;
    if(!/\.(mp3|flac)$/i.test(file.name)){setImportError('Only MP3 and FLAC files are supported.');return;}
    if(!file.size||file.size>MAX_SIZE){setImportError(file.size?'File exceeds the size limit (maximum 100 MB).':'The selected file is empty. Please choose another file.');return;}
    const multiple=(files?.length||0)>1;
    protect(()=>void (async()=>{
      const op=begin(tr('正在导入录音…','Importing recording…'));
      const form=new FormData();form.append('file',file);form.append('sourceKind',sourceKind);
      try{
        const next=await api<Job>('/api/jobs',{method:'POST',body:form,headers:op.headers,signal:op.signal});
        if(op.current()){
          accept(next,undefined,file);
          if(multiple)setNotice(tr(`一次处理一个文件，已选择 ${file.name}。`,`One file at a time. Selected ${file.name}.`));
        }else void api(`/api/jobs/${next.id}`,{method:'DELETE'}).catch(()=>{});
      }catch(error){if(op.current())setImportError((error as Error).message);}
      finally{if(op.current())setPending('');}
    })());
  }
  async function openProject(file?:File){
    if(!file||!serviceReady||pending)return;
    let body:string;
    try{
      if(file.size>32*1024*1024)throw Error(tr('工程文件不能超过 32 MB。','Project exceeds 32 MB.'));
      body=await file.text();JSON.parse(body);
    }catch(error){setImportError(error instanceof SyntaxError?tr('工程文件格式错误。','Invalid project JSON.'):(error as Error).message);return;}
    protect(()=>void (async()=>{
      const op=begin(tr('正在打开工程…','Opening project…'));
      try{
        const opened=await api<OpenProject>('/api/projects/open',{method:'POST',body,headers:{...op.headers,...json},signal:op.signal});
        if(op.current())accept(opened.job,opened);
        else void api(`/api/jobs/${opened.job.id}`,{method:'DELETE'}).catch(()=>{});
      }catch(error){if(op.current())setImportError((error as Error).message);}
      finally{if(op.current())setPending('');}
    })());
  }
  async function clear(){
    if(!job)return;
    const op=begin(tr('正在取消…','Cancelling…'));
    try{await api(`/api/jobs/${job.id}`,{method:'DELETE',signal:op.signal});if(op.current()){setJob(null);setScore(null);setWorkspace(undefined);setSettings(null);setCorrecting(false);setScoreError('');setMediaUrl('');setDirty(false);setNotice('');setPollFailed(false);}}
    catch{if(op.current())setTaskError(tr('无法确认取消，请重新检测连接后重试。','Cancellation could not be confirmed. Check the connection and retry.'));}
    finally{if(op.current())setPending('');}
  }
  async function retry(){
    if(!job||pending)return;
    const op=begin(tr('正在重启分析…','Restarting analysis…'));
    try{await api(`/api/jobs/${job.id}/retry`,{method:'POST',headers:json,body:'{"separationMode":"enhanced"}',signal:op.signal});if(op.current()){setPollFailed(false);setJob({...job,stage:'validating',progress:0,analysisReady:false,analysisError:undefined,error:undefined});}}
    catch(error){if(op.current())setTaskError((error as Error).message);}
    finally{if(op.current())setPending('');}
  }
  async function linkSource(file?:File){
    if(!file||!job||pending)return;
    const op=begin(tr('正在关联原录音…','Linking recording…'));
    const form=new FormData();form.append('file',file);
    try{const next=await api<Job>(`/api/jobs/${job.id}/source`,{method:'POST',body:form,signal:op.signal});if(op.current())setJob(next);}
    catch(error){if(op.current())setTaskError(`${translatedError((error as Error).message,text)} ${tr('请选择原文件','Select the original file')} ${job.name}`);}
    finally{if(op.current())setPending('');}
  }
  const applySettings=async(next:Settings)=>{
    if(!score){
      setSettings(next);setScoreAttempt(x=>x+1);return;
    }
    setScoreError('');setCorrecting(true);
    try{await scoreActions.current?.reconfigure(next);}
    catch(error){setScoreError((error as Error).message);}
    finally{setCorrecting(false);}
  };
  const playerUrl=mediaUrl||(job?.playbackReady?`/api/jobs/${job.id}/audio`:'');
  const vocalUrl=job?.vocalReady?`/api/jobs/${job.id}/vocals`:'';
  const stage=job?.stage||'validating';
  const indeterminate=stage==='instrumentLoading'||stage==='instrumentTranscription'&&job?.sourceKind==='piano';
  const stageLabel=stage==='instrumentLoading'?tr('正在加载乐器模型','Loading instrument model'):stage==='instrumentTranscription'?tr('正在识别演奏','Transcribing performance'):text[stage as keyof typeof en]||text.status;
  const status=service==='checking'?tr('正在检查本机服务','Checking local service'):service==='offline'?tr('本机服务连接失败','Local service unavailable'):service==='incompatible'?tr('本机服务版本不匹配','Incompatible local service'):tr('本机服务已连接','Local service connected');
  const changePanel=(next:Panel,focus=false)=>{
    setPanel(next);
    if(focus)requestAnimationFrame(()=>document.getElementById(`${next}-panel`)?.focus({preventScroll:true}));
  };
  const audio=<section className="recording-player" aria-label={tr('原录音','Original recording')}>
    {playerUrl?<><strong>{tr('原录音已关联','Original recording linked')}</strong><audio ref={media} controls preload="metadata" src={playerUrl} aria-label={text.player} onPlay={()=>setOriginalPlaying(true)} onPause={()=>setOriginalPlaying(false)} onEnded={()=>setOriginalPlaying(false)} onTimeUpdate={e=>setOriginalTime(e.currentTarget.currentTime)} onSeeked={e=>setOriginalTime(e.currentTarget.currentTime)} onError={()=>setTaskError(tr('原录音无法播放，请重试或重新关联。','Unable to play the recording. Retry or link it again.'))}/><a href={playerUrl+(mediaUrl?'':'?download=1')} download={job?.downloadName}>{text.download}</a></>:job?.restored?<><p>{tr('原录音未关联。你仍可编辑和试听谱面。','Original recording not linked. The score can still be edited and played.')}</p><button disabled={!!pending} onClick={()=>linkInput.current?.click()}>{tr('关联原音频','Link original audio')}</button></>:null}
  </section>;
  const parameters=job&&<><MusicSettings key={job.id} value={settings} text={text} onApply={next=>void applySettings(next)} busy={correcting||!!pending} /><div className="parameter-message">{score&&<p>{tr('改用新参数会创建分支并继承音符编辑。原分支保留首拍、和弦和器乐候选。','New parameters create a branch with your note edits. Downbeats, harmony and instrumentals stay on the previous branch.')}</p>}{!score&&busy&&settings&&<p role="status">{tr('分析完成后将按所填参数生成乐谱。','The score will use these settings when analysis finishes.')}</p>}{scoreError&&<p role="alert">{tr('未能生成新谱。可用相同参数重试。','Could not build the score. Retry with the same settings.')} {translatedError(scoreError,text)}</p>}</div></>;
  const sourceControls=<div className="source-controls" onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);select(e.dataTransfer.files);}} data-dragging={dragging}>
    <label className="recording-kind">{score?tr('下次导入类型','Next recording type'):tr('录音类型','Recording type')}<select aria-label={tr('录音类型','Recording type')} value={sourceKind} disabled={!!pending} onChange={e=>setSourceKind(e.target.value as SourceKind)}>{kinds.map((kind,index)=><option key={kind} value={kind}>{names[index]}</option>)}</select></label>
    {service==='ready'&&!canImport&&<p role="status">{health?.missing?.some(item=>item==='ffmpeg'||item==='ffprobe')?tr('缺少音频工具。','Audio tools are missing.'):tr('所选类型的识别资源缺失。','Recognition resources for this type are missing.')} {health?.desktop?tr('请重新解压完整桌面包。','Extract the complete desktop bundle again.'):tr(sourceKind==='vocal'?'请运行 Setup.cmd。':'请运行 SetupInstrument.cmd。',sourceKind==='vocal'?'Run Setup.cmd.':'Run SetupInstrument.cmd.')} {tr('已有工程仍可打开。','Saved projects can still open.')}</p>}
    <div className="source-actions project-actions"><button className="primary-button" disabled={!canImport||!!pending} onClick={()=>input.current?.click()}>{job?tr('替换录音','Replace recording'):text.choose}</button><button disabled={!serviceReady||!!pending} onClick={()=>projectInput.current?.click()}>{tr('打开工程','Open project')}</button>{job&&<button disabled={!!pending} onClick={()=>protect(()=>void clear())}>{busy?tr('取消分析','Cancel analysis'):text.clear}</button>}</div>
    <small>{text.support}</small>
  </div>;
  const issues=<>{pending&&<p role="status">{pending}</p>}{importError&&<p role="alert">{translatedError(importError,text)}</p>}</>;
  const transport=playerUrl||vocalUrl?{
    originalAvailable:!!playerUrl,vocalAvailable:!!vocalUrl,
    start:async(at:number,voice:boolean)=>{const element=media.current;if(!element)return;const url=voice?vocalUrl:playerUrl;if(element.getAttribute('src')!==url)element.src=url;element.currentTime=at;await element.play();},
    seek:(at:number)=>{if(media.current)media.current.currentTime=at;setOriginalTime(at);},
    pause:()=>media.current?.pause()
  }:undefined;
  return <div className="app-shell" data-scene={score?'workspace':job?'analysis':'idle'}>
    <StudioHeader language={language} onLanguage={setLanguage} status={status} ready={service==='ready'} title={text.title} />
    <input ref={input} className="file-input" type="file" accept=".mp3,.flac,audio/mpeg,audio/flac,audio/x-flac" aria-label={text.choose} onChange={e=>{select(e.target.files);e.target.value='';}} />
    <input ref={projectInput} className="file-input" type="file" accept=".acproject.json,.json,application/json" aria-label={tr('打开工程','Open project')} onChange={e=>{void openProject(e.target.files?.[0]);e.target.value='';}} />
    <input ref={linkInput} className="file-input" type="file" accept=".mp3,.flac" aria-label={tr('关联原音频','Link original audio')} onChange={e=>{void linkSource(e.target.files?.[0]);e.target.value='';}} />
    <main>
      {(service==='offline'||service==='incompatible'||service==='ready'&&!canImport)&&<div className="connection-note" role="status"><span>{status}{service==='incompatible'&&tr('。请退出旧版后重新打开声笺。','. Close the older service and reopen Shengjian.')}</span><button onClick={()=>void checkService()}>{tr('重新检测','Check again')}</button></div>}
      {score&&job?<><div className="project-heading"><div><h1 title={job.name}>{job.name}</h1><p>{names[kinds.indexOf(job.sourceKind||'vocal')]} · {versionLabel} · {dirty?tr('有未保存修改','Unsaved changes'):tr('无待保存修改','No unsaved changes')}</p></div><button className="primary-button" onClick={()=>scoreActions.current?.save()}>{tr('保存工程','Save project')}</button></div>
      {notice&&<p role="status" className="project-notice">{notice}</p>}
      <nav className="workspace-tabs" aria-label={tr('工作区','Workspace')} role="tablist" onKeyDown={e=>{
        const panels:Panel[]=['source','score','tools'];
        const index=panels.indexOf(panel);
        const next=e.key==='ArrowRight'?(index+1)%3:e.key==='ArrowLeft'?(index+2)%3:e.key==='Home'?0:e.key==='End'?2:-1;
        if(next>=0){e.preventDefault();changePanel(panels[next]);document.getElementById(`${panels[next]}-tab`)?.focus();}
      }}>{(['source','score','tools'] as const).map((name,index)=><button key={name} id={`${name}-tab`} role="tab" aria-selected={panel===name} tabIndex={panel===name?0:-1} aria-controls={`${name}-panel`} onClick={()=>changePanel(name)}>{(chinese?['音频','乐谱','工具']:['Audio','Score','Tools'])[index]}</button>)}</nav>
      <div className="studio-workspace" data-mobile-panel={panel}>
        <aside id="source-panel" className="source-panel" role="tabpanel" aria-labelledby="source-tab" tabIndex={-1}>
          {audio}{taskError&&<p role="alert">{taskError}</p>}{issues}
          <details className="source-options"><summary>{tr('乐谱参数','Score settings')}</summary>{parameters}</details>
          <details className="source-options"><summary>{tr('打开或替换','Open or replace')}</summary>{sourceControls}</details>
        </aside>
        <section id="score-panel" className="score-card card" ref={scorePanel} role="tabpanel" aria-labelledby="score-tab" tabIndex={-1}>
          <MelodyScore ref={scoreActions} key={job.id} jobId={job.id} data={score} language={language} initialWorkspace={workspace} toolsHost={toolsHost} onShowScore={()=>changePanel('score',true)} originalTime={originalTime} originalPlaying={originalPlaying} transport={transport} onStartScore={()=>media.current?.pause()} onDirty={setDirty} onSettings={setSettings} onVersionLabel={setVersionLabel} onSaved={setNotice}/>
        </section>
        <aside id="tools-panel" className="tools-panel card" role="tabpanel" aria-labelledby="tools-tab" tabIndex={-1}><div ref={setToolsHost}/></aside>
      </div></>:<div className="start-screen">
        <section className="start-card card"><h1>{job?.name||tr('从录音生成乐谱','Turn a recording into a score')}</h1>
          {!job&&sourceControls}{issues}
          {job&&<><div className="analysis-status">
          <strong role="status">{pollFailed?tr('连接中断，进度暂不可用','Connection interrupted. Progress is unavailable.'):job.error||job.analysisError?text.error:correcting?text.rendering:job.analysisReady?tr('分析完成，请确认乐谱参数','Analysis complete. Confirm score settings.'):stageLabel}</strong>
          {busy&&!pollFailed&&<progress max="1" value={indeterminate?undefined:job.progress} aria-label={stageLabel}/>}
          {pollFailed&&<button onClick={()=>setPollAttempt(n=>n+1)}>{tr('重新连接','Reconnect')}</button>}
          {(taskError||job.error||job.analysisError)&&<p role="alert">{translatedError(taskError||job.error||job.analysisError||'',text)}</p>}
          {(job.error||job.analysisError)&&<button disabled={!!pending} onClick={()=>void retry()}>{text.retry}</button>}
          <button disabled={!!pending} onClick={()=>void clear()}>{busy?tr('取消分析','Cancel analysis'):text.clear}</button></div>
          {audio}{parameters}<details className="source-options"><summary>{tr('打开或替换','Open or replace')}</summary>{sourceControls}</details></>}
          {!score&&notice&&<p role="status">{notice}</p>}
        </section>
      </div>}
    </main>
    <dialog aria-labelledby="discard-heading" ref={guardDialog} className="discard-dialog" onCancel={e=>{e.preventDefault();resolveGuard('stay');}}>
      <h2 id="discard-heading">{tr('当前工程有未保存修改','The project has unsaved changes')}</h2>
      <p>{tr('可以先下载工程文件，再继续当前操作。','Download the project before continuing if you want to keep your edits.')}</p>
      {guardError&&<p role="alert">{tr('工程文件生成失败，请继续编辑后重试。','Project file generation failed. Keep editing and retry.')}</p>}
      <div><button autoFocus onClick={()=>resolveGuard('stay')}>{tr('继续编辑','Keep editing')}</button><button onClick={()=>resolveGuard('discard')}>{tr('放弃修改','Discard changes')}</button><button className="primary-button" onClick={()=>resolveGuard('save')}>{tr('先保存','Save first')}</button></div>
    </dialog>
  </div>;
}
