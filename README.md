# Audio Converter · v0.4

[简体中文](README.zh-CN.md) · [Specification](SPEC.md) · [Third-party credits](THIRD_PARTY.md)

A local audio-to-score workspace for MP3/FLAC playback, GF singing-melody transcription and melody-based piano accompaniment. English and Chinese UI. The browser, Python service and models run on your computer. **No Oracle, cloud account, hosting subscription or API key is required.** Public deployment was cancelled; GitHub distributes the source for local use.

## Features

Import one MP3 or FLAC up to 100 MiB, play the original or locally converted 320 kbps MP3, and download it. Extract the singing melody with the reviewed GAME-based GF pipeline. Supply BPM, meter and key, then select a known melody onset as the downbeat to rebuild the measure grid without changing detected pitches or performance timing.

Generate basic chords from the melody, edit and lock chords, adjust phrases/alignment, and generate optional left-hand textures. Preserve the block-chord reference and separate score/arrangement versions. Rich textures currently support 4/4. This composes accompaniment; it does not recover the original backing track.

Build independent treble and bass ensembles from 12 local sampled banks: grand piano, nylon guitar, violin, cello, flute, clarinet, bassoon, trumpet, trombone, harp, organ and xylophone. Each bank offers Natural, Warm, Bright and Soft processed timbres (48 total). Add layers of the same or different instruments, with quantity, enable, volume and pan controls: up to 8 layers and 16 players per staff, up to 8 players per layer. Samples are shared. Default staff levels remain 60/40; instrumentation does not change notes or rhythm.

Compact engraving puts more measures on each A4 page; Standard density remains available. Pages fit proportionally into the remaining viewport without vertical window scrolling. Side panels scroll independently; narrow screens switch between Audio, Score and Tools. Browse score pages, click a measure to play from it, and automatically follow the active measure during score or original-track playback. Download a page as PNG or all page PNGs as one ZIP. Images are 2480×3508 pixels and named `《Track title》Page_x.png`.

## First-time installation on Windows

Install **Python 3.11+** and **Node.js 22.12+** or a compatible newer version, and make both available in your PATH. Windows is the currently tested platform; these launch scripts are not macOS/Linux installers. Inference runs on CPU and does not require a dedicated GPU. Larger recordings require more available memory.

With Git installed, open PowerShell and run:

```powershell
git clone https://github.com/Xian-JL/Audio-Converter.git
cd Audio-Converter
.\Setup.cmd
```

Without Git, use the repository's **Code → Download ZIP**, extract it, and double-click **Setup.cmd** inside the extracted project folder.

Keep the setup window open until it reports completion. Setup prepares the Python environment and frontend dependencies, downloads missing models/FFmpeg, verifies instrument samples, generates test fixtures if absent, and builds the application. Internet access is required for missing installation resources. Compatible packages and verified files are reused when you rerun setup. Model weights, FFmpeg binaries, Python environments and node_modules are installed locally rather than committed to GitHub.

## Offline Windows portable bundle

A complete portable folder runs with its own **Start.cmd**, without an installed Python, Node.js or network access. The normal GitHub source ZIP excludes these runtime/model binaries and still needs first-time setup.

Maintainers can build a portable folder after Setup and a frontend build:

```powershell
.venv\Scripts\python.exe scripts/package_portable.py --output release/LocalAudio-0.4.0 --zip release/LocalAudio-0.4.0.zip
```

The output directory must not exist. The packager collects the installed dependency closure, Python runtime, local models, tools, built frontend and licenses, with SHA-256 provenance. User songs, projects and runtime jobs are excluded. Copy/compress the entire folder; this offline distribution is much larger than source alone.

## Everyday use

Double-click **Start.cmd**, or run the following from the project folder:

```powershell
.\Start.cmd
```

Open **http://127.0.0.1:8765** in your browser. Keep the terminal open while using the app; press **Ctrl+C** in it to stop the service. After the first successful setup, ordinary use only needs Start.cmd and can run offline. Switch to Chinese with the top-right language control.

Do not open index.html directly. `npm run dev` starts only the development frontend; it does not replace the Python service started by Start.cmd.

For model repair, use `setup-game.ps1` or `SetupTexture.cmd`. Instrument preparation is included in Setup and is also available through `scripts/instrument_resources.py`. Once prepared, analysis and instrument playback use local resources.

## Workflow and persistence

