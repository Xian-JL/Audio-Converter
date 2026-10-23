import { useEffect, useState } from 'react';
import type { MusicSettings as Settings } from './lib/api';
import type { en } from './lib/i18n';
const keys = {
  major: ['Cb', 'Gb', 'Db', 'Ab', 'Eb', 'Bb', 'F', 'C', 'G', 'D', 'A', 'E', 'B', 'F#', 'C#'],
  minor: ['Ab', 'Eb', 'Bb', 'F', 'C', 'G', 'D', 'A', 'E', 'B', 'F#', 'C#', 'G#', 'D#', 'A#'],
};
export default function MusicSettings({ text, onApply, busy, value }: { text: typeof en; onApply: (settings: Settings) => void; busy: boolean; value?: Settings|null }) {
  const [bpm, setBpm] = useState('');
  const [meter, setMeter] = useState('');
  const [key, setKey] = useState('');
  useEffect(()=>{if(value){setBpm(String(value.bpm));setMeter(value.meter);setKey(value.key);}},[value]);
  return <section className="music-settings card">
    <div><h2>{text.musicSettings}</h2><p>{text.settingsHint}</p></div>
    <form className="settings-form" onSubmit={event => { event.preventDefault(); onApply({ bpm: Number(bpm), meter, key }); }}>
      <label>{text.tempo}<input aria-label={text.tempo} type="number" min="30" max="300" step=".01" placeholder="—" required value={bpm} onChange={event => setBpm(event.target.value)} /></label>
      <label>{text.meter}<select aria-label={text.meter} required value={meter} onChange={event => setMeter(event.target.value)}><option value="" disabled>{text.chooseSetting}</option>{['2/4','3/4','4/4','5/4','6/8','7/8','9/8','12/8'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>{text.key}<select aria-label={text.key} required value={key} onChange={event => setKey(event.target.value)}><option value="" disabled>{text.chooseSetting}</option>{(['major','minor'] as const).map(mode => <optgroup label={text[mode]} key={mode}>{keys[mode].map(root => <option value={`${root} ${mode}`} key={`${root} ${mode}`}>{root} {text[mode]}</option>)}</optgroup>)}</select></label>
      <button type="submit" disabled={busy}>{busy ? text.rendering : text.apply}</button>
    </form>
  </section>;
}
