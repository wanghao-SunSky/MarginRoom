"""Failures after a saved artifact must be diagnosable without exposing input."""
import asyncio
import json
import logging

import httpx
import pytest
from backend import agent,store as s
from test_reading import env,make_run


@pytest.mark.parametrize('language',['zh','en'])
@pytest.mark.parametrize('failure',[httpx.ConnectError,httpx.RemoteProtocolError])
def test_transport_failure_after_save_keeps_artifact_and_safe_diagnostic(env,monkeypatch,caplog,language,failure):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    with s.db() as c:c.execute('UPDATE runs SET language=? WHERE id=?',(language,run['id']))
    secret='do-not-log-private-request-or-key'
    real=httpx.AsyncClient
    def fail(request):raise failure(secret,request=request)
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(fail),**kw))
    calls=0
    async def model(messages,key,emit):
        nonlocal calls
        calls+=1
        if calls==1:
            return {'role':'assistant','content':None,'tool_calls':[{'id':'save1','type':'function','function':{
                'name':'save_artifact','arguments':json.dumps({'kind':'summary','title':'private-title','content':'Saved summary','section_id':sections[0]['id']})}}]},{}
        return await agent.stream_model(messages,key,emit)
    with caplog.at_level(logging.WARNING,logger='backend.agent'):
        asyncio.run(agent.run_agent(run['id'],model))
    result=s.one('SELECT status,error FROM runs WHERE id=?',(run['id'],))
    assert result['status']=='failed'
    assert ('连接' if language=='zh' else 'connection') in result['error']
    assert ('本次已保存' if language=='zh' else 'already saved') in result['error']
    assert s.one('SELECT content FROM artifacts WHERE run_id=?',(run['id'],))['content']=='Saved summary'
    assert not s.one("SELECT * FROM messages WHERE run_id=? AND role='assistant'",(run['id'],))
    assert failure.__name__ in caplog.text and 'agent.py:' in caplog.text
    assert secret not in caplog.text and 'private-title' not in caplog.text
    assert secret not in result['error']
    event=s.one("SELECT data FROM events WHERE run_id=? AND type='error'",(run['id'],))
    assert json.loads(event['data'])['message']==result['error']


def test_unexpected_failure_logs_class_and_code_location_not_exception_body(env,caplog):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    async def model(*args):raise ValueError('sensitive exception details')
    with caplog.at_level(logging.WARNING,logger='backend.agent'):
        asyncio.run(agent.run_agent(run['id'],model))
    assert 'ValueError' in caplog.text and 'agent.py:' in caplog.text
    assert 'sensitive exception details' not in caplog.text
    assert '本次已保存' not in s.one('SELECT error FROM runs WHERE id=?',(run['id'],))['error']
