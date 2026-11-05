"""Regressions from the three-reader acceptance session."""
import asyncio
import json
import pytest
from backend import agent, ingest, store as s
from test_reading import env, make_run
from test_agent_stability import call, record


def test_shortcut_rejects_wrong_target_and_extra_cards_before_writing(env):
    _,bid,_,sections=env
    run=make_run(bid,sections[0]['id']);run['task_kind']='chapter_summary'
    with pytest.raises(ValueError,match='requested reading position'):
        asyncio.run(agent.execute_tool(run,'save_artifact',{'kind':'summary','title':'Wrong','content':'Wrong chapter','section_id':sections[-1]['id']}))
    with pytest.raises(ValueError,match='only permits'):
        asyncio.run(agent.execute_tool(run,'create_cards',{'cards':[{'front':'Q','back':'A','section_id':sections[0]['id']}]}))
    with pytest.raises(ValueError,match='only permits'):
        asyncio.run(agent.execute_tool(run,'navigate',{'section_id':sections[-1]['id']}))
    assert not s.all_rows('SELECT * FROM artifacts')
    assert not s.all_rows('SELECT * FROM commands')
    asyncio.run(agent.execute_tool(run,'save_artifact',{'kind':'summary','title':'Correct','content':'Current chapter','section_id':sections[0]['id']}))
    assert s.one('SELECT section_id FROM artifacts')['section_id']==sections[0]['id']


def test_current_chapter_shortcut_does_not_replay_old_combined_task(env):
    _,bid,_,sections=env
    old=make_run(bid,sections[-1]['id'],'previous-combined-task')
    with s.db() as c:
        c.execute("UPDATE runs SET status='complete' WHERE id=?",(old['id'],))
        c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(s.uid(),bid,old['id'],'user','旧任务：请总结第三节并生成三张卡',sections[-1]['id'],s.now()-2))
    run=make_run(bid,sections[0]['id'])
    with s.db() as c:c.execute("UPDATE runs SET task_kind='chapter_summary' WHERE id=?",(run['id'],))
    rounds=0
    async def model(messages,key,emit):
        nonlocal rounds
        rounds+=1
        assert not any('旧任务' in (m.get('content') or '') for m in messages)
        if rounds==1:
            return call('save_artifact',{'kind':'summary','title':'第一章','content':'工具调用','section_id':sections[0]['id']}),{}
        return {'role':'assistant','content':'已保存当前章节小结。'},{}
    asyncio.run(agent.run_agent(run['id'],model))
    assert record(run['id'])['status']=='complete'
    assert len(s.all_rows('SELECT * FROM artifacts WHERE run_id=?',(run['id'],)))==1


def test_shortcut_requires_actual_write_even_when_question_is_generic(env):
    _,bid,_,sections=env
    run=make_run(bid,sections[0]['id']);run['task_kind']='chapter_summary'
    with pytest.raises(ValueError,match='save_artifact'):agent.validate_action_claims('本章讲工具调用。',run)


def test_markdown_title_only_heading_does_not_create_empty_section(env):
    client,*_=env
    raw='# 缓存教程\n\n## 第一节\n正文一\n\n## 第二节\n```python\n# comment\nx=1\n```\n\n## 第三节\n正文三'
    result=client.post('/api/import',files={'file':('test.md',raw.encode())}).json()
    sections=client.get('/api/books/'+result['id']).json()['sections']
    assert [s['title'] for s in sections]==['第一节','第二节','第三节']
    assert [s['chapter'] for s in sections]==['第一节','第二节','第三节']
    assert '# comment' in client.get('/api/sections/'+sections[1]['id']).json()['content']
    assert ingest.markdown_sections('# Title\nIntroduction\n## Chapter\nBody','book')[0][0]=='Title'


def test_both_exports_use_canonical_url_not_proxy_host(env,monkeypatch):
    client,bid,_,sections=env;sid=sections[0]['id']
    monkeypatch.setenv('READING_PUBLIC_URL','https://marginroom.app')
    run=make_run(bid,sid)
    asyncio.run(agent.execute_tool(run,'create_cards',{'cards':[{'front':'Q','back':'A','section_id':sid}]}))
    s.save_artifact(bid,'note','Note',f'[Source](/section/{sid})',sid)
    for fmt in ('notes','anki'):
        r=client.get(f'/api/books/{bid}/export/{fmt}',headers={'X-Forwarded-Host':'attacker.example'})
        assert r.status_code==200
        assert f'https://marginroom.app/?book={bid}&section={sid}' in r.text
        assert 'testserver' not in r.text and 'attacker.example' not in r.text
