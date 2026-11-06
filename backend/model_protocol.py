"""Translate native Anthropic messages and stream events into the Agent's chat format."""
import copy
import json


def build_request(config, messages, tools, api_key, thinking=None):
    if config.provider != 'anthropic':
        # Provider-private replay blocks must never be sent to another protocol.
        replay = [{k:v for k,v in m.items() if k in ('role','content','tool_calls','tool_call_id','name')
                   or (k == 'reasoning_content' and config.provider == 'deepseek')} for m in messages]
        body = {'model': config.model, 'messages': replay, 'tools': tools, 'stream': True,
                'stream_options': {'include_usage': True}}
        body['max_completion_tokens' if config.provider == 'openai' else 'max_tokens'] = config.max_tokens
        effort = config.effort
        if config.provider == 'deepseek':
            mode = ('enabled' if thinking else 'disabled') if thinking is not None else (config.thinking or 'disabled')
            body['thinking'] = {'type': mode}
            if thinking is True and not effort: effort = 'high'
        if effort: body['reasoning_effort'] = effort
        return config.endpoint, {'Authorization': 'Bearer ' + api_key}, body
    system = []
    replay = []
    for m in messages:
        role = m['role']
        if role == 'system':
            # Anthropic takes a top-level system prompt. Preserve ordering of
            # later context/repair instructions as user-side control messages.
            if not replay: system.append(m['content'])
            else: replay.append({'role':'user','content':[{'type':'text','text':m['content']}]})
            continue
        if role == 'tool':
            blocks = [{'type':'tool_result','tool_use_id':m['tool_call_id'],'content':m.get('content') or ''}]
            role = 'user'
        elif role == 'assistant' and m.get('_anthropic_content'):
            blocks = copy.deepcopy(m['_anthropic_content'])
        else:
            blocks = [{'type':'text','text':m['content']}] if m.get('content') else []
            for call in m.get('tool_calls', []):
                blocks.append({'type':'tool_use','id':call['id'],'name':call['function']['name'],
                               'input':json.loads(call['function']['arguments'])})
        if not blocks: continue
        if replay and replay[-1]['role'] == role: replay[-1]['content'].extend(blocks)
        else: replay.append({'role':role,'content':blocks})
    body = {'model':config.model,'system':'\n\n'.join(system),'messages':replay,'max_tokens':config.max_tokens,
            'stream':True,'tools':[{'name':t['function']['name'],'description':t['function']['description'],
                                    'input_schema':t['function']['parameters']} for t in tools]}
    if config.effort: body['output_config'] = {'effort':config.effort}
    mode = ('enabled' if thinking else 'disabled') if thinking is not None else config.thinking
    if mode:
        body['thinking'] = {'type':mode}
        if mode == 'enabled': body['thinking']['budget_tokens'] = config.thinking_budget
    return config.endpoint, {'x-api-key':api_key,'anthropic-version':'2023-06-01'}, body


class AnthropicStream:
    def __init__(self):
        self.blocks = {}
        self.arguments = {}
        self.usage = {}
        self.stopped = set()

    @property
    def content(self):
        return [self.blocks[i] for i in sorted(self.blocks)]

    def feed(self, event):
        kind = event.get('type')
        delta = {}; finish = None
        if kind == 'error':
            # Do not leak provider bodies (which may echo prompts or keys).
            raise RuntimeError('模型服务在输出过程中报错，请稍后重试。')
        if kind == 'message_start':
            self.usage.update(event['message'].get('usage', {}))
        elif kind == 'content_block_start':
            i=event['index'];block=copy.deepcopy(event['content_block']);self.blocks[i]=block
            if block['type']=='tool_use':
                self.arguments[i]=''
                delta={'tool_calls':[{'index':i,'id':block['id'],'type':'function','function':{'name':block['name'],'arguments':''}}]}
            elif block['type']=='text': delta={'content':block.get('text','')}
            elif block['type']=='thinking': delta={'reasoning_content':block.get('thinking','')}
        elif kind == 'content_block_delta':
            i=event['index'];d=event['delta'];block=self.blocks[i]
            if d['type']=='text_delta':
                block['text']=block.get('text','')+d['text'];delta={'content':d['text']}
            elif d['type']=='input_json_delta':
                self.arguments[i]+=d['partial_json'];delta={'tool_calls':[{'index':i,'function':{'arguments':d['partial_json']}}]}
            elif d['type']=='thinking_delta':
                block['thinking']=block.get('thinking','')+d['thinking'];delta={'reasoning_content':d['thinking']}
            elif d['type']=='signature_delta':
                block['signature']=block.get('signature','')+d['signature'];delta={'_progress':True}
        elif kind == 'content_block_stop':
            i=event['index'];self.stopped.add(i)
            if self.blocks[i]['type']=='tool_use':
                raw=self.arguments[i] or json.dumps(self.blocks[i].get('input',{}))
                self.blocks[i]['input']=json.loads(raw)
                if not self.arguments[i]:delta={'tool_calls':[{'index':i,'function':{'arguments':raw}}]}
        elif kind == 'message_delta':
            self.usage.update(event.get('usage',{}))
            finish={'end_turn':'stop','stop_sequence':'stop','tool_use':'tool_calls'}.get(event['delta'].get('stop_reason'),event['delta'].get('stop_reason'))
        elif kind == 'message_stop':
            if set(self.blocks)!=self.stopped:raise RuntimeError('模型回复未完整结束，请重试。')
            return {'_done':True}
        usage={'prompt_tokens':sum(self.usage.get(k,0) for k in ('input_tokens','cache_creation_input_tokens','cache_read_input_tokens')),
               'completion_tokens':self.usage.get('output_tokens',0)}
        usage['total_tokens']=usage['prompt_tokens']+usage['completion_tokens']
        return {'choices':[{'delta':delta,'finish_reason':finish}],'usage':usage}
