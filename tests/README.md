# Verification

Run commands from the repository root. Current UI scenarios use an isolated QA API and never the user's `.runtime`. Do not run a browser scenario against the normal application service.

## Source checks

`npm run build` checks TypeScript and creates the frontend. `node tests/playback.mjs`, `node tests/export.mjs` and `node tests/notation-plan.mjs` check scheduling, export encoding and exact notation planning without a browser. `.github/workflows/check.yml` lists the Python checks that work with synthetic fixtures and no downloaded weights. Generate missing fixtures with `python scripts/generate_test_fixtures.py`; existing private fixtures are preserved.

For a fully prepared local installation, `python scripts/check_local.py` runs the Python regression suite. Legacy whole-song AMT inference is excluded by default; use `--legacy-inference` explicitly to include that slow historical test. The normal suite still verifies historical project restoration and both current model adapters.

## Current browser scenarios

In separate PowerShell terminals, start `.venv\Scripts\python.exe -B tests/serve_ui.py 8770` and `.venv\Scripts\python.exe -B -m http.server 8765 --bind 127.0.0.1 --directory dist`. The QA server owns a temporary directory and requires local test fixtures. The browser tests require a separate Playwright installation; `browser-runtime.mjs` can reuse the development environment's installation or `PLAYWRIGHT_PACKAGE`.

Set these variables in the terminal running the tests:

```powershell
$env:TEST_BROWSER_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$env:QA_API_URL = 'http://127.0.0.1:8770'
node tests/layout.mjs
node tests/studio.mjs
node tests/notation-ui.mjs
node tests/notation.mjs
```

`layout.mjs` covers both languages, source selection, invalid input, harmonic generation and responsive layout with QA audio. `studio.mjs` uses the locally retained, accepted EMO example and covers the five tasks, keyboard access, drafts, exact save/reopen, old and accepted candidates, real generation across task changes, mobile layout, PNG, ZIP and print. It writes new candidates only under `tests/output`, leaving the accepted files untouched. `notation-ui.mjs` exercises the retained AMT project, five-point correction, editing, looping, score/source page following and all export modes. `notation.mjs` checks MusicXML equivalence and notation boundaries in a browser without the API.

The two complete-project scenarios require private `exports/*.acproject.json` fixtures that intentionally are not in GitHub. A fresh clone can run source/CI checks and `layout.mjs` using generated synthetic fixtures. Missing private examples are not a reason to download copyrighted songs.

## Audio checks and cleanup

`sound.mjs` and `ensemble-sound.mjs` use Vite on port 5173 and local samples. `desktop_smoke.py` checks the explicit packaged app lifecycle; see desktop/README.md. `tests/output` is regenerable verification output, ignored by Git, and may be deleted after checks.

Obsolete UI scenarios and one-off sample/preview authoring scripts have been deleted. Current coverage is consolidated in the maintained scripts above. Historical release notes may cite filenames from earlier releases. AMT/AccoMontage weights are not needed to restore saved candidates and are no longer installed locally; the optional full-AMT inference test requires explicitly preparing its resources again.


## Instrument beta checks

`test_performance.py` verifies polyphony, independent chord edits, simultaneous equal-pitch identities, original-time preservation, schema-3 reopening and tamper rejection, plus the reviewed-melody arrangement boundary. `instrument-quality.json` records the small guzheng pilot and its unmet formal gates; no audio/labels are distributed.

For `performance.mjs`, stop other test servers and run `.venv\Scripts\python.exe -B tests/serve_ui.py 8765` alone. This serves the built UI and isolated temporary API on the same origin; do not start the normal app or a separate static server. Then run `node tests/performance.mjs` with `TEST_BROWSER_PATH` set as above. It opens the public synthetic `fixtures/performance-project.json`. Actual model-upload checks also run when both local files `tests/output/instrument-piano-probe.flac` and `tests/output/guzheng-real-30s.flac` exist; otherwise the report explicitly says these were skipped. Those recordings are local evidence, not a test dependency downloaded by this script. Browser file uploads must go directly to Flask: Playwright API forwarding can omit multipart file bytes.

Pinned resource setup is `setup-instrument.ps1` → `scripts/transcription_resources.py`. `scripts/instrument_resources.py` remains the existing licensed playback-sample preparer; do not overwrite it with the new transcription-model installer. Upstream source byte checks run without model weights in CI. Full `scripts/check_local.py` uses locally installed inference resources.

Packaging supports `--reuse <existing-package>`: only identical hash-verified immutable model/tool/vendor/runtime/sample resources use hard links on the same filesystem. Mutable server/frontend code and user data stay independent. Replacing linked resources requires a fresh file plus rename; do not overwrite linked binaries in place. Package output must be a new directory.
