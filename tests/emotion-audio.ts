import * as Tone from 'tone';
import {loadInstrument} from '../src/lib/instruments';
import {legacyEnsembles} from '../src/lib/ensemble';
import {createStaffPlayers,triggerPlayers,disposePlayers} from '../src/lib/ensembleSound';
import type {EnsemblePlayer} from '../src/lib/ensembleSound';
import type {ScoreData} from '../src/lib/api';

export async function render(events:ScoreData['events'],left:number,right:number){
  const bank=await loadInstrument(Tone,'piano'),banks=new Map([['piano' as const,bank]]),ensembles=legacyEnsembles(['piano','piano']);
  let groups:[EnsemblePlayer[],EnsemblePlayer[]]=[[],[]];
  const buffer=await Tone.Offline(()=>{
    const limiter=new Tone.Limiter(-1).toDestination();groups=[createStaffPlayers(Tone,ensembles[0],banks,0,[60,40],limiter),createStaffPlayers(Tone,ensembles[1],banks,1,[60,40],limiter)];
    for(const e of events){const start=Math.max(left,e.start),end=Math.min(right,e.end);if(end>start)triggerPlayers(Tone,groups[e.staff===1?0:1],e.pitches,end-start,start-left+.05,e.velocity??.85);}
  },right-left+.7,2,22050);
  const channels=[buffer.getChannelData(0),buffer.getChannelData(1)],frames=channels[0].length,bytes=new Uint8Array(44+frames*4),view=new DataView(bytes.buffer);
  const text=(at:number,s:string)=>{for(let i=0;i<s.length;i++)bytes[at+i]=s.charCodeAt(i);};text(0,'RIFF');view.setUint32(4,bytes.length-8,true);text(8,'WAVE');text(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,2,true);view.setUint32(24,22050,true);view.setUint32(28,88200,true);view.setUint16(32,4,true);view.setUint16(34,16,true);text(36,'data');view.setUint32(40,frames*4,true);
  let peak=0,energy=0;for(let i=0;i<frames;i++)for(let c=0;c<2;c++){const value=channels[c][i];peak=Math.max(peak,Math.abs(value));energy+=value*value;view.setInt16(44+(i*2+c)*2,Math.round(Math.max(-1,Math.min(1,value))*32767),true);}
  let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));groups.forEach(disposePlayers);buffer.dispose();
  return {wav:btoa(binary),peak,rms:Math.sqrt(energy/(frames*2)),seconds:frames/22050};
}
