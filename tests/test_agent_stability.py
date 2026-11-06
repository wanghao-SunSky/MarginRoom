"""Run-level regressions for normal replies and acknowledged reader operations."""
import asyncio
import json

import httpx
import pytest
from backend import agent, store as s
from test_reading import env, make_run


def call(name, args, ident='call-1'):
    return {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': ident, 'type': 'function', 'function': {
            'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]}


def record(rid):
    return s.one('SELECT * FROM runs WHERE id=?', (rid,))


def answer(rid):
    return s.one("SELECT content FROM messages WHERE run_id=? AND role='assistant'", (rid,))['content']


@pytest.mark.parametrize('name,args', [
    ('map_chapter', {'problem': '市场如何成交？', 'central_idea': '撮合买卖双方。', 'sources': []}),
    ('clarify_meaning', {'meaning': '市场撮合买卖双方。', 'sources': []}),
    ('explain_requested_scope', {'answer': '市场撮合买卖双方。', 'sources': []}),
])
def test_usable_reply_with_optional_field_variation_completes(env, name, args):
    _, bid, _, sections = env
    run = make_run(bid, sections[0]['id'])
    async def model(messages, key, emit):
        return call(name, args), {'total_tokens': 100}
    asyncio.run(agent.run_agent(run['id'], model))
    assert record(run['id'])['status'] == 'complete'
    assert '买卖双方' in answer(run['id'])


def test_cumulative_usage_does_not_fail_an_already_applied_navigation(env, monkeypatch):
    _, bid, _, sections = env
    run = make_run(bid, sections[0]['id'])
    real_emit = s.emit
    def acknowledge(rid, kind, data):
        real_emit(rid, kind, data)
        if kind == 'navigation':
            ack = {'status': 'applied', 'section_id': sections[1]['id'], 'view_revision': 4}
            with s.db() as c:
                c.execute("UPDATE commands SET status='applied',result=? WHERE id=?", (json.dumps(ack), data['id']))
    monkeypatch.setattr(s, 'emit', acknowledge)
    rounds = 0
    async def model(messages, key, emit):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            return call('navigate', {'section_id': sections[1]['id']}), {'total_tokens': 40000}
        assert json.loads(next(message['content'] for message in reversed(messages) if message['role']=='tool'))['status'] == 'applied'
        assert json.loads(messages[0]['content'].split('Current reading context (source data):\n')[-1])['current_section']['id'] == sections[1]['id']
        return call('explain_requested_scope', {'answer': '已跳到目标章节。'}), {'total_tokens': 40000}
    asyncio.run(agent.run_agent(run['id'], model))
    assert len(s.all_rows('SELECT * FROM commands WHERE run_id=?', (run['id'],))) == 1
    assert record(run['id'])['status'] == 'complete'
    assert answer(run['id']) == '已跳到目标章节。'
    assert json.loads(record(run['id'])['usage'])['total_tokens'] == 80000


def test_failed_question_is_not_replayed_as_an_unanswered_request(env):
    _, bid, _, sections = env
    old = make_run(bid, sections[0]['id'], 'old-failed')
    with s.db() as c:
        c.execute("UPDATE runs SET status='failed' WHERE id=?", (old['id'],))
        c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',
                  (s.uid(), bid, old['id'], 'user', '旧任务：解释整章', sections[0]['id'], s.now()-1))
    run = make_run(bid, sections[0]['id'])
    seen = []
    async def model(messages, key, emit):
        seen.extend(messages)
        emit('只回答当前问题。')
        return {'role': 'assistant', 'content': '只回答当前问题。'}, {}
    asyncio.run(agent.run_agent(run['id'], model))
    assert not any('旧任务' in (m.get('content') or '') for m in seen)
    assert s.one('SELECT 1 FROM messages WHERE run_id=?', (old['id'],))


def test_invalid_source_is_repaired_without_reexecuting_saved_effect(env):
    _, bid, other, sections = env
    foreign = s.one('SELECT id FROM sections WHERE book_id=?', (other,))['id']
    run = make_run(bid, sections[0]['id'])
    rounds = 0
    async def model(messages, key, emit):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            return call('save_artifact', {'kind': 'note', 'title': '笔记', 'content': '已保存的内容', 'section_id': sections[0]['id']}), {}
        if rounds == 2:
            emit('初稿。')
            return call('clarify_meaning', {'meaning': '初稿。', 'example': '', 'sources': [foreign]}), {}
        tool_result=next(message for message in reversed(messages) if message['role']=='tool')
        assert 'error' in json.loads(tool_result['content'])
        return call('clarify_meaning', {'meaning': '修正后的解释。', 'example': '', 'sources': [sections[0]['id']]}), {}
    asyncio.run(agent.run_agent(run['id'], model))
    assert record(run['id'])['status'] == 'complete'
    assert len(s.all_rows('SELECT * FROM artifacts WHERE run_id=?', (run['id'],))) == 1
    assert rounds == 2
    assert '初稿' in answer(run['id']) and foreign not in answer(run['id'])
    assert '来源尚未确认' in answer(run['id'])
    assert '修正后的解释' not in answer(run['id'])


