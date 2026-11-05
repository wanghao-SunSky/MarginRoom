import asyncio
import io
import json
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from backend import store as s, ingest, agent
from backend import app as web

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'DATA',tmp_path)
    monkeypatch.setattr(ingest,'DATA',tmp_path)
    monkeypatch.setattr(web,'seed',lambda _:None)
    monkeypatch.setattr(web,'load_dotenv',lambda *a,**k:None)
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-only')
    with TestClient(web.app) as client:
        bid,_=ingest.import_file('课程.md','# 章节一\n工具调用\n## 案例\n函数执行 100% 安全\n# 章节二\n检索记忆'.encode())
        other,_=ingest.import_file('其他.md','# 私有书\n只有这里有秘密'.encode())
        sections=s.all_rows('SELECT * FROM sections WHERE book_id=? ORDER BY ordinal',(bid,))
        yield client,bid,other,sections

def make_run(bid,sid,rid='run-test-123'):
    with s.db() as c:
        c.execute('INSERT INTO runs(id,book_id,client_id,question,status,created_at,section_id,view_revision) VALUES(?,?,?,?,?,?,?,?)',(rid,bid,'client-test','解释','running',s.now(),sid,3))
    return s.one('SELECT * FROM runs WHERE id=?',(rid,))

def test_same_origin_on_isolated_port_and_cross_origin_rejection(env):
    client,bid,_,sections=env
    url='/books/'+bid+'/position'
    body={'section_id':sections[0]['id']}
    assert client.put('http://127.0.0.1:8767/api'+url,headers={'Origin':'http://127.0.0.1:8767'},json=body).status_code==200
    assert client.put('/api'+url,headers={'Origin':'https://untrusted.example'},json=body).status_code==403

def test_import_deduplicates_and_preserves_fences(env):
    client,bid,_,sections=env
    raw='# 算法\n```python\n# 这是注释\nx=1\n```\n## 第二节\n正文'.encode()
    a=client.post('/api/import',files={'file':('算法.md',raw)}).json()
    b=client.post('/api/import',files={'file':('重新命名.md',raw)}).json()
    assert a['created'] and not b['created'] and a['id']==b['id']
    rows=client.get('/api/books/'+a['id']).json()['sections']
    assert len(rows)==2
    assert '# 这是注释' in client.get('/api/sections/'+rows[0]['id']).json()['content']

def test_pdf_blank_page_is_not_a_missing_text_gap_and_keeps_original(env):
    client,*_=env
    writer=PdfWriter();writer.add_blank_page(width=500,height=700)
    buf=io.BytesIO();writer.write(buf)
    r=client.post('/api/import',files={'file':('scan.pdf',buf.getvalue())})
    assert r.status_code==200
    bid=r.json()['id'];b=client.get('/api/books/'+bid).json()
    assert b['missing_pages']==0 and b['blank_pages']==[1] and b['sections'][0]['page']==1
    assert client.get('/api/books/'+bid+'/file').content==buf.getvalue()

def test_reading_positions_marks_and_scope(env):
    client,bid,other,sections=env;sid=sections[1]['id']
    assert client.put('/api/books/'+bid+'/position',json={'section_id':sid}).status_code==200
    assert client.get('/api/books').json()[0]['last_section']==sid
    assert client.put('/api/books/'+other+'/position',json={'section_id':sid}).status_code==404
    assert client.put('/api/sections/'+sid+'/read',json={'read':True}).status_code==200
    assert client.get('/api/books').json()[0]['read_count']==1
    assert client.put('/api/sections/'+sid+'/read',json={'read':True}).status_code==200
    assert client.get('/api/books').json()[0]['read_count']==1
    assert client.put('/api/sections/'+sid+'/read',json={'read':False}).status_code==200
    assert client.get('/api/books').json()[0]['read_count']==0

