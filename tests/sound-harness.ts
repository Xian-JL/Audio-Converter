import * as Tone from 'tone';
import {loadInstrument,normalizationDb} from '../src/lib/instruments';
import type {InstrumentId} from '../src/lib/instruments';
import {SustainedSampler} from '../src/lib/sustain';
import {ScorePlayback} from '../src/lib/playback';
import type {ScoreData} from '../src/lib/api';
export async function longNotes(){
  const result=[];
  for(const id of ['violin','cello','flute','clarinet','bassoon','trumpet','trombone','organ'] as InstrumentId[]){
    let sampler:SustainedSampler|undefined;
    const buffer=await Tone.Offline(async()=>{const bank=await loadInstrument(Tone,id),limiter=new Tone.Limiter(-1).toDestination();sampler=new SustainedSampler(Tone,bank,limiter,.025,.15,-14);sampler.triggerAttackRelease(['C4'],5.5,.1,.7);},6,1,44100);
    const data=buffer.getChannelData(0);const rms=(a:number,b:number)=>{let sum=0;for(let i=Math.round(a*44100);i<Math.round(b*44100);i++)sum+=data[i]*data[i];return Math.sqrt(sum/((b-a)*44100));};
    result.push({id,atOneSecond:rms(1,1.5),atFiveSeconds:rms(5,5.5),afterRelease:rms(5.85,5.99),normalizationDb:normalizationDb(id),peak:data.reduce((max,n)=>Math.max(max,Math.abs(n)),0)});sampler?.dispose();
  }
  return result;
}
export async function stress(){
  const events=Array.from({length:20},(_,i)=>({start:i*.06,end:i*.06+.04,pitches:[60+i%4],staff:i%2?1:2}));
  const ticks:number[]=[];const player=new ScorePlayback({duration:1.2,events} as ScoreData,p=>ticks.push(p),()=>{});player.setLoop({start:0,end:1.2});player.setInstruments('flute','cello');await player.play();
  Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));
  const started=performance.now();while(performance.now()-started<800){Math.sqrt(performance.now());}
  await new Promise(r=>setTimeout(r,1800));const at=player.position();player.pause();const stopped=player.position();await new Promise(r=>setTimeout(r,50));const paused=player.position();player.dispose();delete (document as unknown as {hidden?:boolean}).hidden;
  return {ticks:ticks.length,at,stopped,paused};
}