def test_transient_provider_failure_recovers_in_same_request(monkeypatch):
    attempts = []
    def respond(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=b'data: {"choices":[{"delta":{"content":"Recovered"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
    real = httpx.AsyncClient
    monkeypatch.setattr(agent.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(respond), **kw))
    monkeypatch.setattr(agent, 'MODEL_RETRY_DELAY', 0, raising=False)
    visible = []
    result, _ = asyncio.run(agent.stream_model([], 'test', visible.append))
    assert result['content'] == ''.join(visible) == 'Recovered'
    assert len(attempts) == 2


@pytest.mark.parametrize('status', [401, 402, 400])
def test_configuration_errors_are_not_retried(monkeypatch, status):
    attempts = []
    def respond(request):
        attempts.append(request)
        return httpx.Response(status)
    real = httpx.AsyncClient
    monkeypatch.setattr(agent.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(respond), **kw))
    with pytest.raises(RuntimeError):
        asyncio.run(agent.stream_model([], 'test', lambda _: None))
    assert len(attempts) == 1


def test_repeated_navigation_does_not_apply_twice(env, monkeypatch):
    _, bid, _, sections = env
    run = make_run(bid, sections[0]['id'])
    real_emit = s.emit
    def acknowledge(rid, kind, data):
        real_emit(rid, kind, data)
        if kind == 'navigation':
            with s.db() as c:
                c.execute("UPDATE commands SET status='applied',result=? WHERE id=?", (
                    json.dumps({'status': 'applied', 'section_id': sections[1]['id'], 'view_revision': 4}), data['id']))
    monkeypatch.setattr(s, 'emit', acknowledge)
    rounds = 0
    async def model(messages, key, emit):
        nonlocal rounds
        rounds += 1
        if rounds < 3:
            return call('navigate', {'section_id': sections[1]['id']}, f'nav-{rounds}'), {}
        return call('explain_requested_scope', {'answer': '已跳转。'}), {}
    asyncio.run(agent.run_agent(run['id'], model))
    assert record(run['id'])['status'] == 'complete'
    assert len(s.all_rows('SELECT * FROM commands WHERE run_id=?', (run['id'],))) == 1


def test_compaction_keeps_current_source_and_action_receipt():
    messages = [{'role': 'system', 'content': 'current source'}, {'role': 'user', 'content': 'now'}]
    for i in range(4):
        messages.extend([call('read_chapter', {'section_id': str(i)}, f'read-{i}'),
                         {'role': 'tool', 'tool_call_id': f'read-{i}', 'content': '原文'*23000}])
    messages.extend([call('navigate', {'section_id': 'target'}, 'nav'),
                     {'role': 'tool', 'tool_call_id': 'nav', 'content': '{"status":"applied"}'}])
    compact = agent.compact_context(messages)
    assert len(json.dumps(compact, ensure_ascii=False)) <= agent.MAX_CONTEXT_CHARS
    assert compact[0] == messages[0] and compact[-1] == messages[-1]
    assert compact[-3] == messages[-3]  # most recent source is still available
    assert len(compact) == len(messages)  # provider tool-call pairing is intact


def test_invalid_reply_recovery_has_a_finite_limit_and_keeps_usage(env):
    _, bid, _, sections = env
    run = make_run(bid, sections[0]['id'])
    rounds = 0
    async def model(messages, key, emit):
        nonlocal rounds
        rounds += 1
        return call('clarify_meaning', {'meaning': 42, 'sources': []}), {'total_tokens': 20}
    asyncio.run(agent.run_agent(run['id'], model))
    assert rounds == 3 and record(run['id'])['status'] == 'failed'
    assert json.loads(record(run['id'])['usage'])['total_tokens'] == 60
    assert not s.one("SELECT * FROM messages WHERE run_id=? AND role='assistant'", (run['id'],))


def test_cancellation_interrupts_provider_backoff(monkeypatch):
    attempts = []
    def respond(request):
        attempts.append(request)
        return httpx.Response(503)
    real = httpx.AsyncClient
    monkeypatch.setattr(agent.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(respond), **kw))
    async def scenario():
        task = asyncio.create_task(agent.stream_model([], 'test', lambda _: None))
        await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(scenario())
    assert len(attempts) == 1


