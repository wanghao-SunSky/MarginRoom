import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {translate} from '../src/i18n.ts';
import {selectedReadingText} from '../src/selection.ts';

const inside={} as Node,outside={} as Node;
const root={contains:(node:Node|null)=>node===inside};
const selected=(overrides={})=>({anchorNode:inside,focusNode:inside,isCollapsed:false,toString:()=> '规划与推理\n分析约束',...overrides});
test('a collapsed or cross-reader selection does not keep a selected-character toolbar',()=>{
 assert.equal(selectedReadingText(root,selected()),'规划与推理\n分析约束');
 assert.equal(selectedReadingText(root,selected({isCollapsed:true})), '');
 assert.equal(selectedReadingText(root,selected({focusNode:outside})), '');
 assert.equal(selectedReadingText(root,selected({anchorNode:outside})), '');
 assert.equal(selectedReadingText(null,selected()), '');
 assert.equal(selectedReadingText(root,null), '');
});
test('selection capture preserves multiline quotation and caps request size',()=>{
 assert.equal(selectedReadingText(root,selected({toString:()=> 'x'.repeat(6000)})).length,5000);
 assert.equal(selectedReadingText(root,selected({toString:()=> '  \n  '})), '');
});
test('all literal interface keys and quick questions have an English translation',()=>{
 const source=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
 const keys=[...source.matchAll(/\bt\('([^']+)'/g)].map(match=>match[1]);
 assert.ok(keys.length>100);
 for(const key of keys)assert.doesNotMatch(translate('en',key),/[\u3400-\u9fff]/,key);
});
test('dynamic labels interpolate in both languages without translating book text',()=>{
 assert.equal(translate('en','已选 {count} 字',{count:69}),'69 characters selected');
 assert.equal(translate('zh','已读 {count} / {total} 节',{count:2,total:5}),'已读 2 / 5 节');
 assert.equal(translate('en','unknown-source-title'),'unknown-source-title');
 assert.match(translate('en','请读取这一章并总结：它在解决什么问题，关键思路是什么？'),/Read this chapter/);
});
