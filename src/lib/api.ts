export interface Job {
  id: string; name: string; size: number; downloadName: string; stage: string; progress: number;
  playbackReady: boolean; analysisReady: boolean; error?: string; analysisError?: string;
  conversionSeconds?: number; analysisSeconds?: number;
  rhythmAvailable?: boolean;
  separationMode?: 'enhanced' | 'original';
  info?: { duration: number; sampleRate: number; channels: number; format: string; ignoredTrailingData?: boolean };
}
export interface ScoreData {
  baseFingerprint?:string;
  downbeat?:{noteId:string;time:number;phaseSeconds:number;measureNumber:number}|null;
  grid?:{phaseSeconds:number;pickupTicks:number};
  melodyOnly?: boolean; engine?: string; sourceName?: string; sourceSha256?: string; scoreFingerprint?: string;
  engineSignature?: { version: string; files: Record<string,string> };
  notes?: { id: string; index: number; midi: number; midiFloat: number; start: number; end: number; notatedStart: number; notatedEnd: number; startTick: number; endTick: number }[];
  fragments?: { noteId: string; startTick: number; endTick: number; midi: number }[];
  divisions?: number; maxNotationShiftMs?: number;
  notatedEvents?: ScoreData['events'];
  xml: string; bpm: number; meter: string; key: string; duration: number;
  noteCount: number; chordCount: number;
  detail?: 'stable' | 'detailed'; rawNoteCount?: number;
  rhythmMode?: 'manual' | 'beat';
  rhythmDetails?: { userBpm: number; detectedBpm: number; firstDownbeat: number; pickupTicks: number; shortGapsJoined: number; tailsExtended?: number };
  pattern?: ArrangementSettings['pattern']; color?: ArrangementSettings['color']; grouping?: string;
  accompanimentSource?: 'composed-from-melody'; uncertainHarmonyCount?: number;
  harmonyReviews?: { start: number; startTick: number; reasons: string[] }[];
  harmonies?: { start: number; end: number; name: string; roman: string; pitches: number[]; pattern: string }[];
  measures: { number: number; displayNumber?:number; pickup?:boolean; startTick?:number; endTick?:number; start: number; end: number; label: string; hasVocal: boolean }[];
  events: { id?: string; start: number; end: number; pitches: number[]; staff: number; velocity?: number }[];
}
export interface MusicSettings { bpm: number; meter: string; key: string }
export interface AccompanimentData {
  sourceFingerprint:string;harmonyFingerprint:string;fingerprint:string;
  settings:{style:'lyrical'|'flowing'|'syncopated';density:number;variant:number};
  events:ScoreData['events'];xml:string;writtenChords:BasicHarmony['writtenChords'];
  references:{firstMeasure:number;bars:number;donor:number}[];
  model:{version:string;commit:string};generationSeconds:number;
}
export interface BasicChord {
  id:string; degree:number; root:number|null; quality:string; roman:string; pitchClasses:number[]; name:string; tones:string[];
}
export interface BasicHarmony {
  sourceFingerprint:string; fingerprint:string; model:{version:string;resourceSha256:string;upstreamCommit:string};
  bars:(ScoreData['measures'][number]&{playStart:number;playEnd:number;chordId:string;name:string;roman:string;tones:string[];root:number|null;quality:string;pitches:number[];locked:boolean;phraseStart:boolean;needsReview:boolean;alternatives:string[]})[];
  choices:BasicChord[]; events:ScoreData['events']; xml:string; locks:Record<string,string>; phraseStarts:number[];
  alignment:{version:string;offsetMs:number;anchors:[number,number][];maxWarpMs:number};
  writtenChords:(ScoreData['events'][number]&{startTick:number;endTick:number;chordId:string})[];
}
export interface ArrangementSettings { pattern: 'auto' | 'block' | 'arpeggio' | 'syncopated'; color: 'lyrical' | 'basic'; grouping: string; rhythm?: 'manual' | 'beat' }
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: 'Unable to reach the local service.' }));
    throw new Error(body.error || 'Unable to reach the local service.');
  }
  if (response.status === 204) return undefined as T;
  const body = await response.text();
  return body ? JSON.parse(body) as T : undefined as T;
}
export function clock(seconds: number) {
  return `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`;
}
