import type { InstrumentId } from './instruments';
type Tone=typeof import('tone');
export const sustained=new Set<InstrumentId>(['violin','cello','flute','clarinet','bassoon','trumpet','trombone','organ']);
const loops=new WeakMap<AudioBuffer,AudioBuffer>();
/** Short crossfade at a stable sample loop; attack remains unmodified. */
function loopBuffer(source:AudioBuffer,context:BaseAudioContext){
  const cached=loops.get(source);if(cached)return cached;
  const buffer=context.createBuffer(source.numberOfChannels,source.length,source.sampleRate);
  const first=Math.floor(source.length*.3),last=Math.floor(source.length*.7),fade=Math.min(Math.floor(source.sampleRate*.012),Math.floor((last-first)/8));
  for(let channel=0;channel<source.numberOfChannels;channel++){
    const input=source.getChannelData(channel),output=buffer.getChannelData(channel);output.set(input);
    for(let i=0;i<fade;i++){const weight=(i+1)/fade;output[last-fade+i]=input[last-fade+i]*(1-weight)+input[first-fade+i]*weight;}
  }
  loops.set(source,buffer);return buffer;
}
export class SustainedSampler {
  readonly volume:import('tone').Param<'decibels'>;
  private output:import('tone').Volume;
  private sources=new Set<AudioBufferSourceNode>();
  private bank:{midi:number;buffer:AudioBuffer}[];
  private tone:Tone;private attack:number;private release:number;
  constructor(tone:Tone,buffers:Record<string,AudioBuffer>,destination:import('tone').Limiter,attack:number,release:number,level:number){
    this.tone=tone;this.attack=attack;this.release=release;
    this.output=new tone.Volume(level).connect(destination);this.volume=this.output.volume;
    this.bank=Object.entries(buffers).map(([note,buffer])=>({midi:tone.Frequency(note).toMidi(),buffer}));
  }
  triggerAttackRelease(notes:string[],length:number,start:number,velocity:number){
    const context=this.tone.getContext().rawContext as AudioContext;
    for(const name of notes){
      const midi=this.tone.Frequency(name).toMidi(),sample=this.bank.reduce((a,b)=>Math.abs(b.midi-midi)<Math.abs(a.midi-midi)?b:a);
      const source=context.createBufferSource(),envelope=context.createGain();source.buffer=loopBuffer(sample.buffer,context);source.playbackRate.value=2**((midi-sample.midi)/12);
      source.loop=true;source.loopStart=Math.floor(sample.buffer.length*.3)/sample.buffer.sampleRate;source.loopEnd=Math.floor(sample.buffer.length*.7)/sample.buffer.sampleRate;
      const attack=Math.min(this.attack,length/2);envelope.gain.setValueAtTime(0,start);envelope.gain.linearRampToValueAtTime(velocity,start+attack);envelope.gain.setValueAtTime(velocity,start+length);envelope.gain.linearRampToValueAtTime(0,start+length+this.release);
      source.connect(envelope);this.tone.connect(envelope,this.output);this.sources.add(source);
      source.onended=()=>{this.sources.delete(source);source.disconnect();envelope.disconnect();};source.start(start);source.stop(start+length+this.release+.01);
    }
  }
  dispose(){for(const source of this.sources){try{source.stop();}catch{/* A scheduled source may already have ended. */}}this.sources.clear();this.output.dispose();}
}
