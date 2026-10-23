import assert from 'node:assert/strict';
import {zipFiles} from '../src/lib/zip.ts';
import {songTitle,pageFileName} from '../src/lib/scorePages.ts';
assert.equal(songTitle('门尼 - 呜（The Ember）.flac'),'呜（The Ember）');
assert.equal(pageFileName(songTitle('门尼 - 呜（The Ember）.flac'),2),'《呜（The Ember）》Page_2.png');
assert.equal(pageFileName('a:b/c?',10),'《a_b_c_》Page_10.png');
const name='《呜》Page_1.png',bytes=new Uint8Array(await zipFiles([{name,data:new TextEncoder().encode('123456789')}]).arrayBuffer());
const view=new DataView(bytes.buffer);assert.equal(view.getUint32(0,true),0x04034b50);assert.equal(view.getUint16(6,true),0x800);assert.equal(view.getUint32(14,true),0xcbf43926);assert.equal(view.getUint16(12,true),33);const length=view.getUint16(26,true);assert.equal(new TextDecoder().decode(bytes.slice(30,30+length)),name);assert.equal(view.getUint32(bytes.length-22,true),0x06054b50);
console.log('PNG filenames, UTF-8 ZIP headers, CRC and date passed');
