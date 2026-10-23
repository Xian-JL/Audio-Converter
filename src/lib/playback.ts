import type { ScoreData } from './api';
import { instrument, loadInstrument, normalizationDb } from './instruments';
import { sustained, SustainedSampler } from './sustain';
import type { InstrumentId } from './instruments';
import { cycleEvents, loopPosition, scheduledTime } from './playbackTimeline';
type ToneModule = typeof import('tone');

export function remainingEvents(events: ScoreData['events'], position: number) {
  return events.filter(event => event.end > position).map(event => ({ ...event, start: Math.max(position, event.start) }));
}

/** One local synth player. Tied MusicXML fragments are already joined in these events. */
export class ScorePlayback {
  private tone: ToneModule | null = null;
  private voices: import('tone').Sampler | SustainedSampler | null = null;
  private chords: import('tone').Sampler | SustainedSampler | null = null;
  private limiter: import('tone').Limiter | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private visibilityPump:(()=>void)|null=null;
  private epoch = 0;
  private anchor = 0;
  private offset = 0;
  private enabled = [true, true];
  private levels = [60, 40];
  private instruments: [InstrumentId,InstrumentId] = ['piano','piano'];
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
  setInstruments(melody:InstrumentId,accompaniment:InstrumentId){this.instruments=[melody,accompaniment];}
  setLevels(vocal: number, accompaniment: number) {
    this.levels = [vocal, accompaniment];
    if (this.voices) this.voices.volume.value = this.levelDb(0);
    if (this.chords) this.chords.volume.value = this.levelDb(1);
  }
  private levelDb(staff: number) { return this.levels[staff] > 0 ? (staff === 0 ? -5 : -8) + instrument(this.instruments[staff]).trim + normalizationDb(this.instruments[staff]) + 20 * Math.log10(this.levels[staff] / 100) : -Infinity; }
  setLoop(range:{start:number;end:number}|null){this.loop=range&&range.start>=0&&range.end>range.start&&range.end<=this.data.duration?range:null;}
  position() { return this.running && this.tone ? loopPosition(this.tone.immediate()-this.anchor,this.offset,this.until,this.playingLoop) : this.offset; }
  async play(position = this.offset, until = this.data.duration) {
    this.pause();
    const epoch = ++this.epoch;
    const tone = await import('tone');
    await tone.start();
    const selected=[...this.instruments] as [InstrumentId,InstrumentId];
    const [rightBuffers,leftBuffers] = await Promise.all(selected.map(id=>loadInstrument(tone,id)));
    if (epoch !== this.epoch) return false;
    this.tone = tone;
    this.offset = Math.max(0, Math.min(position, this.data.duration));
    if (this.offset >= this.data.duration) this.offset = 0;
    this.playingLoop=this.loop;
    if(this.playingLoop&&(this.offset<this.playingLoop.start||this.offset>=this.playingLoop.end))this.offset=this.playingLoop.start;
    this.until = Math.max(this.offset,Math.min(this.data.duration,until));
    if(this.playingLoop)this.until=this.playingLoop.end;
    this.limiter = new tone.Limiter(-1).toDestination();
    const right=instrument(selected[0]),left=instrument(selected[1]);
    this.voices = sustained.has(selected[0])?new SustainedSampler(tone,rightBuffers,this.limiter,right.attack,right.release,this.levelDb(0)):new tone.Sampler({ urls: rightBuffers, attack: right.attack, release: right.release, volume: this.levelDb(0) }).connect(this.limiter);
    this.chords = sustained.has(selected[1])?new SustainedSampler(tone,leftBuffers,this.limiter,left.attack,left.release,this.levelDb(1)):new tone.Sampler({ urls: leftBuffers, attack: left.attack, release: selected[1]==='piano'?.25:left.release, volume: this.levelDb(1) }).connect(this.limiter);
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
        const synth = event.staff === 1 ? this.voices : this.chords;
        if (!this.enabled[event.staff - 1] || !synth) continue;
        if(event.end<=elapsed)continue;
        const start = scheduledTime(event.start,0,this.anchor,clock);
        const length = Math.max(.01, this.anchor + event.end - start);
        synth.triggerAttackRelease(event.pitches.map(midi => tone.Frequency(midi, 'midi').toNote()), length, start, event.velocity ?? (event.staff === 1 ? .85 : .72));
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
    this.voices?.dispose(); this.chords?.dispose(); this.voices = null; this.chords = null;
    this.limiter?.dispose(); this.limiter = null;
    return this.offset;
  }
  stop() { this.pause(); this.offset = 0; }
  dispose() { this.stop(); }
}