The desktop workspace has three columns: source/settings on the left, playback/score in the center, and instruments/editing/downbeat/chords/export on the right. Transparent controls flank the score for page turning; narrow screens switch panels after score generation.

Apply musical settings, choose a file, wait for the melody, correct the downbeat if needed, and open **Chords & arrangement** to generate/edit chords and textures. The treble staff is written one octave above sounding pitch with an octave clef; playback retains the detected pitch. Click notes, rests, labels or measure whitespace to start playback.

Use **Save project** to retain a complete `.acproject.json`: original GF notes, edits/rebar versions, per-version chords and arrangements, instruments, levels, position and loop range. **Open project** restores editable work without rerunning recognition. Audio is omitted; use **Link original audio** with the exact original file for source playback. Invalid files/projects preserve existing work. Save before refreshing or closing; there is no automatic song/project persistence.

**Edit melody** enables treble-note pitch and start/end edits, insertion, deletion, split and equal-pitch merge. Each operation creates a revision with undo/redo; original GF remains available. Regenerate chords after edits. Pitch fields use sounding MIDI pitch, and times use original-audio seconds.

Choose first/last measures and enable **Loop playback** to rehear a section; clicking outside the loop exits it and plays that measure. Both staff levels are adjustable (60/40 default). Sustained strings, winds and organ use sample loops with release envelopes; piano/plucked instruments decay naturally. Bounded sample-RMS calibration reduces level differences; this is not exact perceptual loudness matching.

Layered accompaniment retains individual note durations in independent left-hand voices and adds phrase shaping, melody-responsive register and repeated-phrase motif reuse. Disable its checkbox for the compact reference. Cancelling terminates the actual CPU worker. Musical quality still needs listening evaluation.

**Print & export options** supports page-range ZIP, cancellation and A4 printing / browser Save as PDF. PNGs carry a 300 dpi physical-resolution tag.

## Ensemble example

Choose Violin for the treble layer and set Players to 4. Keep Grand piano on bass, add another bass layer, and choose Cello. These six sampled players perform the same two staff event streams together. Every instrument has four processed timbres; Layer mix exposes individual volume and pan. Quantity uses gain compensation and small deterministic tuning/onset/stereo differences to simulate an ensemble, using the existing credited recordings.

Project format 2 retains ensembles and page density. Format 1 projects migrate to one Natural player per staff. Original GF pitches and timings remain intact.

## Updating and troubleshooting

Stop the running service before updating. Git users can pull the new source, rerun Setup.cmd, start Start.cmd and refresh the browser. ZIP users should extract the new source to a project folder and run Setup.cmd there. You do not need to rerun setup for every song.

| Symptom | What to check |
| --- | --- |
| Browser cannot connect | Start.cmd is still running; use exactly `http://127.0.0.1:8765` |
| Missing models/resources | Run Setup.cmd; a clone/ZIP intentionally does not contain model binaries |
| Resource download failed | Check connectivity to the upstream source and rerun Setup.cmd; valid completed resources are reused |
| Service is already running / port 8765 in use | Use the existing app, or close its previous service terminal before restarting |
| Page requests a service restart after an update | Stop the old service, run Start.cmd again and refresh |
| Rich accompaniment is unavailable for the chosen meter | Rich textures currently support 4/4; basic block chords remain available |

The service listens on local loopback only. `127.0.0.1` on another device means that other device itself. Each user installs and runs their own copy; a public source repository is not a shared processing website.

## Development and tests

```powershell
npm.cmd run build
npm.cmd test
node tests/playback.mjs
node tests/export.mjs
```

Setup generates deterministic synthetic regression fixtures when fixtures are absent. The generator never overwrites existing local listening data. Private song recordings and their note-analysis JSON are excluded from Git. Committed media fixtures are generated silence. Synthetic fixtures test software invariants, not musical accuracy.

GitHub Actions runs the frontend build, small Node checks and lightweight notation/harmony Python tests without downloading inference models. The full local suite requires prepared models. Browser checks additionally need Playwright/Chromium; see `tests/serve_ui.py`, `tests/ui.mjs`, `tests/downbeat.mjs`, `tests/layout.mjs`, `tests/pagination.mjs` and `tests/instruments.mjs` and `tests/workspace.mjs` and `tests/v4.mjs`. With the development frontend running, `tests/sound.mjs` and `tests/ensemble-sound.mjs` additionally check sustained instruments and scheduling pressure. `PLAYWRIGHT_PACKAGE` and `TEST_BROWSER_PATH` can point to an existing test installation; neither is a product dependency.

