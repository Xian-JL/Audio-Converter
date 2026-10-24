import { instruments } from './instruments';
import type { InstrumentId } from './instruments';

/** Derived timbres over the credited sample banks, not additional recordings. */
export const timbres=[
  {id:'natural',en:'Natural',zh:'原声',low:0,mid:0,high:0,attack:1,release:1},
  {id:'warm',en:'Warm',zh:'温暖',low:2,mid:-1,high:-4,attack:1.15,release:1.1},
  {id:'bright',en:'Bright',zh:'明亮',low:-3,mid:1,high:3,attack:.8,release:.9},
  {id:'soft',en:'Soft',zh:'柔和',low:0,mid:-2,high:-8,attack:2,release:1.3},
] as const;
export type TimbreId=typeof timbres[number]['id'];
export interface EnsembleLayer {instrument:InstrumentId;timbre:TimbreId;count:number;gain:number;pan:number;enabled:boolean}
export type Ensembles=[EnsembleLayer[],EnsembleLayer[]];
export const MAX_LAYERS=8,MAX_PLAYERS=16;
export const singleInstrument=(instrument:InstrumentId='piano'):EnsembleLayer=>({instrument,timbre:'natural',count:1,gain:100,pan:0,enabled:true});
export function legacyEnsembles(instruments:[InstrumentId,InstrumentId]):Ensembles{return [[singleInstrument(instruments[0])],[singleInstrument(instruments[1])]];}
export function validateEnsembles(value:Ensembles):Ensembles{
  if(!Array.isArray(value)||value.length!==2)throw Error('Invalid ensembles');
  return value.map(staff=>{
    if(!Array.isArray(staff)||!staff.length||staff.length>MAX_LAYERS)throw Error('Invalid ensemble layers');
    let players=0;
    const layers=staff.map(layer=>{
      if(!layer||!instruments.some(i=>i.id===layer.instrument)||!timbres.some(t=>t.id===layer.timbre)||!Number.isInteger(layer.count)||layer.count<1||layer.count>8||!Number.isFinite(layer.gain)||layer.gain<0||layer.gain>100||!Number.isFinite(layer.pan)||layer.pan< -1||layer.pan>1||typeof layer.enabled!=='boolean')throw Error('Invalid ensemble layer');
      players+=layer.count;return {...layer};
    });
    if(players>MAX_PLAYERS)throw Error('Maximum 16 players per staff');return layers;
  }) as Ensembles;
}
export function ensembleSummary(layers:EnsembleLayer[],language:'en'|'zh'){
  return layers.filter(l=>l.enabled&&l.gain>0).map(l=>`${instruments.find(i=>i.id===l.instrument)![language]} ×${l.count} (${timbres.find(t=>t.id===l.timbre)![language]})`).join(' + ')||(language==='zh'?'静音':'Muted');
}
export function playerSpread(count:number,index:number){
  const fraction=count>1?(index/(count-1)*2-1):0;
  return {cents:fraction*4,pan:fraction*.22,delay:count>1?index/(count-1)*.006:0};
}
