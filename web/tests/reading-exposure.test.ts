import test from 'node:test';
import assert from 'node:assert/strict';
import {ReadingExposure} from '../src/reading-exposure.ts';

test('a short table fully visible becomes read without a click',()=>{
 const reader=new ReadingExposure(120);
 for(let ms=0;ms<3000;ms+=500)assert.equal(reader.observe(ms,0,1,true),false);
 assert.equal(reader.observe(3000,0,1,true),true);
});
test('a fast pass, a jump to the end and an unseen middle do not finish a section',()=>{
 const reader=new ReadingExposure(120);
 for(let ms=0;ms<=1000;ms+=500)assert.equal(reader.observe(ms,0,1,true),false);
 for(let ms=1500;ms<=10000;ms+=500)assert.equal(reader.observe(ms,.8,1,true),false);
 const skipped=new ReadingExposure(120);
 for(let ms=0;ms<=4000;ms+=500)assert.equal(skipped.observe(ms,0,.4,true),false);
 for(let ms=4500;ms<=10000;ms+=500)assert.equal(skipped.observe(ms,.6,1,true),false);
});
test('hidden pages and unloaded placeholders do not accrue reading time',()=>{
 const reader=new ReadingExposure(120);
 for(let ms=0;ms<=10000;ms+=500)assert.equal(reader.observe(ms,0,1,false),false);
 assert.equal(reader.observe(10500,0,1,true),false);
 assert.equal(reader.observe(11000,0,1,true),false);
 assert.equal(reader.observe(30000,0,1,true),false);
});
test('a long section counts only after reading all its parts',()=>{
 const reader=new ReadingExposure(1200);
 let result=false;
 for(let part=0;part<4;part++)for(let step=0;step<=12;step++)result=reader.observe((part*13+step)*500,part*.25,(part+1)*.25,true);
 assert.equal(result,true);
});
test('reading time scales with content but is bounded',()=>{
 assert.equal(new ReadingExposure(0).requiredMs,3000);
 assert.equal(new ReadingExposure(600).requiredMs,10000);
 assert.equal(new ReadingExposure(20000).requiredMs,30000);
});