def test_literal_chinese_search_never_crosses_books(env):
    _,bid,other,sections=env
    assert agent.search(bid,'工具')[0]['id']==sections[0]['id']
    assert len(agent.search(bid,'%'))==1
    assert agent.search(bid,'秘密')==[]
    assert len(agent.search(other,'秘密'))==1
    with s.db() as c:
        c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(s.uid(),bid,None,'user','我把工具调用和执行弄混了',sections[0]['id'],s.now()))
    assert agent.search(bid,'弄混',True)[0]['role']=='user'
    assert agent.search(other,'弄混',True)==[]

def test_cards_atomic_idempotent_and_export_stable(env):
    client,bid,other,sections=env
    run=make_run(bid,sections[0]['id']);foreign=s.one('SELECT id FROM sections WHERE book_id=?',(other,))['id']
    cards=[{'front':'什么是工具？','back':'有边界的函数接口','section_id':sections[0]['id']}]
    with pytest.raises(ValueError):
        asyncio.run(agent.execute_tool(run,'create_cards',{'cards':cards+[dict(cards[0],section_id=foreign)]}))
    assert not s.all_rows('SELECT * FROM artifacts')
    first=asyncio.run(agent.execute_tool(run,'create_cards',{'cards':cards}))
    second=asyncio.run(agent.execute_tool(run,'create_cards',{'cards':cards}))
    assert first==second
    with pytest.raises(ValueError):
        asyncio.run(agent.execute_tool(run,'create_cards',{'cards':[dict(cards[0],back='不能把不同内容当成重试')]}))
    assert len(s.all_rows('SELECT * FROM artifacts'))==1
    a=client.get('/api/books/'+bid+'/export/anki').text
    assert first['cards'][0]['id'] in a and '什么是工具？' in a
    assert a==client.get('/api/books/'+bid+'/export/anki').text
    assert len(a.strip().splitlines())==4

def test_edit_conflict_and_source_validation(env):
    client,bid,other,sections=env
    a=client.post('/api/books/'+bid+'/artifacts',json={'title':'想法','content':'原内容','section_id':sections[0]['id']}).json()
    body={'title':'修改','content':'新内容','expected_content':'原内容'}
    assert client.patch('/api/artifacts/'+a['id'],json=body).status_code==200
    assert client.patch('/api/artifacts/'+a['id'],json=body).status_code==409
    assert client.post('/api/books/'+other+'/artifacts',json={'title':'越界','content':'内容','section_id':sections[0]['id']}).status_code==422

def test_cancel_blocks_late_artifacts_and_restart_interrupts(env):
    client,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    assert client.post('/api/runs/'+run['id']+'/cancel').status_code==200
    with pytest.raises(ValueError):s.save_artifact(bid,'note','标题','内容',sections[0]['id'],run['id'])
    run=make_run(bid,sections[0]['id'],'run-after-cancel');s.init()
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='interrupted'

def test_navigation_ack_checks_window_target_and_revision(env):
    client,bid,other,sections=env;run=make_run(bid,sections[0]['id'])
    with s.db() as c:c.execute('INSERT INTO commands(id,run_id,client_id,action,section_id,expected_revision,expires_at) VALUES(?,?,?,?,?,?,?)',('command',run['id'],'client-test','navigate',sections[1]['id'],3,s.now()+20))
    ack={'client_id':'wrong-tab','status':'applied','section_id':sections[1]['id'],'view_revision':4}
    assert client.post('/api/commands/command/ack',json=ack).status_code==403
    ack['client_id']='client-test';ack['section_id']=sections[0]['id']
    assert client.post('/api/commands/command/ack',json=ack).status_code==422
    ack['section_id']=sections[1]['id'];ack['view_revision']=3
    assert client.post('/api/commands/command/ack',json=ack).status_code==422
    ack['view_revision']=4
    assert client.post('/api/commands/command/ack',json=ack).json()['status']=='applied'
    assert client.post('/api/commands/command/ack',json=ack).json()['status']=='applied'

def test_origin_and_missing_key(env,monkeypatch):
    client,bid,_,sections=env
    assert client.post('/api/import',headers={'Origin':'https://evil.example'},files={'file':('a.md',b'Hello')}).status_code==403
    monkeypatch.setenv('DEEPSEEK_API_KEY','')
    body={'id':'request-key-test','book_id':bid,'section_id':sections[0]['id'],'client_id':'tab','question':'解释'}
    assert client.post('/api/runs',json=body).status_code==503
    assert s.all_rows('SELECT * FROM runs')==[]

