import { version as appVersion } from '../../package.json';
import type { ScoreData, BasicHarmony, AccompanimentData, NoteInput, Job } from './api';
import type { InstrumentId } from './instruments';
import type { Ensembles } from './ensemble';
import {legacyEnsembles} from './ensemble';
export interface ScoreVersion {score:ScoreData;harmony:BasicHarmony|null;kind?:'original'|'edit'|'rebar'}
export interface LoopSettings {enabled:boolean;startMeasure:number;endMeasure:number}
export interface Workspace {
  versions:ScoreVersion[];activeVersion:number;
  textureSets:Record<string,{items:AccompanimentData[];active:number}>;
  instruments:[InstrumentId,InstrumentId];voices:[boolean,boolean];position:number;loop:LoopSettings;
  levels?:[number,number];
  ensembles?:Ensembles; scoreLayout?:'compact'|'standard';
}
export interface OpenProject {job:Job;score:ScoreData;workspace:Workspace}
const raw=(notes:NonNullable<ScoreData['notes']>):NoteInput[]=>notes.map(({id,start,end,midi,midiFloat})=>({id,start,end,midi,midiFloat}));
export function packProject(source:ScoreData,workspace:Workspace){
  const valid=new Set(workspace.versions.flatMap((v,i)=>v.harmony?[`${i}:${v.harmony.fingerprint}`]:[]));
  const textureSets=Object.fromEntries(Object.entries(workspace.textureSets).filter(([key])=>valid.has(key)).map(([key,value])=>[key,{...value,items:value.items.map(({xml:_,...item})=>item)}]));
  return {kind:'audio-converter-project',schemaVersion:2,appVersion,
    source:{name:source.sourceName,duration:source.duration,sourceSha256:source.sourceSha256,engineSignature:source.engineSignature,identityNotesJson:source.identityNotesJson,notes:raw(source.notes||[]),bpm:source.bpm,meter:source.meter,key:source.key,scoreFingerprint:source.scoreFingerprint},
    ...workspace,ensembles:workspace.ensembles||legacyEnsembles(workspace.instruments),scoreLayout:workspace.scoreLayout||'compact',textureSets,versions:workspace.versions.map(v=>({kind:v.kind,editedNotes:v.score.editedNotes,identityNotesJson:v.score.editedNotes?v.score.identityNotesJson:undefined,anchorNoteId:v.score.downbeat?.noteId,downbeats:v.score.downbeats?.map(({noteId,measure})=>({noteId,measure})),harmony:v.harmony?{fingerprint:v.harmony.fingerprint,...(v.harmony.policy?{harmonyPolicy:v.harmony.policy,segmentLocks:v.harmony.segmentLocks||{}}:{}),locks:v.harmony.locks,phraseStarts:v.harmony.phraseStarts,chordOffsetMs:v.harmony.alignment.offsetMs}:null}))};
}
