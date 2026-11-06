import asyncio
import json

import pytest

from backend import agent, store as s
from test_reading import env, make_run


@pytest.mark.parametrize('language,expected', [('en', 'English'), ('zh', 'Chinese')])
def test_language_survives_chinese_history_and_tool_result(env, language, expected):
    _, book_id, _, sections = env
    run = make_run(book_id, sections[0]['id'])
    with s.db() as connection:
        connection.execute('UPDATE runs SET language=? WHERE id=?', (language, run['id']))
        connection.execute('INSERT INTO messages(id,book_id,role,content,created_at) VALUES(?,?,?,?,?)',
                           ('old-language', book_id, 'assistant', '上一轮中文回答', 1))
    requests = []

    async def model(messages, api_key, emit):
        requests.append(messages)
        assert messages[-1]['role'] == 'system'
        assert f'Response language for this turn: {expected}.' in messages[-1]['content']
        assert 'unless the current user explicitly requests another language' in messages[-1]['content']
        if len(requests) == 1:
            return {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'read', 'type': 'function', 'function': {
                'name': 'read_section', 'arguments': json.dumps({'section_id': sections[0]['id']})}}]}, {}
        assert any(message['role'] == 'tool' for message in messages)
        return {'role': 'assistant', 'content': 'The value is dropped.'}, {}

    asyncio.run(agent.run_agent(run['id'], model))
    assert len(requests) == 2
    assert s.one('SELECT status FROM runs WHERE id=?', (run['id'],))['status'] == 'complete'
