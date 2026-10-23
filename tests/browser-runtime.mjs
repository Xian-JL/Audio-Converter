import {createRequire} from 'node:module';
import {existsSync} from 'node:fs';
import {homedir} from 'node:os';
import path from 'node:path';

const local=createRequire(import.meta.url);
const bundled=path.join(homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json');
let runtime;
if(process.env.PLAYWRIGHT_PACKAGE)runtime=createRequire(path.resolve(process.env.PLAYWRIGHT_PACKAGE))('playwright');
else{
  try{runtime=local('playwright');}
  catch{if(existsSync(bundled))runtime=createRequire(bundled)('playwright');else throw Error('Browser tests require a separate Playwright installation. Set PLAYWRIGHT_PACKAGE to its package.json.');}
}
export const chromium=runtime.chromium;
export function browserPath(){return process.env.TEST_BROWSER_PATH||chromium.executablePath();}
