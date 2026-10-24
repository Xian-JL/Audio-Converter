import * as Tone from 'tone';
import {loadInstrument,normalizationDb} from '../src/lib/instruments';
import type {InstrumentId} from '../src/lib/instruments';
import {SustainedSampler} from '../src/lib/sustain';
import {ScorePlayback} from '../src/lib/playback';
import type {ScoreData} from '../src/lib/api';
import {instruments} from '../src/lib/instruments';
import {singleInstrument,timbres,legacyEnsembles,validateEnsembles,playerSpread} from '../src/lib/ensemble';
import type {Ensembles} from '../src/lib/ensemble';
import {createStaffPlayers,triggerPlayers,disposePlayers} from '../src/lib/ensembleSound';
import type {EnsemblePlayer,SampleBanks} from '../src/lib/ensembleSound';

export async function ensembleSounds(){
  const banks:SampleBanks=new Map(await Promise.all(instruments.map(async i=>[i.id,await loadInstrument(Tone,i.id)] as const))),results=[];
  const render=async(ensembles:Ensembles)=>{
    let groups:[EnsemblePlayer[],EnsemblePlayer[]]=[[],[]];
    const buffer=await Tone.Offline(()=>{const limiter=new Tone.Limiter(-1).toDestination();groups=[createStaffPlayers(Tone,ensembles[0],banks,0,[60,40],limiter),createStaffPlayers(Tone,ensembles[1],banks,1,[60,40],limiter)];triggerPlayers(Tone,groups[0],[60,64,67],.8,.05,.75);triggerPlayers(Tone,groups[1],[48,55],.8,.05,.65);},1.3,2,22050);
    const data=buffer.getChannelData(0),right=buffer.getChannelData(1);let peak=0,energy=0,fingerprint=0,stereo=0;
    for(let i=0;i<data.length;i++){peak=Math.max(peak,Math.abs(data[i]),Math.abs(right[i]));energy+=data[i]*data[i]+right[i]*right[i];fingerprint+=data[i]*(i%97);stereo+=Math.abs(data[i]-right[i]);}
    const counts=groups.map(g=>g.length),spread=groups[0].map(p=>({cents:p.cents,pan:p.pan.pan.value,delay:p.delay}));groups.forEach(disposePlayers);buffer.dispose();
    return {peak,rms:Math.sqrt(energy/(data.length*2)),fingerprint,stereo,counts,spread};
  };
  for(const instrument of instruments)for(const timbre of timbres){const ensembles=legacyEnsembles([instrument.id,'piano']);ensembles[0][0].timbre=timbre.id;ensembles[1][0].enabled=false;results.push({instrument:instrument.id,timbre:timbre.id,...await render(ensembles)});}
  const group:Ensembles=[[{...singleInstrument('violin'),count:4,timbre:'warm'}],[singleInstrument('piano'),singleInstrument('cello')]];
  const mixed=await render(group),solo=await render(legacyEnsembles(['violin','piano']));
  let rejected=0;for(const bad of [{...singleInstrument(),count:9},{...singleInstrument(),gain:NaN},{...singleInstrument(),timbre:'invalid'}]){try{validateEnsembles([[bad],[singleInstrument()]] as Ensembles);}catch{rejected++;}}
  return {results,mixed,solo,rejected,spread:playerSpread(4,3)};
}
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
