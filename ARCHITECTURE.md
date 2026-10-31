# Current architecture · 0.7.2

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

Application version comes from `package.json`: frontend header/project persistence import it, the backend reads it in a source checkout, and Vite writes `dist/app-version.json` for portable runtime use. The portable packager also reads that version. Dependency lock metadata must only change at its two root application version fields when bumping a release. No dependency upgrades are part of 0.7.2. Score protocol stays 20; project schema stays 2 with schema 1 migration.

## Repository and maintenance

Current commands and verification boundaries live in [tests/README.md](tests/README.md). Old UI scenarios have been retained under `tests/legacy-ui`, separating historical model workflows from current release checks. Research documents describe route history; the current route in this file and SPEC.md takes precedence.

Do not remove `.venv`, `node_modules`, local models, original downloads, samples, private fixtures, exports or user jobs as routine source cleanup. Git ignores generated results and private media while retaining licensed public samples and the two synthetic silence fixtures. Installation reuses verified resources. Third-party source, weight and training-data licenses remain distinct; see [THIRD_PARTY.md](THIRD_PARTY.md).