def test_agent_tools_real_database_and_budget(env):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id']);calls=[]
    async def fake(messages,key,emit):
        calls.append(messages.copy())
        if len(calls)==1:
            return {'role':'assistant','content':None,'tool_calls':[{'id':'call1','type':'function','function':{'name':'read_chapter','arguments':json.dumps({'section_id':sections[0]['id']})}}]}, {'total_tokens':20}
        evidence=json.loads(messages[-1]['content']);assert evidence['covered']>0
        emit('基于原文的解释。');return {'role':'assistant','content':'基于原文的解释。'}, {'total_tokens':15}
    asyncio.run(agent.run_agent(run['id'],fake))
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='complete'
    assert len(s.all_rows("SELECT * FROM messages WHERE role='assistant'"))==1
    assert json.loads(s.one('SELECT usage FROM runs WHERE id=?',(run['id'],))['usage'])['total_tokens']==35

def test_reading_state_does_not_invent_mastery(env):
    client,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    assert asyncio.run(agent.execute_tool(run,'get_reading_state',{}))['read_sections']==[]
    client.put('/api/sections/'+sections[0]['id']+'/read',json={'read':True})
    state=asyncio.run(agent.execute_tool(run,'get_reading_state',{}))
    assert [x['id'] for x in state['read_sections']]==[sections[0]['id']]

def test_import_markdown_chapters_and_oversize_coverage(env):
    client,bid,_,sections=env
    assert len({x['chapter'] for x in sections})==2
    run=make_run(bid,sections[0]['id'])
    chapter=asyncio.run(agent.execute_tool(run,'read_chapter',{'section_id':sections[0]['id']}))
    assert chapter['total']==2 and chapter['covered']==2
    with s.db() as c:c.execute('UPDATE sections SET content=? WHERE id=?',('长文本'*18000,sections[0]['id']))
    chapter=asyncio.run(agent.execute_tool(run,'read_chapter',{'section_id':sections[0]['id']}))
    assert chapter['truncated'] is True and chapter['covered']==1
    assert len(chapter['sections'][0]['content'])==46000

def test_run_idempotence_and_payload_conflict(env,monkeypatch):
    client,bid,_,sections=env
    async def wait(_):await asyncio.sleep(60)
    monkeypatch.setattr(web,'run_agent',wait)
    body={'id':'same-request-123','book_id':bid,'section_id':sections[0]['id'],'client_id':'tab','question':'解释'}
    assert client.post('/api/runs',json=body).status_code==200
    assert client.post('/api/runs',json=body).status_code==200
    assert len(s.all_rows('SELECT * FROM messages'))==1
    assert client.post('/api/runs',json={**body,'question':'另一个问题'}).status_code==409
    assert client.post('/api/runs',json={**body,'id':'different-request-123'}).status_code==409
    client.post('/api/runs/'+body['id']+'/cancel')

def test_stale_ack_does_not_move_position_and_expired_never_applies(env):
    client,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    client.put('/api/books/'+bid+'/position',json={'section_id':sections[0]['id']})
    for cid,expiry in [('stale',s.now()+20),('expired',s.now()-1)]:
        with s.db() as c:c.execute('INSERT INTO commands(id,run_id,client_id,action,section_id,expected_revision,expires_at) VALUES(?,?,?,?,?,?,?)',(cid,run['id'],'client-test','navigate',sections[1]['id'],3,expiry))
    body={'client_id':'client-test','status':'stale','view_revision':4}
    assert client.post('/api/commands/stale/ack',json=body).json()['status']=='stale'
    assert client.get('/api/books').json()[0]['last_section']==sections[0]['id']
    body.update(status='applied',section_id=sections[1]['id'])
    assert client.post('/api/commands/expired/ack',json=body).json()['status']=='expired'
