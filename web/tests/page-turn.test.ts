import test from 'node:test';
import assert from 'node:assert/strict';
import {PageTurnGesture,atReadingEnd,showIncomplete} from '../src/page-turn.ts';

test('scroll momentum reaching bottom does not skip the end of a chapter',()=>{
 const gate=new PageTurnGesture();
 assert.equal(gate.wheel(false,300,0),false);
 assert.equal(gate.wheel(true,300,30),false);
 assert.equal(gate.wheel(true,300,60),false);
 assert.equal(gate.wheel(true,120,800),true);
});
test('one gesture cannot skip multiple short chapters; next gesture can turn',()=>{
 const gate=new PageTurnGesture();
 assert.equal(gate.wheel(true,120,0),true);
 for(let t=30;t<1500;t+=30)assert.equal(gate.wheel(true,120,t),false);
 assert.equal(gate.wheel(true,120,2300),true);
});
test('small movements and upward gestures do not turn forward',()=>{
 const gate=new PageTurnGesture();
 assert.equal(gate.wheel(true,20,0),false);
 assert.equal(gate.wheel(true,-30,20),false);
 assert.equal(gate.wheel(true,120,40),false);
 assert.equal(atReadingEnd({scrollHeight:1000,scrollTop:497,clientHeight:500}),true);
 assert.equal(atReadingEnd({scrollHeight:1000,scrollTop:400,clientHeight:500}),false);
});
test('a finished reply awaiting record refresh is never marked incomplete',()=>{
 for(const status of ['running','complete',''])assert.equal(showIncomplete(status),false);
 for(const status of ['failed','cancelled','interrupted'])assert.equal(showIncomplete(status),true);
});
