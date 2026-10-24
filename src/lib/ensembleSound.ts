import {instrument,normalizationDb} from './instruments';
import type {InstrumentId} from './instruments';
import {playerSpread,timbres} from './ensemble';
import type {EnsembleLayer} from './ensemble';
import {sustained,SustainedSampler} from './sustain';
type Tone=typeof import('tone');
export type SampleBanks=Map<InstrumentId,Record<string,AudioBuffer>>;
export type EnsemblePlayer={synth:import('tone').Sampler|SustainedSampler;eq:import('tone').EQ3;pan:import('tone').Panner;layer:EnsembleLayer;cents:number;delay:number};
export function voiceLevelDb(staff:number,layer:EnsembleLayer,count:number,levels:number[]){
  return levels[staff]>0&&layer.gain>0?(staff===0?-5:-8)+instrument(layer.instrument).trim+normalizationDb(layer.instrument)+20*Math.log10(levels[staff]/100)+20*Math.log10(layer.gain/100)-10*Math.log10(Math.max(1,count)):-Infinity;
}
export function disposePlayers(players:EnsemblePlayer[]){for(const p of players){p.synth.dispose();p.eq.dispose();p.pan.dispose();}}
export function createStaffPlayers(tone:Tone,layers:EnsembleLayer[],banks:SampleBanks,staff:number,levels:number[],limiter:import('tone').Limiter){
  const players:EnsemblePlayer[]=[],count=layers.filter(l=>l.enabled&&l.gain>0).reduce((n,l)=>n+l.count,0);
  try{
    for(const layer of layers){
      if(!layer.enabled||layer.gain===0)continue;
      const sound=instrument(layer.instrument),profile=timbres.find(t=>t.id===layer.timbre)!;
      for(let member=0;member<layer.count;member++){
        const spread=playerSpread(layer.count,member),pan=new tone.Panner(Math.max(-1,Math.min(1,layer.pan+spread.pan))).connect(limiter);
        const eq=new tone.EQ3({low:profile.low,mid:profile.mid,high:profile.high,lowFrequency:250,highFrequency:2500}).connect(pan);
        const attack=sound.attack*profile.attack,release=(staff===1&&layer.instrument==='piano'?.25:sound.release)*profile.release;
        const synth=sustained.has(layer.instrument)?new SustainedSampler(tone,banks.get(layer.instrument)!,eq,attack,release,voiceLevelDb(staff,layer,count,levels)):new tone.Sampler({urls:banks.get(layer.instrument)!,attack,release,volume:voiceLevelDb(staff,layer,count,levels)}).connect(eq);
        players.push({synth,eq,pan,layer,cents:spread.cents,delay:spread.delay});
      }
    }
    return players;
  }catch(error){disposePlayers(players);throw error;}
}
export function triggerPlayers(tone:Tone,players:EnsemblePlayer[],pitches:number[],length:number,start:number,velocity:number){
  for(const player of players)player.synth.triggerAttackRelease(pitches.map(midi=>tone.Frequency(midi+player.cents/100,'midi').toFrequency()),length,start+player.delay,velocity);
}
