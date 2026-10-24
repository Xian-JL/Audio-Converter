import {chromium,browserPath,routeQaApi} from './browser-runtime.mjs';
import fs from 'node:fs/promises';
await fs.mkdir('tests/output',{recursive:true});
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:browserPath()});
const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
await routeQaApi(page);
await page.route('**/api/reset',r=>r.fulfill({status:204}));await page.route('**/api/jobs',r=>r.fulfill({status:202,json:{id:'e'.repeat(32)}}));
try{
 await page.goto('http://127.0.0.1:8765');await page.locator('.drop-zone[aria-disabled="false"]').waitFor();
 assert.equal(await page.locator('.release-tag').innerText(),'v0.4.0');
 for(const width of [390,768,1024,1440]){await page.setViewportSize({width,height:1000});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
 await page.screenshot({path:'tests/output/home-en.png'});
 await page.getByRole('button',{name:'中文',exact:true}).click();await page.screenshot({path:'tests/output/home-zh.png'});
 await page.locator('input[accept*="audio/mpeg"]').setInputFiles({name:'invalid.wav',mimeType:'audio/wav',buffer:Buffer.from('invalid')});await page.getByRole('alert').filter({hasText:'仅支持 MP3 和 FLAC 文件。'}).waitFor();assert.equal(await page.locator('.file-card').count(),0);
 await page.getByRole('spinbutton',{name:'速度（BPM）'}).fill('68');await page.getByLabel('拍号',{exact:true}).selectOption('4/4');await page.getByLabel('调',{exact:true}).selectOption('C major');await page.getByRole('button',{name:'应用乐谱参数',exact:true}).click();
 const chooser=page.waitForEvent('filechooser');await page.locator('.drop-zone').focus();await page.keyboard.press('Enter');await(await chooser).setFiles('tests/fixtures/ui-upload.flac');await page.locator('.score-note').first().waitFor();await page.locator('.score-settings summary').click();
 const response=page.waitForResponse(r=>r.url().endsWith('/harmony'));await page.getByRole('button',{name:'生成基本和弦',exact:true}).click();assert.equal((await response).status(),200);await page.waitForFunction(()=>!document.body.innerText.includes('正在绘制乐谱'));
 await page.screenshot({path:'tests/output/workspace-zh.png'});
 for(const width of [390,768,1024,1440]){await page.setViewportSize({width,height:1000});await page.waitForTimeout(250);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'tests/output/mobile-zh.png'});
 assert.deepEqual(errors,[]);await fs.writeFile('tests/output/layout.json',JSON.stringify({widths:[390,768,1024,1440],languages:['en','zh'],horizontalOverflow:false,errors},null,2));console.log('Desktop, tablet and mobile layout checks passed');
}finally{await browser.close();}
