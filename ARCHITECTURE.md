# Current architecture · 0.8.0-beta.1

Piano (Transkun 2.0.1) and experimental guzheng (Basic Pitch 0.4.0 ONNX) bypass vocal separation. `instrument_runtime.py` verifies pinned resources; `performance_score.py` creates polyphonic two-staff scores without the vocal octave shift; `performance_editing.py` edits independent chord members; `performance_project.py` restores schema 3 without inference. Performance events retain their actual times while notation and downbeat grids can change. A separately reviewed monophonic branch enables existing harmony and EMO tools. Model availability is per source type; projects open without model weights. Preview uses key-note/fixed-pitch events; pedal controllers are saved/exported, and guzheng bend trajectories are retained in project data. Formal quality gates in [DESIGN-0.8.0.md](DESIGN-0.8.0.md) remain unmet.

## Musical route

The accepted route is GF melody transcription → manual musical settings and downbeat correction → adaptive block chords under the melody → optional emotional composition in gaps → strictly equivalent notation simplification → playback and export.

Melody accompaniment uses `adaptive-block-v1`, with within-measure changes, seventh/diminished options and user locks. Instrumental composition is limited to at least two complete melody-free measures, validated against both ticks and actual seconds. Sustains, breaths, pickups and incomplete endings are protected. Original GF events and identities never become model-generated music.

EMO is the default instrumental engine. Its phrase-development decoder uses statement, development and resolution, directional harmonic boundaries, soft repetition penalties and context registers. MIDI Emotion remains an explicit alternative. Feeling and tension contour are user choices, not automatic emotion recognition. New results are candidates; loading a project never reruns inference. Historical AMT and AccoMontage readers/adapters remain for compatibility, not as a whole-song generation UI.

The locally accepted example is the third candidate of `exports/EMO-呜-乐句发展示例.acproject.json`, fingerprint `37aff0a1d820146a46aa984e3d327f515275a90dd99ad29a85609d5a9c071cdb`. The intro was reused and the interlude regenerated, recorded in model provenance. That project and its WAV are private local references, excluded from Git. Preserve them; create separate candidates when experimenting. Acceptance is specific to this example.

## Frontend boundaries

`App.tsx` owns source/project loading, service connectivity and source audio. `StudioHeader.tsx` owns branding, service status and language controls. `MelodyScore.tsx` owns the versioned score, rendering/playback coordination and musical actions. `ToolWorkspace.tsx` organizes those actions into Melody, Chords, Compose, Sound and Export, with keyboard-accessible tabs. Panels stay mounted while hidden so drafts, cancellation handles and in-flight generation survive navigation. Save project is always available in the tool panel.

`styles/components.css` holds existing component primitives; `styles/workspace.css` holds full-page fitting and responsive geometry; `styles/studio.css` holds the current shell and task styles. `App.css` defines their import order. Engraving stays at its fixed offscreen size and the resulting A4 page fits proportionally into the viewport. Window scrolling is suppressed only when a score exists; side panels scroll independently.

Playback uses the original performance events with Tone samples. `lib/notation.ts` derives equivalent display XML, never edits playback or saved fingerprints. `lib/scorePages.ts` is the common PNG/ZIP/print path. The original voice remains the sole GF editing/downbeat target; generated treble notes use separate voices.

## Backend boundaries

`adaptive_harmony.py`, `instrumental.py` and `hybrid.py` implement harmony, safe gaps and assembly/restoration. `emotional_score.py`, `phrase_development.py` and `emotion_runtime.py` implement emotional decoding and CPU checkpoint adapters. Workers are independent processes so cancellation actually stops computation. Source code and vocabulary provenance live under `vendor` and `server/data`; large weights remain local under ignored model directories.

Application version comes from `package.json`: frontend header/project persistence import it, the backend reads it in a source checkout, and Vite writes `dist/app-version.json` for portable runtime use. The portable packager also reads that version. Dependency lock metadata must only change at its two root application version fields when bumping a release. Existing frontend dependency versions are unchanged. Instrument adapters add the pinned requirements-instrument.txt dependencies. Score protocol is 21; vocal projects remain schema 2 with schema 1 migration, while instrument projects use schema 3.

## Repository and maintenance

Current commands and verification boundaries live in [tests/README.md](tests/README.md). Only maintained tests remain. Obsolete UI scenarios, research notes, authoring utilities and superseded icon designs have been removed rather than archived.

Keep source code, the active development environment, frontend dependencies, current models, tools, samples and the one desktop application folder. Source and desktop copies of hash-verified immutable model/tool/compiled assets share NTFS hard links on this machine, saving physical disk space while keeping both paths usable. Do not modify those binary resources in place; download/build into temporary files and replace paths. Mutable code, saved projects, browser preferences and runtime jobs are not linked.

After successful extraction and validation, original model download archives can be removed. AMT and AccoMontage inference weights are no longer installed; small compatibility code and provenance remain to restore saved projects and run core regression checks. Existing generated arrangements reopen without old weights. Keep the accepted EMO project/WAV and the AMT project used by the maintained compatibility UI regression. Browser cache and regenerable test outputs may be deleted; preferences/local storage remain intact. Licensing remains documented in [THIRD_PARTY.md](THIRD_PARTY.md).
