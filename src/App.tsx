import { useEffect, useRef, useState } from 'react';
import { api, clock } from './lib/api';
import type { Job, ScoreData, MusicSettings as Settings } from './lib/api';
import { en, zh, translatedError } from './lib/i18n';
import MelodyScore from './MelodyScore';
import type { OpenProject, Workspace } from './lib/project';
import MusicSettings from './MusicSettings';
import './App.css';
const MAX_SIZE = 100 * 1024 * 1024;
const stages = ['validating', 'converting', 'decoding', 'separating', 'melody', 'beats', 'engraving'];
function Wave({ small = false }: { small?: boolean }) {
  return <svg viewBox="0 0 48 48" width={small ? 30 : 48} height={small ? 30 : 48} fill="none" aria-hidden="true"><path d="M9 20v8m8-16v24m7-31v38m7-29v20m8-13v6" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" /></svg>;
}
export default function App() {
  const [language, setLanguage] = useState<'en' | 'zh'>('en');
  const text = language === 'en' ? en : zh;
  const [serviceReady, setServiceReady] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [selected, setSelected] = useState<{ name: string; size: number; format: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playbackError, setPlaybackError] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [directUrl, setDirectUrl] = useState<string | null>(null);
  const [score, setScore] = useState<ScoreData | null>(null);
  const [toolsHost,setToolsHost]=useState<HTMLDivElement|null>(null);
  const [workspace,setWorkspace]=useState<Workspace|null>(null);
  const projectInput=useRef<HTMLInputElement>(null),sourceInput=useRef<HTMLInputElement>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const separationMode = 'enhanced';
  const vocalPreview = useRef<HTMLAudioElement>(null);
  const [originalTime, setOriginalTime] = useState(0);
  const [originalPlaying, setOriginalPlaying] = useState(false);
  const audioElement = useRef<HTMLAudioElement>(null);
  const [correcting, setCorrecting] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const sequence = useRef(0);
  const client = useRef(crypto.randomUUID());
  const request = useRef<AbortController | null>(null);
  const urlRef = useRef<string | null>(null);
  useEffect(() => {
    document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN';
    document.title = language === 'en' ? 'Local Audio · Converter & Vocal Score' : '本地音频 · 转换与演唱乐谱';
  }, [language]);
  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        await api('/api/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client: client.current, sequence: 0 }) });
        const health = await api<{ ready: boolean; engine?: string; scoreVersion?:number }>('/api/health');
        if (active) { setServiceReady(health.ready && health.engine === 'game' && Number(health.scoreVersion||0)>=15); if (!health.ready) setError('Local audio tools are missing. Run setup.ps1 first.'); else if (health.engine !== 'game'||Number(health.scoreVersion||0)<15) setError('Restart the local service.'); }
      } catch { if (active) setError('Unable to reach the local service.'); }
    })();
    const unload = () => navigator.sendBeacon('/api/reset', new Blob([JSON.stringify({ client: client.current, sequence: ++sequence.current, closing: true })], { type: 'application/json' }));
    window.addEventListener('pagehide', unload);
    return () => { active = false; window.removeEventListener('pagehide', unload); request.current?.abort(); if (urlRef.current) URL.revokeObjectURL(urlRef.current); };
  }, []);
  useEffect(() => {
    if (!job?.id || job.stage === 'ready' || job.stage === 'error') return;
    const id = job.id;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const updated = await api<Job>(`/api/jobs/${id}`);
        if (!active) return;
        setJob(updated);
        if (updated.stage !== 'ready' && updated.stage !== 'error') timer = setTimeout(() => void poll(), 800);
      } catch (cause) { if (active) setError(cause instanceof Error ? cause.message : 'Unable to reach the local service.'); }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [job?.id, job?.stage === 'ready', job?.stage === 'error']);
  useEffect(() => {
    if (!job?.analysisReady || !settings || (job.restored&&workspace)) return;
    const controller = new AbortController();
    setCorrecting(true); setScore(null);
    const query = new URLSearchParams({ bpm: String(settings.bpm), meter: settings.meter, key: settings.key });
    void api<ScoreData>(`/api/jobs/${job.id}/score?${query}`, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) { setScore(data); setError(null); }
    }).catch(cause => { if (!controller.signal.aborted) setError(String(cause.message)); })
      .finally(() => { if (!controller.signal.aborted) setCorrecting(false); });
    return () => controller.abort();
  }, [job?.id, job?.analysisReady, job?.separationMode, settings, workspace]);
  const reset = async () => {
    const current = ++sequence.current;
    request.current?.abort();
    clearLocal();
    if (input.current) input.current.value = '';
    try { await api('/api/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client: client.current, sequence: current }) }); }
    catch (cause) { if (current === sequence.current) setError(cause instanceof Error ? cause.message : 'Unable to reach the local service.'); }
    return current;
  };
  const clearLocal = () => {
    for (const previousAudio of [audioElement.current, vocalPreview.current]) {
      if (previousAudio) { previousAudio.pause(); previousAudio.removeAttribute('src'); previousAudio.load(); }
    }
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
    setDirectUrl(null); setJob(null); setScore(null); setSelected(null); setError(null); setPlaybackError(false); setUploading(false); setCorrecting(false); setOriginalPlaying(false); setOriginalTime(0);
    setWorkspace(null);
  };
  const select = async (file?: File) => {
    if (!file || !serviceReady) return;
    const extension = file.name.split('.').pop()?.toLowerCase();
    if (!['mp3', 'flac'].includes(extension || '')) { setError('Only MP3 and FLAC files are supported.'); return; }
    if (!file.size) { setError('The selected file is empty. Please choose another file.'); return; }
    if (file.size > MAX_SIZE) { setError('File exceeds the size limit (maximum 100 MB).'); return; }
    const current=++sequence.current;request.current?.abort();setError(null);setUploading(true);
    const controller = new AbortController(); request.current = controller;
    const body = new FormData(); body.append('file', file); body.append('separationMode', separationMode);
    try {
      const result = await api<{ id: string }>('/api/jobs', { method: 'POST', body, signal: controller.signal, headers: { 'X-Client-Session': client.current, 'X-Upload-Sequence': String(current) } });
      if (current !== sequence.current) return;
      const task = await api<Job>(`/api/jobs/${result.id}`, { signal: controller.signal });
      if (current === sequence.current) {clearLocal();setSelected({name:file.name,size:file.size,format:extension!.toUpperCase()});if(extension==='mp3'){const url=URL.createObjectURL(file);urlRef.current=url;setDirectUrl(url);}setJob(task);}
    } catch (cause) { if (current === sequence.current && !controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Unable to reach the local service.'); }
    finally { if (current === sequence.current) setUploading(false); }
  };
  const openProject=async(file?:File)=>{
    if(!file||!serviceReady)return;
    if(file.size>32*1024*1024){setError(language==='zh'?'工程文件不能超过 32 MB。':'Project exceeds the size limit (32 MB).');return;}
    const current=++sequence.current;request.current?.abort();const controller=new AbortController();request.current=controller;setUploading(true);setError(null);
    try{
      const body=await file.text();JSON.parse(body);
      const result=await api<OpenProject>('/api/projects/open',{method:'POST',body,signal:controller.signal,headers:{'Content-Type':'application/json','X-Client-Session':client.current,'X-Upload-Sequence':String(current)}});
      if(current!==sequence.current)return;clearLocal();setJob(result.job);setSettings({bpm:result.score.bpm,meter:result.score.meter,key:result.score.key});setWorkspace(result.workspace);setScore(result.score);setSelected({name:result.job.name,size:0,format:'PROJECT'});
    }catch(cause){if(current===sequence.current&&!controller.signal.aborted)setError(cause instanceof SyntaxError?(language==='zh'?'工程文件格式错误。':'Invalid project JSON.'):String((cause as Error).message));}
    finally{if(current===sequence.current)setUploading(false);}
  };
  const linkSource=async(file?:File)=>{
    if(!file||!job)return;const id=job.id;const current=sequence.current;
    if(file.size>MAX_SIZE||!file.size){setError(language==='zh'?'请选择不超过 100 MB 的原音频。':'Choose the original audio (maximum 100 MB).');return;}
    const body=new FormData();body.append('file',file);setUploading(true);setError(null);
    try{const next=await api<Job>(`/api/jobs/${id}/source`,{method:'POST',body});if(current===sequence.current){setJob(next);setSelected({name:next.name,size:file.size,format:file.name.split('.').pop()!.toUpperCase()});}}
    catch(cause){if(current===sequence.current)setError(String((cause as Error).message));}
    finally{if(current===sequence.current)setUploading(false);}
  };
  const retry = async () => {
    if (!job) return;
    const current = sequence.current;
    const preview = vocalPreview.current;
    if (preview) { preview.pause(); preview.removeAttribute('src'); preview.load(); }
    audioElement.current?.pause();
    setScore(null);
    try { await api(`/api/jobs/${job.id}/retry`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ separationMode }) }); if (current === sequence.current) { setScore(null); setError(null); setJob({ ...job, stage: 'validating', progress: 0, analysisReady: false, analysisError: undefined, error: undefined }); } }
    catch (cause) { if (current === sequence.current) setError(cause instanceof Error ? cause.message : 'Unable to reach the local service.'); }
  };
  const applySettings = (next: Settings) => { if(settings&&next.bpm===settings.bpm&&next.meter===settings.meter&&next.key===settings.key)return;setWorkspace(null); vocalPreview.current?.pause(); audioElement.current?.pause(); setScore(null); setSettings(next); };
  const syncPlaying = () => setOriginalPlaying(Boolean((audioElement.current && !audioElement.current.paused) || (vocalPreview.current && !vocalPreview.current.paused)));
  const stopBothAudio = () => { audioElement.current?.pause(); vocalPreview.current?.pause(); };
  const playerUrl = job?.error ? null : directUrl || (job?.playbackReady ? `/api/jobs/${job.id}/audio` : null);
  const message = error || job?.error || job?.analysisError || (playbackError ? 'Unable to play this audio file.' : null);
  const stage = uploading ? 'localUpload' : job?.stage || 'validating';
  const stageLabel = text[stage as keyof typeof en] || text.status;
  const busy = uploading || !!job && !['ready', 'error'].includes(job.stage);
  return <div className="app-shell">
    <header className="site-header"><a className="brand" href="#" aria-label={text.title}><span className="brand-icon"><Wave small /></span><span>{text.title}<small>{text.subtitle}</small></span></a><div className="header-controls"><span className="privacy"><span aria-hidden="true">◉</span>{text.privacy}</span><div className="language" aria-label="Language / 语言"><button className={language === 'en' ? 'active' : ''} aria-pressed={language === 'en'} onClick={() => setLanguage('en')}>EN</button><button className={language === 'zh' ? 'active' : ''} aria-pressed={language === 'zh'} onClick={() => setLanguage('zh')}>中文</button></div></div></header>
    <main><div className="intro"><div><span className="eyebrow">LOCAL AUDIO <span className="release-tag">v0.3.1</span></span><h1>{text.intro}</h1><p>{text.description}</p></div><div className="intro-mark" aria-hidden="true"><span>♩</span><i /><i /><i /><i /><i /></div></div>
      <div className="studio-workspace"><aside className="source-panel" aria-label={language==='zh'?'音频与乐谱参数':'Audio and musical settings'}>
      <MusicSettings value={settings} text={text} onApply={applySettings} busy={correcting} />
      <input ref={projectInput} className="file-input" type="file" accept=".acproject.json,.json,application/json" aria-label={language==='zh'?'打开工程':'Open project'} onChange={e=>{void openProject(e.target.files?.[0]);e.target.value='';}}/>
      <input ref={sourceInput} className="file-input" type="file" accept=".mp3,.flac" aria-label={language==='zh'?'关联原音频':'Link original audio'} onChange={e=>{void linkSource(e.target.files?.[0]);e.target.value='';}}/>
      <div className="project-actions"><button disabled={!serviceReady||uploading} onClick={()=>projectInput.current?.click()}>{language==='zh'?'打开工程':'Open project'}</button>{job?.restored&&<button disabled={uploading} onClick={()=>sourceInput.current?.click()}>{language==='zh'?'关联原音频':'Link original audio'}</button>}</div>
      <input ref={input} type="file" accept=".mp3,.flac,audio/mpeg,audio/flac,audio/x-flac" className="file-input" aria-label={text.choose} onChange={event => {void select(event.target.files?.[0]);event.target.value='';}} />
      <div className={`drop-zone ${dragging ? 'dragging' : ''} ${!serviceReady ? 'unavailable' : ''}`} role="button" tabIndex={serviceReady ? 0 : -1} aria-label={`${text.choose}. ${text.support}`} aria-disabled={!serviceReady} onClick={() => serviceReady && input.current?.click()} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (serviceReady) input.current?.click(); } }} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); void select(event.dataTransfer.files[0]); }}>
        <div className="upload-icon"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 16V4m-4 4 4-4 4 4M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg></div>
        <h2>{text.upload}</h2><p>{text.dropHint}</p><span className="choose-button">{text.choose}<span aria-hidden="true">↗</span></span><small>{text.support}</small>
      </div>
      {selected && <section className="file-card card" aria-label={text.file}><span className="file-icon"><Wave small /></span><div className="file-title"><span className="label">{text.file}</span><h2 title={selected.name}>{selected.name}</h2></div><dl><div><dt>{text.format}</dt><dd>{selected.format==='PROJECT'?(language==='zh'?'工程':'Project'):job?.info?.format || selected.format}</dd></div><div><dt>{text.size}</dt><dd>{selected.size?`${(selected.size/1048576).toFixed(2)} MB`:'—'}</dd></div><div><dt>{text.duration}</dt><dd>{job?.info ? clock(job.info.duration) : '—'}</dd></div></dl></section>}
      {(busy || message || job?.stage === 'ready') && <section className={`status-card ${message ? 'has-error' : ''}`} aria-live="polite" aria-atomic="true"><div className="status-row"><span className={`status-dot ${busy ? 'pulsing' : ''}`} /><strong>{message ? text.error : stageLabel}</strong>{busy && !uploading && <span>{Math.round((job?.progress || 0) * 100)}%</span>}</div>{busy && <progress max="1" value={uploading?undefined:job?.progress || 0} aria-label={stageLabel} />}{message && <p role="alert">{translatedError(message, text)}</p>}{message && <div className="error-actions">{error&&score&&<button onClick={()=>setError(null)}>{language==='zh'?'继续当前乐谱':'Keep current score'}</button>}{job?.analysisError && <button onClick={() => void retry()}>{text.retry}</button>}<button onClick={() => input.current?.click()}>{text.replace}</button></div>}{busy && <div className="stage-track" aria-hidden="true">{stages.map(s => <span key={s} className={s === stage ? 'current' : ''} />)}</div>}</section>}
      <section className="player-card card"><div className="card-heading"><div><span className="label">01 / AUDIO</span><h2>{text.player}</h2></div><span className={`badge ${playerUrl ? 'success' : ''}`}>{playerUrl ? 'MP3' : '—'}</span></div>{playerUrl ? <><audio ref={audioElement} onTimeUpdate={event => setOriginalTime(event.currentTarget.currentTime)} onSeeked={event => setOriginalTime(event.currentTarget.currentTime)} onPlay={() => { setPlaybackError(false); vocalPreview.current?.pause(); syncPlaying(); }} onPause={syncPlaying} onEnded={syncPlaying} key={playerUrl} controls preload="metadata" src={playerUrl} aria-label={text.player} onError={event => { if (event.currentTarget === audioElement.current && event.currentTarget.getAttribute('src') && event.currentTarget.error?.code !== 1) setPlaybackError(true); }} /><div className="actions"><a className="primary-button" href={job?.playbackReady ? `/api/jobs/${job.id}/audio?download=1` : playerUrl} download={job?.downloadName || selected?.name}>{text.download}<span aria-hidden="true">↓</span></a><button onClick={() => input.current?.click()}>{text.replace}</button><button className="quiet-button" onClick={() => void reset()}>{text.clear}</button></div></> : <div className="player-placeholder"><Wave small /><div><strong>{text.waiting}</strong><p>{text.waitingHint}</p></div>{selected && <button onClick={() => void reset()}>{text.clear}</button>}</div>}</section>
      </aside><section className="score-card card"><div className="card-heading"><div><span className="label">02 / SCORE</span><h2>{text.score}</h2></div><span className="score-heading-mark" aria-hidden="true">𝄞</span></div>{score ? <><div className="score-toolbar"><div className="score-summary">{language==='zh'?'全曲乐谱':'Full score'}</div><span className="score-settings-summary">{score.bpm} BPM · {score.meter} · {score.key.replace(/ major$/, ` ${text.major}`).replace(/ minor$/, ` ${text.minor}`)}</span></div><MelodyScore toolsHost={toolsHost} initialWorkspace={workspace||undefined} key={`${job!.id}:${score.scoreFingerprint}`} jobId={job!.id} data={score} language={language} originalTime={originalTime} originalPlaying={originalPlaying} onStartScore={stopBothAudio} /></> : <div className="score-placeholder"><div className="staff-decoration" aria-hidden="true"><span>♪</span></div><strong>{job?.analysisReady && !settings ? text.settingsRequired : busy || correcting ? text.scoreWaiting : text.scoreIdle}</strong><p>{text.scoreSub}</p></div>}</section><aside className="tools-panel card" aria-label={language==='zh'?'乐谱工具':'Score tools'}><div className="card-heading"><div><span className="label">03 / TOOLS</span><h2>{language==='zh'?'演奏与编配':'Performance & arrangement'}</h2></div></div>{!score&&<p className="tools-placeholder">{language==='zh'?'生成乐谱后，在这里选择乐器、定位第一拍与编配和弦。':'Once your score is ready, choose instruments, locate the downbeat and arrange chords here.'}</p>}<div ref={setToolsHost} className="score-tools-host"/></aside></div>
    </main><footer><span className="footer-dot" />{text.footer}</footer>
  </div>;
}




