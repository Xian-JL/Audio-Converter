import {instruments} from './lib/instruments';
import {MAX_LAYERS,MAX_PLAYERS,singleInstrument,timbres} from './lib/ensemble';
import type {Ensembles,EnsembleLayer,TimbreId} from './lib/ensemble';
import type {InstrumentId} from './lib/instruments';

export default function EnsembleEditor({value,language,enabled,levels,busy,onChange,onEnabled,onLevels}:{value:Ensembles;language:'en'|'zh';enabled:[boolean,boolean];levels:[number,number];busy:boolean;onChange:(staff:number,layers:EnsembleLayer[])=>void;onEnabled:(staff:number,value:boolean)=>void;onLevels:(value:[number,number])=>void}){
  const zh=language==='zh';
  return <div className="staff-instruments ensemble-editor">{value.map((layers,staff)=>{
    const name=zh?(staff===0?'高音':'低音'):(staff===0?'Treble':'Bass'),total=layers.reduce((n,l)=>n+l.count,0);
    const update=(index:number,patch:Partial<EnsembleLayer>)=>onChange(staff,layers.map((l,i)=>i===index?{...l,...patch}:l));
    return <section key={staff} className={`instrument-strip ensemble-staff ${staff===1?'bass-strip':''}`} data-staff={staff+1} aria-label={zh?`${name}声部合奏`:`${name} ensemble`}>
      <div className="ensemble-staff-heading"><label className="voice-toggle"><input type="checkbox" checked={enabled[staff]} aria-label={zh?(staff===0?'旋律':'和弦'):(staff===0?'Melody':'Chords')} onChange={e=>onEnabled(staff,e.target.checked)}/><span>{zh?(staff===0?'高音 · 旋律':'低音 · 伴奏'):(staff===0?'Treble · melody':'Bass · accompaniment')}</span></label><span>{total}{zh?' 件':' players'}</span></div>
      <label className="staff-level"><span>{zh?'声部音量':'Staff volume'}</span><input aria-label={zh?(staff===0?'旋律音量':'伴奏音量'):(staff===0?'Melody volume':'Accompaniment volume')} type="range" min="0" max="100" value={levels[staff]} onChange={e=>onLevels(staff===0?[Number(e.target.value),levels[1]]:[levels[0],Number(e.target.value)])}/><small>{levels[staff]}%</small></label>
      {layers.map((layer,index)=><div className="ensemble-layer" key={index} data-layer={index+1}>
        <div className="ensemble-layer-top"><label className="voice-toggle"><input type="checkbox" checked={layer.enabled} aria-label={zh?`启用${name}乐器 ${index+1}`:`Enable ${name} instrument ${index+1}`} disabled={busy} onChange={e=>update(index,{enabled:e.target.checked})}/><span>{zh?'乐器':'Instrument'} {index+1}</span></label><button className="quiet-button" disabled={busy||layers.length===1} aria-label={zh?`移除${name}乐器 ${index+1}`:`Remove ${name} instrument ${index+1}`} onClick={()=>onChange(staff,layers.filter((_,i)=>i!==index))}>×</button></div>
        <label>{zh?'乐器':'Instrument'}<select aria-label={index===0?(zh?`${name}谱表音色`:`${name} instrument`):(zh?`${name}乐器 ${index+1}`:`${name} instrument ${index+1}`)} value={layer.instrument} disabled={busy} onChange={e=>update(index,{instrument:e.target.value as InstrumentId})}>{instruments.map(i=><option key={i.id} value={i.id}>{i[language]}</option>)}</select></label>
        <div className="ensemble-layer-options"><label>{zh?'音色':'Timbre'}<select aria-label={zh?`${name}音色风格 ${index+1}`:`${name} timbre ${index+1}`} value={layer.timbre} disabled={busy} onChange={e=>update(index,{timbre:e.target.value as TimbreId})}>{timbres.map(t=><option key={t.id} value={t.id}>{t[language]}</option>)}</select></label><label>{zh?'数量':'Players'}<input aria-label={zh?`${name}数量 ${index+1}`:`${name} players ${index+1}`} type="number" min="1" max={Math.min(8,MAX_PLAYERS-total+layer.count)} step="1" value={layer.count} disabled={busy} onChange={e=>update(index,{count:Math.max(1,Math.min(8,MAX_PLAYERS-total+layer.count,Math.round(Number(e.target.value)||1)))})}/></label></div>
        <details className="layer-mix"><summary>{zh?'独立混音':'Layer mix'}</summary><label>{zh?'音量':'Volume'}<input aria-label={zh?`${name}乐器音量 ${index+1}`:`${name} layer volume ${index+1}`} type="range" min="0" max="100" value={layer.gain} disabled={busy} onChange={e=>update(index,{gain:Number(e.target.value)})}/><small>{layer.gain}%</small></label><label>{zh?'声像：左 / 右':'Pan: left / right'}<input aria-label={zh?`${name}声像 ${index+1}`:`${name} pan ${index+1}`} type="range" min="-1" max="1" step=".05" value={layer.pan} disabled={busy} onChange={e=>update(index,{pan:Number(e.target.value)})}/></label></details>
      </div>)}
      <button className="add-instrument" disabled={busy||layers.length>=MAX_LAYERS||total>=MAX_PLAYERS} onClick={()=>onChange(staff,[...layers,singleInstrument(staff===0?'violin':'cello')])}>{zh?`＋ 添加${name}乐器`:`＋ Add ${name} instrument`}</button>
    </section>;
  })}</div>;
}
