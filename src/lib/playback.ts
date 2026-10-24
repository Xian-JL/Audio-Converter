import type { ScoreData } from './api';
import { loadInstrument } from './instruments';
import {legacyEnsembles,validateEnsembles} from './ensemble';
import type {Ensembles} from './ensemble';
import type { InstrumentId } from './instruments';
import { cycleEvents, loopPosition, scheduledTime } from './playbackTimeline';
import {createStaffPlayers,disposePlayers,triggerPlayers,voiceLevelDb} from './ensembleSound';
import type {EnsemblePlayer} from './ensembleSound';
type ToneModule = typeof import('tone');

export function remainingEvents(events: ScoreData['events'], position: number) {
  return events.filter(event => event.end > position).map(event => ({ ...event, start: Math.max(position, event.start) }));
}

/** One local synth player. Tied MusicXML fragments are already joined in these events. */
export class ScorePlayback {
  private tone: ToneModule | null = null;
  private players:[EnsemblePlayer[],EnsemblePlayer[]]=[[],[]];
  private limiter: import('tone').Limiter | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private visibilityPump:(()=>void)|null=null;
  private epoch = 0;
  private anchor = 0;
  private offset = 0;
  private enabled = [true, true];
  private levels = [60, 40];
  private ensembles:Ensembles=legacyEnsembles(['piano','piano']);
  private running = false;
  private data: ScoreData;
  private until = Infinity;
  private loop:{start:number;end:number}|null=null;
  private playingLoop:{start:number;end:number}|null=null;
  private onTick: (position: number) => void;
  private onEnd: () => void;
  constructor(data: ScoreData, onTick: (position: number) => void, onEnd: () => void) {
    this.data = data; this.onTick = onTick; this.onEnd = onEnd;
  }
  setVoices(vocal: boolean, accompaniment: boolean) { this.enabled = [vocal, accompaniment]; }
  setInstruments(melody:InstrumentId,accompaniment:InstrumentId){this.setEnsembles(legacyEnsembles([melody,accompaniment]));}
  setEnsembles(ensembles:Ensembles){this.ensembles=validateEnsembles(ensembles);}
  setLevels(vocal: number, accompaniment: number) {
    this.levels = [vocal, accompaniment];
    this.players.forEach((players,staff)=>players.forEach(p=>p.synth.volume.value=voiceLevelDb(staff,p.layer,players.length,this.levels)));
  }
  setLoop(range:{start:number;end:number}|null){this.loop=range&&range.start>=0&&range.end>range.start&&range.end<=this.data.duration?range:null;}
  position() { return this.running && this.tone ? loopPosition(this.tone.immediate()-this.anchor,this.offset,this.until,this.playingLoop) : this.offset; }
  async play(position = this.offset, until = this.data.duration) {
    this.pause();
    const epoch = ++this.epoch;
    const tone = await import('tone');
    await tone.start();
    const selected=validateEnsembles(this.ensembles);
    const banks=new Map(await Promise.all([...new Set(selected.flat().filter(l=>l.enabled&&l.gain>0).map(l=>l.instrument))].map(async id=>[id,await loadInstrument(tone,id)] as const)));
    if (epoch !== this.epoch) return false;
    this.tone = tone;
    this.offset = Math.max(0, Math.min(position, this.data.duration));
    if (this.offset >= this.data.duration) this.offset = 0;
    this.playingLoop=this.loop;
    if(this.playingLoop&&(this.offset<this.playingLoop.start||this.offset>=this.playingLoop.end))this.offset=this.playingLoop.start;
    this.until = Math.max(this.offset,Math.min(this.data.duration,until));
    if(this.playingLoop)this.until=this.playingLoop.end;
    this.limiter = new tone.Limiter(-1).toDestination();
    try{
      selected.forEach((layers,staff)=>{this.players[staff]=createStaffPlayers(tone,layers,banks,staff,this.levels,this.limiter!);});
    }catch(error){this.pause();throw error;}
    this.anchor = tone.immediate() + .08;
    this.running = true;
    let events = cycleEvents(this.data.events, this.offset,this.until,0);
    let nextCycle=this.until-this.offset;
    let index = 0;
    const pump = () => {
      if (!this.running) return;
      const clock = tone.immediate();
      const elapsed = Math.max(0, clock - this.anchor);
      const horizon=document.hidden?3:.35;
      while(this.playingLoop&&nextCycle<elapsed+horizon){
        events=events.slice(index);index=0;
        events.push(...cycleEvents(this.data.events,this.playingLoop.start,this.playingLoop.end,nextCycle));
        nextCycle+=this.playingLoop.end-this.playingLoop.start;
      }
      while (index < events.length && events[index].start < elapsed + horizon) {
        const event = events[index++];
        const staff=event.staff===1?0:1;
        if (!this.enabled[staff]) continue;
        if(event.end<=elapsed)continue;
        const start = scheduledTime(event.start,0,this.anchor,clock);
        const length = Math.max(.01, this.anchor + event.end - start);
        triggerPlayers(tone,this.players[staff],event.pitches,length,start,event.velocity??(staff===0?.85:.72));
      }
      this.onTick(this.position());
      if (!this.playingLoop&&elapsed>=this.until-this.offset) { this.pause(); this.offset = 0; this.onEnd(); }
    };
    pump();
    this.timer = setInterval(pump, 30);
    this.visibilityPump=pump;document.addEventListener('visibilitychange',pump);
    return true;
  }
  pause() {
    this.offset = Math.max(0, this.position());
    this.epoch++; this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    if(this.visibilityPump)document.removeEventListener('visibilitychange',this.visibilityPump);this.visibilityPump=null;
    for(const staff of this.players)disposePlayers(staff);this.players=[[],[]];
    this.limiter?.dispose(); this.limiter = null;
    return this.offset;
  }
  stop() { this.pause(); this.offset = 0; }
  dispose() { this.stop(); }
}
