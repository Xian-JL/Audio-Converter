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

## Audio and historical scenarios

`sound.mjs` and `ensemble-sound.mjs` use Vite on port 5173 and the local samples; `emotion-preview.mjs` is a preview-authoring utility. Preview utilities may write exports, so choose new names before authoring a new reference. Python example scripts refuse to overwrite their output files.

`legacy-ui/` retains scenarios written for the old v0.4–v0.7.1 interfaces and model routes. They are historical development records, not current release gates; their selectors and whole-song generation assumptions deliberately are not restored to the product. Current coverage is consolidated in the scripts above. Historical release notes cite their original filenames. `tests/output` is local verification evidence and is ignored by Git.
