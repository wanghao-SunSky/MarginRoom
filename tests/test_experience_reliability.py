"""Failure injection uses the isolated reading fixture, never production data."""
import asyncio
import json
import httpx
import pytest
from backend import agent, dialogue, store as s
from test_reading import env, make_run
from test_agent_stability import call


def test_bad_link_keeps_body_and_valid_link(env):
    _,bid,_,sections=env
    good=sections[0]['id']
    text=dialogue.render('explain_requested_scope',{'answer':f'可读解释 [坏引用](/section/missing) [好引用](/section/{good})'},bid)
    assert '可读解释' in text and '/section/missing' not in text
    assert f'/section/{good}' in text and '不代表逐句事实已核验' in text


def test_budget_preserves_checked_material_without_extra_calls(env,monkeypatch):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    monkeypatch.setattr(agent,'MAX_TOOLS',1)
    calls=0
    async def model(messages,key,emit):
        nonlocal calls
        calls+=1
        return call('read_section',{'section_id':sections[0]['id']},str(calls)),{}
    asyncio.run(agent.run_agent(run['id'],model))
    assert calls==2
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='incomplete'
    coverage=json.loads(s.one("SELECT data FROM events WHERE run_id=? AND type='coverage'",(run['id'],))['data'])
    assert coverage['can_continue'] and coverage['sections'][0]['id']==sections[0]['id']
    assert '已查阅' in s.one("SELECT content FROM messages WHERE run_id=? AND role='assistant'",(run['id'],))['content']


def test_delayed_response_headers_are_bounded(monkeypatch):
    real=httpx.AsyncClient
    async def respond(request):
        await asyncio.sleep(1)
        return httpx.Response(200,content=b'')
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))
    monkeypatch.setattr(agent,'MODEL_CALL_TIMEOUT',.025)
    async def scenario():
        with pytest.raises(RuntimeError,match='超时'):
            await asyncio.wait_for(agent.stream_model([{'role':'user','content':'x'}],'fake',lambda x:None),.2)
    asyncio.run(scenario())


def test_provider_retry_reuses_receipt_without_repeating_note(env,monkeypatch):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    rounds=0;requests=0
    async def transport(messages,key,emit,**kw):
        nonlocal requests
        requests+=1
        assert any(m['role']=='tool' and json.loads(m['content']).get('saved') for m in messages)
        if requests==1:raise httpx.ConnectError('injected')
        return {'role':'assistant','content':'已保存笔记。'},{}
    monkeypatch.setattr(agent,'_stream_model',transport)
    monkeypatch.setattr(agent,'MODEL_RETRY_DELAY',0)
    async def model(messages,key,emit):
        nonlocal rounds
        rounds+=1
        if rounds==1:return call('save_artifact',{'kind':'note','title':'n','content':'c','section_id':sections[0]['id']}),{}
        return await agent.stream_model(messages,key,emit)
    asyncio.run(agent.run_agent(run['id'],model))
    assert requests==2
    assert len(s.all_rows('SELECT * FROM artifacts WHERE run_id=?',(run['id'],)))==1
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='complete'


def test_browser_event_replay_does_not_execute_model_or_write_again(env):
    client,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    calls=0
    async def model(messages,key,emit):
        nonlocal calls
        calls+=1
        if calls==1:return call('save_artifact',{'kind':'note','title':'once','content':'saved once','section_id':sections[0]['id']}),{}
        emit('已保存笔记。')
        return {'role':'assistant','content':'已保存笔记。'},{}
    asyncio.run(agent.run_agent(run['id'],model))
    rows=s.all_rows('SELECT id FROM events WHERE run_id=? ORDER BY id',(run['id'],))
    cursor=rows[1]['id']
    first=client.get(f"/api/runs/{run['id']}/events?after={cursor}").text
    second=client.get(f"/api/runs/{run['id']}/events?after={cursor}").text
    assert first==second and 'event: terminal' in first
    assert f'id: {rows[0]["id"]}\n' not in first
    assert calls==2
    assert len(s.all_rows('SELECT * FROM artifacts WHERE run_id=?',(run['id'],)))==1


def test_continuation_keeps_incomplete_question_and_coverage_in_history(env):
    _,bid,_,sections=env
    first=make_run(bid,sections[0]['id'],'prior-incomplete')
    with s.db() as c:
        c.execute("UPDATE runs SET status='incomplete' WHERE id=?",(first['id'],))
        c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(s.uid(),bid,first['id'],'user','比较两个章节的所有权规则',sections[0]['id'],s.now()))
        c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(s.uid(),bid,first['id'],'assistant','已查第一章，第二章尚未覆盖。',sections[0]['id'],s.now()))
    current=make_run(bid,sections[0]['id'],'continuation')
    async def model(messages,key,emit):
        contents=[m.get('content') for m in messages]
        assert '比较两个章节的所有权规则' in contents
        assert '已查第一章，第二章尚未覆盖。' in contents
        return {'role':'assistant','content':'继续查阅。'},{}
    asyncio.run(agent.run_agent(current['id'],model))
    assert s.one('SELECT status FROM runs WHERE id=?',(current['id'],))['status']=='complete'


def test_tool_round_narration_and_final_answer_have_a_paragraph_boundary(env):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    rounds=0
    async def model(messages,key,emit):
        nonlocal rounds
        rounds+=1
        if rounds==1:
            emit('I will check the source.')
            return {**call('read_section',{'section_id':sections[0]['id']}),'content':'I will check the source.'},{}
        emit('## Answer\nThe checked explanation.')
        return {'role':'assistant','content':'## Answer\nThe checked explanation.'},{}
    asyncio.run(agent.run_agent(run['id'],model))
    message=s.one("SELECT content FROM messages WHERE run_id=? AND role='assistant'",(run['id'],))['content']
    assert message=='I will check the source.\n\n## Answer\nThe checked explanation.'
    streamed=''.join(json.loads(r['data'])['text'] for r in s.all_rows("SELECT data FROM events WHERE run_id=? AND type='delta' ORDER BY id",(run['id'],)))
    assert streamed==message