## Open-source foundations and attribution

| Project | Role | Attribution / scope |
| --- | --- | --- |
| [openvpi/GAME](https://github.com/openvpi/GAME) | Small ONNX singing-melody model; adapted GF chunk/context driver | GAME 1.0.3; MIT; `server/GAME-LICENSE.txt` |
| [Demucs](https://github.com/facebookresearch/demucs) / [ONNX export](https://github.com/StemSplit/demucs-onnx) | Enhanced vocal separation | MIT; pinned export and manifests under `models/` |
| [Ultimate Vocal Remover / MDX resources](https://github.com/Anjok07/ultimatevocalremovergui) | Original separation model/configuration | Sources and SHA-256 recorded by resource scripts |
| [AccoMontage2](https://github.com/billyblu2000/AccoMontage2) | Corpus/fit priors adapted into basic-chord search | MIT; pinned commit and conversion-input provenance retained |
| [AccoMontage](https://github.com/zhaojw1998/AccoMontage) | Pretrained chord/texture VAE; adapted retrieval and left-hand reduction | MIT source; four unmodified inference modules retained; model/data provenance separate |
| [Salamander / Tonejs audio](https://github.com/Tonejs/audio/tree/master/salamander) | Alexander Holm's Yamaha C5 piano samples | CC BY 3.0; notices in `public/piano/` |
| [tonejs-instruments](https://github.com/nbrosowsky/tonejs-instruments) | N. P. Brosowsky's collection of additional instruments | Samples CC BY 3.0; original contributor notices retained |
| [OpenSheetMusicDisplay](https://github.com/opensheetmusicdisplay/opensheetmusicdisplay) | MusicXML engraving and page layout | BSD-3-Clause |
| [Tone.js](https://github.com/Tonejs/Tone.js) | Sampled playback and shared audio clock | MIT |
| [FFmpeg](https://ffmpeg.org/) | Local validation, decoding and MP3 conversion | Installed binary's GPLv3 notice retained; binaries not redistributed here |
| React / Vite / TypeScript / Flask / ONNX Runtime / PyTorch | Application, build and inference infrastructure | Respective upstream licenses |

The GF driver, manual-downbeat workflow, constrained chord/texture adaptations, timing mapping, UI and PNG/ZIP export are integration work. This is **not** an original model trained from scratch or an unmodified end-to-end AccoMontage implementation. Source-code licensing does not automatically license all upstream training recordings. See [THIRD_PARTY.md](THIRD_PARTY.md) and the retained notices.

## Limitations and licensing

BPM, meter, key and downbeat require user confirmation. Detection can contain wrong/missing notes; accompaniment is generated rather than reconstructed. Large files may exceed CPU/memory, and instruments have different natural attacks/decays. Prior listening feedback is not a measured accuracy benchmark.

The repository is public. An original-project license has not been selected for this release; third-party code/assets retain their existing licenses. No user recording or listening-analysis dataset is distributed by this repository.

## Local folders and cleanup

src, server, scripts and tests contain source and regression scripts. Keep public, models, tools and vendor for samples, inference resources, media tools and upstream notices. Existing .venv and node_modules are reused rather than reinstalled during cleanup.

dist is the current built frontend. tests/output is regenerable test output. release retains only the current portable ZIP, checksums and verification record. Old archives, duplicate extracted runtimes, screenshots and test projects can be removed. Store personal audio and .acproject.json files outside this repository; neither belongs on GitHub. Do not clear .runtime while a task is active.

Browser regression can use an isolated API on port 8770: keep the normal frontend on 8765, run `.venv\Scripts\python.exe -B tests/serve_ui.py 8770`, and set `$env:QA_API_URL='http://127.0.0.1:8770'` before running the legacy browser scripts. `tests/v4.mjs` already forwards its API calls to that isolated service. Neither route writes to real user jobs. For offline timbre/ensemble checks, run the Vite development frontend and `node tests/ensemble-sound.mjs`.

The center reserves only one compact playback/seek row above the largest full-page score that fits. Measure jump, loop range, page selection and density live under **Page & playback** in the right panel. Transparent turn buttons remain beside the score. Full A4 proportions are preserved, including necessary whitespace when the viewport has a different aspect ratio.
