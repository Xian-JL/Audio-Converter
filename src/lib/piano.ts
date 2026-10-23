type ToneModule = typeof import('tone');
const anchorNames = ['A0', ...Array.from({ length: 7 }, (_, index) => ['C', 'Ds', 'Fs', 'A'].map(note => `${note}${index + 1}`)).flat(), 'C8'];
let bank: Promise<Record<string, AudioBuffer>> | null = null;

/** Generic instrument samples only; never caches user audio. All URLs stay on loopback. */
export function loadPiano(tone: ToneModule) {
  if (!bank) {
    bank = Promise.all(anchorNames.map(async name => {
      const holder = new tone.ToneAudioBuffer();
      try {
        await holder.load(`/piano/${name}.mp3`);
        const buffer = holder.get();
        if (!buffer) throw new Error('Piano sample decoding failed.');
        return [name.replace('Ds', 'D#').replace('Fs', 'F#'), buffer] as const;
      } finally { holder.dispose(); }
    })).then(entries => Object.fromEntries(entries)).catch(error => { bank = null; throw error; });
  }
  return bank;
}
