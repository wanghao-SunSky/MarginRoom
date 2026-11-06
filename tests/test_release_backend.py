"""Release regressions: language, data boundaries, and complete responses."""
import asyncio
import json
import sqlite3
import pytest
from backend import agent,store as s,ingest
from backend import app as web
from test_reading import env,make_run


def test_language_migration_retains_existing_reading_data(env):
    client,bid,_,sections=env
    run=make_run(bid,sections[0]['id'])
    with s.db() as c:c.execute('ALTER TABLE runs DROP COLUMN language')
    s.init()
    record=s.one('SELECT * FROM runs WHERE id=?',(run['id'],))
    assert record['language']=='zh' and record['status']=='interrupted'
    assert client.get('/api/books/'+bid).json()['sections'][0]['id']==sections[0]['id']
    s.init()
    assert s.one('SELECT language FROM runs WHERE id=?',(run['id'],))['language']=='zh'


def test_english_run_prompt_and_error_are_persisted(env):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    with s.db() as c:c.execute("UPDATE runs SET language='en' WHERE id=?",(run['id'],))
    async def failed(messages,key,emit):
        assert messages[0]['content'].startswith(agent.SYSTEM_EN)
        assert 'Reply in clear, natural English' in messages[0]['content']
        raise RuntimeError('回复格式未完整结束，请重试。')
    asyncio.run(agent.run_agent(run['id'],failed))
    row=s.one('SELECT * FROM runs WHERE id=?',(run['id'],))
    assert row['error']=='The response format is incomplete. Please try again.'
    event=s.one("SELECT data FROM events WHERE run_id=? AND type='error'",(run['id'],))
    assert json.loads(event['data'])['message']==row['error']


def test_english_api_errors_and_request_language_validation(env,monkeypatch):
    client,bid,_,sections=env
    assert client.get('/api/books/not-found',headers={'X-Reading-Language':'en'}).json()['detail']=='Document not found.'
    assert client.get('/api/books/not-found?language=en').json()['detail']=='Document not found.'
    monkeypatch.setenv('DEEPSEEK_API_KEY','')
    body={'id':'english-missing-key','book_id':bid,'section_id':sections[0]['id'],'client_id':'test','question':'Explain','language':'en'}
    response=client.post('/api/runs',json=body)
    assert response.status_code==503 and response.json()['detail'].startswith('A model API key')
    assert client.post('/api/runs',json={**body,'language':'fr'}).status_code==422


def test_idempotency_includes_quote_language_and_revision(env,monkeypatch):
    client,bid,_,sections=env
    async def wait(_):await asyncio.sleep(60)
    monkeypatch.setattr(web,'run_agent',wait)
    body={'id':'payload-language-quote','book_id':bid,'section_id':sections[0]['id'],'client_id':'test','question':'Explain','selected_text':'original','language':'en','view_revision':2}
    assert client.post('/api/runs',json=body).status_code==200
    assert client.post('/api/runs',json=body).status_code==200
    assert s.one('SELECT language FROM runs WHERE id=?',(body['id'],))['language']=='en'
    for changes in [{'selected_text':'different'},{'language':'zh'},{'view_revision':3}]:
        response=client.post('/api/runs',json={**body,**changes})
        assert response.status_code==409
    client.post('/api/runs/'+body['id']+'/cancel')


def test_card_edits_reject_duplicate_ids_and_oversize_text(env):
    client,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    saved=asyncio.run(agent.execute_tool(run,'create_cards',{'cards':[{'front':'Q1','back':'A1','section_id':sections[0]['id']},{'front':'Q2','back':'A2','section_id':sections[0]['id']}]}))
    artifact=s.one('SELECT * FROM artifacts WHERE run_id=?',(run['id'],))
    for cards in [[saved['cards'][0]]*2,[{**saved['cards'][0],'front':'x'*1001},saved['cards'][1]]]:
        response=client.patch('/api/artifacts/'+artifact['id'],json={'title':artifact['title'],'content':json.dumps(cards),'expected_content':artifact['content']})
        assert response.status_code==422
    assert s.one('SELECT content FROM artifacts WHERE id=?',(artifact['id'],))['content']==artifact['content']


def test_blank_import_and_notes_rejected(env):
    client,bid,_,sections=env
    assert client.post('/api/import',files={'file':('blank.txt',b' \n\t')}).status_code==422
    assert client.post('/api/books/'+bid+'/artifacts',json={'title':' ','content':' ','section_id':sections[0]['id']}).status_code==422