@pytest.mark.parametrize('terminal', [False, True])
def test_navigation_claim_without_a_receipt_is_repaired(env, monkeypatch, terminal):
    _, bid, _, sections = env
    run = make_run(bid, sections[0]['id'])
    with s.db() as c:c.execute('UPDATE runs SET question=? WHERE id=?', ('跳转到交易的 setup 部分', run['id']))
    real_emit = s.emit
    def acknowledge(rid, kind, data):
        real_emit(rid, kind, data)
        if kind == 'navigation':
            with s.db() as c:
                c.execute("UPDATE commands SET status='applied',result=? WHERE id=?", (
                    json.dumps({'status': 'applied', 'section_id': sections[1]['id'], 'view_revision': 4}), data['id']))
    monkeypatch.setattr(s, 'emit', acknowledge)
    rounds = 0
    async def model(messages, key, emit):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            text = '已跳到 setup 一节。'
            emit(text)
            return (call('explain_requested_scope', {'answer': text}) if terminal else {'role': 'assistant', 'content': text}), {}
        if rounds == 2:return call('navigate', {'section_id': sections[1]['id']}), {}
        return call('explain_requested_scope', {'answer': '已跳到目标章节。'}), {}
    asyncio.run(agent.run_agent(run['id'], model))
    assert record(run['id'])['status'] == 'complete'
    assert len(s.all_rows("SELECT * FROM commands WHERE run_id=? AND status='applied'", (run['id'],))) == 1
    assert answer(run['id']) == '已跳到目标章节。'


def test_saved_note_claim_must_have_this_runs_artifact(env):
    _, bid, _, sections = env
    run = make_run(bid, sections[0]['id'])
    rounds = 0
    async def model(messages, key, emit):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            return call('explain_requested_scope', {'answer': '笔记已保存：《setup 与 pattern 的区别》。'}), {}
        if rounds == 2:
            return call('save_artifact', {'kind': 'note', 'title': '区别', 'content': '区别的解释', 'section_id': sections[0]['id']}), {}
        return call('explain_requested_scope', {'answer': '笔记已保存。'}), {}
    asyncio.run(agent.run_agent(run['id'], model))
    assert record(run['id'])['status'] == 'complete'
    assert len(s.all_rows('SELECT id FROM artifacts WHERE run_id=?', (run['id'],))) == 1


def test_completed_writes_are_removed_but_other_actions_remain_available(monkeypatch):
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, content=b'data: {"choices":[{"delta":{"content":"Saved."},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
    real = httpx.AsyncClient
    monkeypatch.setattr(agent.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(respond), **kw))
    messages = [call('save_artifact', {}, 'save'), {'role': 'tool', 'tool_call_id': 'save', 'content': '{"saved":true}'}]
    asyncio.run(agent.stream_model(messages, 'test', lambda _: None))
    available = {t['function']['name'] for t in requests[0]['tools']}
    assert 'save_artifact' not in available
    assert {'create_cards', 'navigate', 'explain_requested_scope'} <= available


def test_requested_cards_require_real_cards_not_a_conversational_confirmation(env):
    _, bid, _, sections = env
    run = make_run(bid, sections[0]['id'])
    with s.db() as c:c.execute('UPDATE runs SET question=? WHERE id=?', ('把这一章拆成 3 张 Anki 卡片帮我记住。', run['id']))
    rounds = 0
    async def model(messages, key, emit):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            return call('explain_requested_scope', {'answer': '三张卡整理好了，去复习卡看看。'}), {}
        if rounds == 2:
            return call('create_cards', {'cards': [{'front': f'问题{i}', 'back': '答案', 'section_id': sections[0]['id']} for i in range(3)]}), {}
        return call('explain_requested_scope', {'answer': '三张卡整理好了。'}), {}
    asyncio.run(agent.run_agent(run['id'], model))
    assert record(run['id'])['status'] == 'complete'
    cards=json.loads(s.one("SELECT content FROM artifacts WHERE run_id=? AND kind='cards'",(run['id'],))['content'])
    assert len(cards) == 3


@pytest.mark.parametrize('question', ['不要跳页，解释这段', '复习卡要怎么用？', '如何保存笔记？', '解释如何生成卡片', '返回值是什么？', '回到刚才的问题再解释一下', "Don't create flashcards, just explain."])
def test_questions_and_negations_do_not_require_actions(question):
    assert agent.requested_effects(question) == set()


@pytest.mark.parametrize('missing_tables', [('ebook_documents',), ('pdf_documents','ebook_documents')])
def test_outline_works_in_a_legacy_library_without_pdf_metadata(env, missing_tables):
    _, bid, _, sections = env
    run = make_run(bid, sections[0]['id'])
    with s.db() as c:
        for table in missing_tables:c.execute(f'DROP TABLE IF EXISTS {table}')
    rounds = 0
    async def model(messages, key, emit):
        nonlocal rounds
        rounds += 1
        if rounds == 1:return call('get_outline', {}), {}
        outline=json.loads(next(message['content'] for message in reversed(messages) if message['role']=='tool'))
        assert len(outline['sections']) == len(sections)
        assert outline['bookmarks'] == []
        return call('explain_requested_scope', {'answer': '已找到本书目录。'}), {}
    asyncio.run(agent.run_agent(run['id'], model))
    assert record(run['id'])['status'] == 'complete'
