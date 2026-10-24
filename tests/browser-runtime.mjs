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
export async function routeQaApi(page,base=process.env.QA_API_URL){
 if(!base)return;const target=new URL(base);if(target.hostname!=='127.0.0.1')throw Error('QA service must be local.');
 await page.route('**/api/**',async route=>{const url=new URL(route.request().url());url.host=target.host;const response=await route.fetch({url:url.href,headers:{...route.request().headers(),origin:'http://127.0.0.1:8765'}});await route.fulfill({response});});
}