def test_english_exports_follow_actual_origin(env):
    client,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    asyncio.run(agent.execute_tool(run,'create_cards',{'cards':[{'front':'Question','back':'Answer','section_id':sections[0]['id']}]}))
    response=client.get('http://localhost:9876/api/books/'+bid+'/export/anki?language=en')
    assert '#columns:ID\tQuestion\tAnswer\tSource\tTags' in response.text
    assert 'http://localhost:9876/?book=' in response.text and 'View source' in response.text
    notes=client.get('/api/books/'+bid+'/export/notes?language=en').text
    assert 'Reading notes' in notes and '## Conversation' in notes


def test_terminal_sse_drains_event_committed_after_last_fetch(env,monkeypatch):
    client,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    real=s.all_rows;injected=False
    def race(sql,args=()):
        nonlocal injected
        if sql.startswith('SELECT * FROM events') and not injected:
            injected=True
            s.emit(run['id'],'delta',{'text':'last chunk'})
            with s.db() as c:c.execute("UPDATE runs SET status='complete' WHERE id=?",(run['id'],))
            return []
        return real(sql,args)
    monkeypatch.setattr(s,'all_rows',race)
    output=client.get('/api/runs/'+run['id']+'/events').text
    assert 'last chunk' in output and output.index('last chunk')<output.index('event: terminal')


def test_seed_only_uses_bundled_original_examples(env,tmp_path):
    _,bid,_,sections=env
    private=tmp_path/'workspace/learning/cs329z-chinese';private.mkdir(parents=True)
    (private/'01-private.md').write_text('# Private lesson\nDO NOT IMPORT ME')
    before=len(s.all_rows('SELECT * FROM books'))
    ingest.seed(tmp_path/'workspace')
    after=s.all_rows('SELECT * FROM books')
    assert len(after)==before+1
    assert any(b["title"]=="CS329Z：AI Agent 工程（中文教程）" for b in after)
    assert not s.all_rows("SELECT * FROM sections WHERE content LIKE '%DO NOT IMPORT ME%'")
    ingest.seed(tmp_path/'workspace')
    assert len(s.all_rows('SELECT * FROM books'))==len(after)
    assert s.one('SELECT id FROM books WHERE id=?',(bid,))


def test_repeated_save_is_idempotent_but_different_content_reports_conflict(env):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    args={'kind':'note','title':'First note','content':'First content','section_id':sections[0]['id']}
    first=asyncio.run(agent.execute_tool(run,'save_artifact',args))
    assert asyncio.run(agent.execute_tool(run,'save_artifact',args))==first
    with pytest.raises(ValueError):
        asyncio.run(agent.execute_tool(run,'save_artifact',{**args,'title':'Second note','content':'Second content'}))
    assert len(s.all_rows('SELECT * FROM artifacts'))==1
    assert s.one('SELECT content FROM artifacts')['content']=='First content'


@pytest.mark.parametrize('outer,inner',[('````markdown','```python'),('~~~markdown','```python')])
def test_nested_code_fences_do_not_create_fake_sections(env,outer,inner):
    closing=outer.split('markdown')[0]
    raw=f'# Chapter\n\n{outer}\n# Example heading\n{inner}\n# This is a code comment\nprint(1)\n```\n{closing}\n\n## Real section\nText'
    sections=ingest.markdown_sections(raw,'book')
    assert [x[0] for x in sections]==['Chapter','Real section']
    assert '# This is a code comment' in sections[0][1]


@pytest.mark.parametrize('language,label',[('en','Source'),('zh','原文')])
def test_notes_export_links_back_to_source_without_rewriting_code(env,language,label):
    client,bid,_,sections=env;sid=sections[0]['id']
    literal=f'[literal](/section/{sid})'
    body=f'[citation](/section/{sid})\n\n`{literal}`\n\n````markdown\n```\n{literal}\n```\n````\n\n[after](/section/{sid})'
    note=s.save_artifact(bid,'note','My note',body,sid)
    with s.db() as c:
        c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(s.uid(),bid,None,'assistant',body,sid,s.now()))
    exported=client.get(f'http://localhost:9876/api/books/{bid}/export/notes?language={language}').text
    target=f'http://localhost:9876/?book={bid}&section={sid}'
    assert f'[citation]({target})' in exported and f'[after]({target})' in exported
    assert f'{label}: [{sections[0]["title"]}]({target})' in exported
    assert f'`{literal}`' in exported
    assert f'````markdown\n```\n{literal}\n```\n````' in exported
    assert exported.count(f'[citation]({target})')==2
    assert s.one('SELECT content FROM artifacts WHERE id=?',(note['id'],))['content']==body
