import test from 'node:test';
import assert from 'node:assert/strict';
import {locateAnchor,textVersion,relatedHistory,type Anchor} from '../src/learning-anchors.ts';
const text='first identical phrase. middle identical phrase. end';
const start=text.lastIndexOf('identical');
const anchor:Anchor={artifact_id:'n',section_id:'s',quote:'identical phrase.',prefix:text.slice(0,start),suffix:' end',start,version:textVersion(text)};
test('saved selection reloads at the exact repeated occurrence',()=>{assert.equal(locateAnchor(text,JSON.parse(JSON.stringify(anchor))),start);assert.notEqual(locateAnchor(text,anchor),text.indexOf('identical'));});
test('changed material and wrong context never force an old underline',()=>{assert.equal(locateAnchor('changed '+text,anchor),null);assert.equal(locateAnchor(text,{...anchor,start:6}),null);assert.equal(locateAnchor(text,{...anchor,prefix:'different'}),null);});
test('history reminders exclude generic words and other sections and return exact ids',()=>{const section={id:'s',content:'Ownership borrowing lifetime references prevent dangling pointers.'};const rows=[{id:'generic',section_id:'s',content:'Please explain this chapter section text'},{id:'other',section_id:'other',content:'ownership borrowing references'},{id:'right',section_id:'s',content:'How does borrowing prevent dangling references?'}];assert.deepEqual(relatedHistory(section,rows).map(x=>x.id),['right']);});
