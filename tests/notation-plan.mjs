import assert from 'node:assert/strict';
import {notationPlan} from '../src/lib/notation.ts';
const simple={divisions:32,meter:'4/4',length:128};
const ticks=plan=>plan.map(p=>p.ticks);
assert.deepEqual(ticks(notationPlan(0,128,simple)),[128]);
assert.deepEqual(notationPlan(0,28,simple),[{ticks:28,type:'eighth',dots:2}]);
assert.deepEqual(ticks(notationPlan(0,17,simple)),[16,1]);
assert.deepEqual(ticks(notationPlan(32,96,simple)),[32,32]); // Keep the middle strong beat.
assert.deepEqual(ticks(notationPlan(16,64,simple)),[16,32]); // Keep syncopation visible.
assert.deepEqual(ticks(notationPlan(0,96,simple,true)),[64,32]);
assert.deepEqual(ticks(notationPlan(0,56,{...simple,pickup:true,length:64})),[56]);
const compound={divisions:32,meter:'6/8',length:96};
assert.deepEqual(ticks(notationPlan(0,96,compound)),[96]);
assert.deepEqual(ticks(notationPlan(0,56,compound)),[48,8]);
assert.deepEqual(ticks(notationPlan(16,48,compound,true)),[16,16]);
assert.deepEqual(ticks(notationPlan(0,56,{divisions:64,meter:'4/4',length:256})),[56]);
for(const meter of ['2/4','3/4','4/4','5/4','6/8','7/8','9/8','12/8']) {
  const [n,d]=meter.split('/').map(Number),context={divisions:32,meter,length:n*128/d};
  for(let start=0;start<context.length;start+=3) for(let end=start+1;end<=context.length;end+=7) {
    const plan=notationPlan(start,end,context);
    assert.equal(plan.reduce((n,p)=>n+p.ticks,0),end-start);
    assert.ok(plan.every(p=>Number.isInteger(p.ticks)&&p.ticks>0&&p.dots<=2));
  }
}
assert.equal(notationPlan(0,129,simple),null);
console.log('Exact notation durations, strong beats, compound meters, pickup and dense resolution passed.');
