# Audio Converter · v0.2

[简体中文](README.zh-CN.md) · [Specification](SPEC.md) · [Third-party credits](THIRD_PARTY.md) · [Deployment](DEPLOYMENT.md)

A local audio-to-score workspace for MP3/FLAC playback, GF singing-melody transcription and melody-based piano accompaniment. English and Chinese UI. Analysis runs in a Python service on the same computer; a static website alone cannot run the models.

## Features

Import one MP3 or FLAC up to 100 MiB, play the original or locally converted 320 kbps MP3, and download it. Extract the singing melody with the reviewed GAME-based GF pipeline. Supply BPM, meter and key, then select a known melody onset as the downbeat to rebuild the measure grid without changing detected pitches or performance timing.

Generate basic chords from the melody, edit and lock chords, adjust phrases/alignment, and generate optional left-hand textures. Preserve the block-chord reference and separate score/arrangement versions. Rich textures currently support 4/4. This composes accompaniment; it does not recover the original backing track.

Choose independent treble and bass instruments from 12 local sampled banks: grand piano, nylon guitar, violin, cello, flute, clarinet, bassoon, trumpet, trombone, harp, organ and xylophone. Default melody/accompaniment levels are 60/40. Instrument changes do not change notes or rhythm.

Browse fixed A4 score pages, click a measure to play from it, and automatically follow the active measure during score or original-track playback. Download a page as PNG or all page PNGs as one ZIP. Images are 2480×3508 pixels and named `《Track title》Page_x.png`.

## Run locally

The currently tested desktop setup is Windows, Python 3.11+ and Node.js 22.12+ or a compatible newer version.

```powershell
git clone https://github.com/Xian-JL/Audio-Converter.git
cd Audio-Converter
.\Setup.cmd
.\Start.cmd
```

Open **http://127.0.0.1:8765** and keep the terminal running. Setup reuses compatible installed packages and verified assets. Missing resources are downloaded from their upstream sources. Model weights, FFmpeg binaries, Python environments and node_modules are not Git source files and are not committed.

For model repair, use `setup-game.ps1` or `SetupTexture.cmd`. Instrument preparation is included in Setup and is also available through `scripts/instrument_resources.py`. Once prepared, analysis and instrument playback use local resources.

## Workflow and persistence

Apply musical settings, choose a file, wait for the melody, correct the downbeat if needed, and open **Chords & arrangement** to generate/edit chords and textures. The treble staff is written one octave above sounding pitch with an octave clef; playback retains the detected pitch. Click notes, rests, labels or measure whitespace to start playback.

Refresh clears audio jobs and generated versions. Some chord settings and the last downbeat reference can be restored by source fingerprint in the same browser. Export images and chord/arrangement JSON before closing to retain them. The 60/40 mix is a control-level ratio, not a measured loudness ratio.

## Hosting status

This release is a **desktop/local service**, not an operational public inference service. Sites/Cloudflare can host a public frontend, but Python/FFmpeg/ONNX/PyTorch inference needs a separate compute host. Do not expose the desktop Flask service directly as an anonymous shared backend: its single-active-job lifecycle and loopback checks need multi-user adaptation first.

No backend host, paid subscription or public processing endpoint has been provisioned by this source release. See [DEPLOYMENT.md](DEPLOYMENT.md) for the comparison with AI Price Atlas and confirmed hosting constraints. A public source repository does not mean public inference deployment is complete.

## Development and tests

```powershell
npm.cmd run build
npm.cmd test
node tests/playback.mjs
node tests/export.mjs
```

Setup generates deterministic synthetic regression fixtures when fixtures are absent. The generator never overwrites existing local listening data. Private song recordings and their note-analysis JSON are excluded from Git. Committed media fixtures are generated silence. Synthetic fixtures test software invariants, not musical accuracy.

GitHub Actions runs the frontend build, small Node checks and lightweight notation/harmony Python tests without downloading inference models. The full local suite requires prepared models. Browser checks additionally need Playwright/Chromium; see `tests/serve_ui.py`, `tests/ui.mjs`, `tests/downbeat.mjs`, `tests/layout.mjs`, `tests/pagination.mjs` and `tests/instruments.mjs`. `PLAYWRIGHT_PACKAGE` and `TEST_BROWSER_PATH` can point to an existing test installation; neither is a product dependency.

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
