import { loadPiano } from './piano';
type ToneModule=typeof import('tone');
export const instruments=[
  {id:'piano',en:'Grand piano',zh:'三角钢琴',attack:.003,release:.3,trim:0},
  {id:'guitar-nylon',en:'Nylon guitar',zh:'尼龙吉他',attack:.003,release:.18,trim:0},
  {id:'violin',en:'Violin',zh:'小提琴',attack:.025,release:.16,trim:-5},
  {id:'cello',en:'Cello',zh:'大提琴',attack:.025,release:.18,trim:-5},
  {id:'flute',en:'Flute',zh:'长笛',attack:.02,release:.14,trim:-5},
  {id:'clarinet',en:'Clarinet',zh:'单簧管',attack:.015,release:.14,trim:-5},
  {id:'bassoon',en:'Bassoon',zh:'巴松',attack:.02,release:.15,trim:-5},
  {id:'trumpet',en:'Trumpet',zh:'小号',attack:.015,release:.12,trim:-8},
  {id:'trombone',en:'Trombone',zh:'长号',attack:.025,release:.15,trim:-8},
  {id:'harp',en:'Harp',zh:'竖琴',attack:.003,release:.3,trim:0},
  {id:'organ',en:'Organ',zh:'管风琴',attack:.01,release:.13,trim:-7},
  {id:'xylophone',en:'Xylophone',zh:'木琴',attack:.003,release:.12,trim:-2},
] as const;
export type InstrumentId=typeof instruments[number]['id'];
const banks=new Map<string,Promise<Record<string,AudioBuffer>>>();
let catalog:Promise<{instruments:Record<string,{samples:Record<string,string>}>}>|null=null;
export function instrument(id:InstrumentId){return instruments.find(item=>item.id===id)!;}
export function loadInstrument(tone:ToneModule,id:InstrumentId){
  if(id==='piano')return loadPiano(tone);
  if(!banks.has(id)){
    catalog??=fetch('/instruments/manifest.json').then(r=>{if(!r.ok)throw Error('Instrument resources missing');return r.json();}).catch(e=>{catalog=null;throw e;});
    const bank=catalog.then(async data=>{
      const samples=data.instruments[id]?.samples;if(!samples)throw Error('Unknown instrument');
      return Object.fromEntries(await Promise.all(Object.entries(samples).map(async([note,name])=>{
        const holder=new tone.ToneAudioBuffer();try{await holder.load(`/instruments/${id}/${name}`);const value=holder.get();if(!value)throw Error('Sample decoding failed');return [note,value];}finally{holder.dispose();}
      })));
    }).catch(e=>{banks.delete(id);throw e;});banks.set(id,bank);
  }
  return banks.get(id)!;
}
