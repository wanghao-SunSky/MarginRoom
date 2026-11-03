"""Regression: an open SSE stream may send heartbeats forever after one token."""
import asyncio
import httpx
import json
import pytest
from backend import agent, store as s
from test_reading import env, make_run

def test_thinking_progress_is_private_and_replayed_for_tool_continuation(monkeypatch):
    requests=[]
    def event(delta,finish=None):
        return ('data: '+json.dumps({'choices':[{'delta':delta,'finish_reason':finish}]})+'\n\n').encode()
    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests)==1:
            chunks=[event({'reasoning_content':'private reasoning'}) for _ in range(5)]
            chunks += [event({'tool_calls':[{'index':0,'id':'call1','function':{'name':'get_outline','arguments':'{}'}}]},'tool_calls'),b'data: [DONE]\n\n']
        else:chunks=[event({'content':'visible answer'},'stop'),b'data: [DONE]\n\n']
        return httpx.Response(200,stream=FiniteStream(chunks,delay=.01))
    real_client=httpx.AsyncClient
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(respond),**kwargs))
    monkeypatch.setattr(agent,'MODEL_PROGRESS_TIMEOUT',.04)
    visible=[]
    async def scenario():
        messages=[{'role':'user','content':'read'}]
        result,_=await agent.stream_model(messages,'test',visible.append,thinking=True)
        messages += [result,{'role':'tool','tool_call_id':'call1','content':'outline'}]
        await agent.stream_model(messages,'test',visible.append,thinking=True)
    asyncio.run(scenario())
    assert requests[0]['thinking']=={'type':'enabled'}
    assert requests[0]['reasoning_effort']=='high'
    assert requests[1]['messages'][1]['reasoning_content']=='private reasoning'*5
    assert visible==['visible answer']

class HeartbeatStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'data: {"choices":[{"delta":{"content":"first token"},"finish_reason":null}]}\n\n'
        while True:
            await asyncio.sleep(.005)
            yield b': keep-alive\n\n'
    async def aclose(self):pass


def test_heartbeat_without_model_progress_stops_waiting(env,monkeypatch):
    _,bid,_,sections=env
    run=make_run(bid,sections[0]['id'])
    real_client=httpx.AsyncClient
    transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=HeartbeatStream()))
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kwargs:real_client(transport=transport,**kwargs))
    monkeypatch.setattr(agent,'MODEL_PROGRESS_TIMEOUT',.025,raising=False)
    async def scenario():
        task=asyncio.create_task(agent.run_agent(run['id'],agent.stream_model))
        done,_=await asyncio.wait({task},timeout=.2)
        if not done:
            task.cancel();await task
            pytest.fail('Still waiting after heartbeats: no meaningful-progress deadline')
        await task
    asyncio.run(scenario())
    record=s.one('SELECT status,error FROM runs WHERE id=?',(run['id'],))
    assert record['status']=='failed'
    assert '超时' in record['error']
    assert not s.all_rows("SELECT * FROM messages WHERE run_id=? AND role='assistant'",(run['id'],))
    assert s.all_rows('SELECT * FROM events WHERE run_id=? AND type=?',(run['id'],'delta'))


def test_incomplete_stream_is_not_saved_as_finished_answer(env,monkeypatch):
    _,bid,_,sections=env
    run=make_run(bid,sections[0]['id'])
    real_client=httpx.AsyncClient
    transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b'data: {"choices":[{"delta":{"content":"only part"},"finish_reason":null}]}\n\n'))
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kwargs:real_client(transport=transport,**kwargs))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='failed'
    assert not s.all_rows("SELECT * FROM messages WHERE run_id=? AND role='assistant'",(run['id'],))

class FiniteStream(httpx.AsyncByteStream):
    def __init__(self,events,delay=0):self.events=events;self.delay=delay
    async def __aiter__(self):
        for event in self.events:
            if self.delay:await asyncio.sleep(self.delay)
            yield event
    async def aclose(self):pass


def install_stream(monkeypatch,stream):
    real_client=httpx.AsyncClient
    transport=httpx.MockTransport(lambda request:httpx.Response(200,stream=stream))
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kwargs:real_client(transport=transport,**kwargs))


def test_progress_resets_idle_deadline_and_complete_text_is_preserved(env,monkeypatch):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    token=b'data: {"choices":[{"delta":{"content":"word "},"finish_reason":null}]}\n\n'
    end=b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    install_stream(monkeypatch,FiniteStream([token]*8+[end],.01))
    monkeypatch.setattr(agent,'MODEL_PROGRESS_TIMEOUT',.045)
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='complete'
    assert s.one("SELECT content FROM messages WHERE run_id=? AND role='assistant'",(run['id'],))['content']=='word '*8


def test_finished_tool_call_arguments_are_preserved(monkeypatch):
    events=[b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-1","function":{"name":"read_section","arguments":"{\\\"section_id\\\":"}}]},"finish_reason":null}]}\n\n',
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\\"abc\\\"}"}}]},"finish_reason":"tool_calls"}]}\n\n',
            b'data: {"choices":[],"usage":{"total_tokens":20}}\n\ndata: [DONE]\n\n']
    install_stream(monkeypatch,FiniteStream(events))
    message,usage=asyncio.run(agent.stream_model([], 'test-only',lambda _:None))
    assert message['tool_calls'][0]['function']=={'name':'read_section','arguments':'{"section_id":"abc"}'}
    assert usage['total_tokens']==20


def test_continuous_progress_still_has_total_call_deadline(env,monkeypatch):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    token=b'data: {"choices":[{"delta":{"content":"word "},"finish_reason":null}]}\n\n'
    install_stream(monkeypatch,FiniteStream([token]*100,.005))
    monkeypatch.setattr(agent,'MODEL_CALL_TIMEOUT',.03)
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    record=s.one('SELECT status,error FROM runs WHERE id=?',(run['id'],))
    assert record['status']=='failed' and '超时' in record['error']


def test_output_limit_is_not_reported_as_complete(env,monkeypatch):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    install_stream(monkeypatch,FiniteStream([b'data: {"choices":[{"delta":{"content":"cut short"},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n']))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='failed'


def test_provider_unavailable_finishes_run_with_actionable_error(env,monkeypatch):
    client,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    real_client=httpx.AsyncClient
    transport=httpx.MockTransport(lambda request:httpx.Response(503,json={'error':{'message':'Service is too busy'}}))
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kwargs:real_client(transport=transport,**kwargs))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    record=s.one('SELECT status,error FROM runs WHERE id=?',(run['id'],))
    assert record['status']=='failed' and '官方服务' in record['error']
    with s.db() as c:c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(s.uid(),bid,run['id'],'user','解释这一节',sections[0]['id'],s.now()))
    history=client.get('/api/books/'+bid+'/messages').json()
    assert history[-1]['run_status']=='failed' and history[-1]['run_error']==record['error']
    events=client.get('/api/runs/'+run['id']+'/events').text
    assert 'event: terminal' in events and '"status": "failed"' in events
    assert not s.all_rows("SELECT * FROM messages WHERE run_id=? AND role='assistant'",(run['id'],))
