import asyncio
import json
import os
import httpx
import pytest
from backend import agent
from backend.model_config import get_model_config
from backend.model_protocol import build_request
from test_reading import env

@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    for key in list(os.environ):
        if key.startswith(('LLM_', 'OPENAI_', 'ANTHROPIC_', 'DEEPSEEK_')):monkeypatch.delenv(key)


def config(monkeypatch, provider='openai'):
    monkeypatch.setenv('LLM_PROVIDER', provider)
    monkeypatch.setenv('LLM_API_KEY', 'test-private-key')
    return get_model_config()


def test_legacy_key_and_provider_specific_credentials(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','old-key')
    assert get_model_config().api_key=='old-key'
    monkeypatch.setenv('LLM_PROVIDER','openai')
    assert get_model_config().api_key==''
    monkeypatch.setenv('OPENAI_API_KEY','openai-key')
    assert get_model_config().api_key=='openai-key'
    assert 'openai-key' not in repr(get_model_config())

@pytest.mark.parametrize('url',['http://remote.example/v1','https://u:p@example.com/v1','https://example.com/v1?key=secret','https://example.com/v1/chat/completions'])
def test_unsafe_or_endpoint_urls_rejected(monkeypatch,url):
    monkeypatch.setenv('LLM_BASE_URL',url)
    with pytest.raises(ValueError):get_model_config()


def test_openai_custom_url_medium_and_no_deepseek_fields(monkeypatch):
    config(monkeypatch)
    monkeypatch.setenv('LLM_BASE_URL','https://models.example/v1/')
    monkeypatch.setenv('LLM_MODEL','custom-model')
    monkeypatch.setenv('LLM_REASONING_EFFORT','medium')
    c=get_model_config();url,headers,body=build_request(c,[{'role':'assistant','content':'x','_anthropic_content':[],'reasoning_content':'private'}],[],c.api_key)
    assert url=='https://models.example/v1/chat/completions'
    assert body['reasoning_effort']=='medium' and body['model']=='custom-model'
    assert 'thinking' not in body and 'max_tokens' not in body
    assert body['messages']==[{'role':'assistant','content':'x'}]
    assert headers=={'Authorization':'Bearer test-private-key'}


def test_status_hides_key_and_endpoint(env,monkeypatch):
    client,*_=env;config(monkeypatch)
    monkeypatch.setenv('LLM_BASE_URL','https://private-gateway.example/v1')
    d=client.get('/api/status').json()
    assert d['configured'] and d['provider']=='OpenAI'
    assert 'test-private-key' not in json.dumps(d) and 'private-gateway' not in json.dumps(d)


def test_anthropic_request_maps_multiple_results_and_adaptive(monkeypatch):
    config(monkeypatch,'anthropic');monkeypatch.setenv('LLM_THINKING','adaptive');monkeypatch.setenv('LLM_REASONING_EFFORT','medium')
    tools=[{'type':'function','function':{'name':'read','description':'Read','parameters':{'type':'object'}}}]
    native=[{'type':'thinking','thinking':'private','signature':'signed'},{'type':'tool_use','id':'a','name':'read','input':{}},{'type':'tool_use','id':'b','name':'read','input':{}}]
    msgs=[{'role':'system','content':'system'},{'role':'user','content':'read'},
          {'role':'assistant','content':None,'_anthropic_content':native},
          {'role':'tool','tool_call_id':'a','content':'first'}, {'role':'tool','tool_call_id':'b','content':'second'}]
    c=get_model_config();url,headers,body=build_request(c,msgs,tools,c.api_key)
    assert url=='https://api.anthropic.com/v1/messages' and headers['anthropic-version']=='2023-06-01'
    assert body['messages'][1]['content']==native
    assert [b['tool_use_id'] for b in body['messages'][2]['content']]==['a','b']
    assert body['tools'][0]['input_schema']=={'type':'object'}
    assert body['thinking']=={'type':'adaptive'} and body['output_config']=={'effort':'medium'}


def native_events(*,partial=False,stop='tool_use'):
    result=[{'type':'message_start','message':{'usage':{'input_tokens':20,'output_tokens':1}}},
            {'type':'content_block_start','index':0,'content_block':{'type':'thinking','thinking':'','signature':''}},
            {'type':'content_block_delta','index':0,'delta':{'type':'thinking_delta','thinking':'private reasoning'}},
            {'type':'content_block_delta','index':0,'delta':{'type':'signature_delta','signature':'opaque-signature'}},
            {'type':'content_block_stop','index':0},
            {'type':'content_block_start','index':1,'content_block':{'type':'tool_use','id':'tool1','name':'get_outline','input':{}}},
            {'type':'content_block_delta','index':1,'delta':{'type':'input_json_delta','partial_json':'{'}}]
    if partial:return result
    return result+[{'type':'content_block_delta','index':1,'delta':{'type':'input_json_delta','partial_json':'}'}},
                   {'type':'content_block_stop','index':1},
                   {'type':'message_delta','delta':{'stop_reason':stop},'usage':{'output_tokens':30}},
                   {'type':'message_stop'}]


def mock_events(monkeypatch, events, requests):
    real=httpx.AsyncClient
    def respond(req):
        requests.append(json.loads(req.content))
        return httpx.Response(200,content=''.join('data: '+json.dumps(e)+'\n\n' for e in events))
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))


