import type { ScoreData } from './api';
import { instrument, loadInstrument } from './instruments';
import type { InstrumentId } from './instruments';
import { clipEvents, scheduledTime } from './playbackTimeline';
type ToneModule = typeof import('tone');

export function remainingEvents(events: ScoreData['events'], position: number) {
  return events.filter(event => event.end > position).map(event => ({ ...event, start: Math.max(position, event.start) }));
}

/** One local synth player. Tied MusicXML fragments are already joined in these events. */
export class ScorePlayback {
  private tone: ToneModule | null = null;
  private voices: import('tone').Sampler | null = null;
  private chords: import('tone').Sampler | null = null;
  private limiter: import('tone').Limiter | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private epoch = 0;
  private anchor = 0;
  private offset = 0;
  private enabled = [true, true];
  private levels = [60, 40];
  private instruments: [InstrumentId,InstrumentId] = ['piano','piano'];
  private running = false;
  private data: ScoreData;
  private until = Infinity;
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
  private levelDb(staff: number) { return this.levels[staff] > 0 ? (staff === 0 ? -5 : -8) + instrument(this.instruments[staff]).trim + 20 * Math.log10(this.levels[staff] / 100) : -Infinity; }
  position() { return this.running && this.tone ? Math.min(this.data.duration, this.offset + Math.max(0, this.tone.immediate() - this.anchor)) : this.offset; }
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
    this.until = Math.max(this.offset,Math.min(this.data.duration,until));
    this.limiter = new tone.Limiter(-1).toDestination();
    const right=instrument(selected[0]),left=instrument(selected[1]);
    this.voices = new tone.Sampler({ urls: rightBuffers, attack: right.attack, release: right.release, volume: this.levelDb(0) }).connect(this.limiter);
    this.chords = new tone.Sampler({ urls: leftBuffers, attack: left.attack, release: selected[1]==='piano'?.25:left.release, volume: this.levelDb(1) }).connect(this.limiter);
    this.anchor = tone.immediate() + .08;
    this.running = true;
    const events = clipEvents(this.data.events, this.offset,this.until);
    let index = 0;
    const pump = () => {
      if (!this.running) return;
      const clock = tone.immediate();
      const current = this.offset + Math.max(0, clock - this.anchor);
      while (index < events.length && events[index].start < current + .16) {
        const event = events[index++];
        const synth = event.staff === 1 ? this.voices : this.chords;
        if (!this.enabled[event.staff - 1] || !synth) continue;
        const start = scheduledTime(event.start,this.offset,this.anchor,clock);
        const length = Math.max(.01, this.anchor + event.end - this.offset - start);
        synth.triggerAttackRelease(event.pitches.map(midi => tone.Frequency(midi, 'midi').toNote()), length, start, event.velocity ?? (event.staff === 1 ? .85 : .72));
      }
      this.onTick(Math.min(current, this.until));
      if (current >= this.until) { this.pause(); this.offset = 0; this.onEnd(); }
    };
    pump();
    this.timer = setInterval(pump, 30);
    return true;
  }
  pause() {
    this.offset = Math.max(0, this.position());
    this.epoch++; this.running = false;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.voices?.dispose(); this.chords?.dispose(); this.voices = null; this.chords = null;
    this.limiter?.dispose(); this.limiter = null;
    return this.offset;
  }
  stop() { this.pause(); this.offset = 0; }
  dispose() { this.stop(); }
}
