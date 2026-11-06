import test from 'node:test';
import assert from 'node:assert/strict';
import {readerModelLabel} from '../src/model-label.ts';
test('model name excludes runtime flags while preserving other providers',()=>{
 assert.equal(readerModelLabel({model:'deepseek-flash',model_label:'DeepSeek Flash · Thinking'}),'DeepSeek Flash');
 assert.equal(readerModelLabel({model:'claude-sonnet',model_label:'Claude Sonnet · Thinking'}),'Claude Sonnet');
 assert.equal(readerModelLabel({model:'gpt-5'}),'gpt-5');
 assert.equal(readerModelLabel({}),'');
});