def test_anthropic_stream_keeps_signed_thinking_private_for_next_round(monkeypatch):
    config(monkeypatch,'anthropic');reqs=[];visible=[]
    mock_events(monkeypatch,native_events(),reqs)
    m,u=asyncio.run(agent.stream_model([{'role':'user','content':'read'}],'key',visible.append))
    assert not visible and m['tool_calls'][0]['function']=={'name':'get_outline','arguments':'{}'}
    assert m['_anthropic_content'][0]['signature']=='opaque-signature'
    assert u=={'prompt_tokens':20,'completion_tokens':30,'total_tokens':50}
    _,_,next_body=build_request(get_model_config(),[{'role':'user','content':'read'},m,{'role':'tool','tool_call_id':'tool1','content':'outline'}],[],'key')
    assert next_body['messages'][1]['content'][0]['thinking']=='private reasoning'

@pytest.mark.parametrize('events',[native_events(partial=True),native_events(stop='max_tokens'),[{'type':'error','error':{'message':'secret-key must not leak'}}]])
def test_anthropic_incomplete_or_error_never_succeeds(monkeypatch,events):
    config(monkeypatch,'anthropic');mock_events(monkeypatch,events,[])
    with pytest.raises(RuntimeError) as e:asyncio.run(agent.stream_model([],'key',lambda _:None))
    assert 'secret-key' not in str(e.value)


def test_anthropic_final_expression_streams_readable_text(monkeypatch):
    config(monkeypatch,'anthropic');visible=[]
    events=[{'type':'content_block_start','index':0,'content_block':{'type':'tool_use','id':'f','name':'clarify_meaning','input':{}}}]
    raw=json.dumps({'meaning':'A concrete explanation.','example':'A new example.','sources':[]})
    events.extend({'type':'content_block_delta','index':0,'delta':{'type':'input_json_delta','partial_json':chunk}} for chunk in [raw[:28],raw[28:]])
    events.extend([{'type':'content_block_stop','index':0},{'type':'message_delta','delta':{'stop_reason':'tool_use'}},{'type':'message_stop'}])
    mock_events(monkeypatch,events,[])
    m,_=asyncio.run(agent.stream_model([],'key',visible.append))
    assert ''.join(visible)=='A concrete explanation.\n\nA new example.'
    assert 'tool_use' not in ''.join(visible)


def test_openai_tool_signature_is_replayed(monkeypatch):
    config(monkeypatch);requests=[]
    tc={'index':0,'id':'call1','function':{'name':'get_outline','arguments':'{}'},'extra_content':{'google':{'thought_signature':'opaque'}}}
    events=[{'choices':[{'delta':{'tool_calls':[tc]},'finish_reason':'tool_calls'}]}]
    real=httpx.AsyncClient
    def respond(req):
        requests.append(json.loads(req.content))
        return httpx.Response(200,content=''.join('data: '+json.dumps(e)+'\n\n' for e in events)+'data: [DONE]\n\n')
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))
    m,_=asyncio.run(agent.stream_model([],'key',lambda _:None))
    asyncio.run(agent.stream_model([m,{'role':'tool','tool_call_id':'call1','content':'outline'}],'key',lambda _:None))
    assert requests[1]['messages'][0]['tool_calls'][0]['extra_content']=={'google':{'thought_signature':'opaque'}}
