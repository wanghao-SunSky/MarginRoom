from pathlib import Path
import pytest
from backend import store as s, ingest
from test_reading import env

FIXTURES = Path(__file__).parent / 'fixtures/onboarding-v1'

@pytest.mark.parametrize('language', ['zh', 'en'])
def test_refresh_preserves_old_text_notes_positions_and_links(env, language):
    client, _, _, _ = env
    name = f'reading-demo.{language}.md'
    old, _ = ingest.import_file(name, (FIXTURES / name).read_bytes(), language)
    sections = s.all_rows('SELECT * FROM sections WHERE book_id=? ORDER BY ordinal', (old,))
    sid = sections[1]['id']
    note = s.save_artifact(old, 'note', 'My note', 'Keep this', sid)
    with s.db() as c:
        c.execute('INSERT INTO positions VALUES(?,?,?)', (old, sid, 42))
        c.execute('INSERT INTO marks VALUES(?,?)', (sid, 42))
        c.execute("INSERT INTO messages VALUES(?,?,NULL,'user','My original question',?,42)", (s.uid(), old, sid))
    for _ in range(2):
        ingest.seed()
        result = client.get('/api/books/' + old).json()
        new = result['replacement_id']
        assert new != old
        assert s.all_rows('SELECT * FROM sections WHERE book_id=? ORDER BY ordinal', (old,)) == sections
        assert s.one('SELECT * FROM artifacts WHERE id=?', (note['id'],))['content'] == 'Keep this'
        assert s.one('SELECT * FROM positions WHERE book_id=?', (old,))['section_id'] == sid
        assert s.one('SELECT * FROM marks WHERE section_id=?', (sid,))
        assert client.get('/api/sections/' + sid).json()['book_id'] == old
        assert client.get('/api/books/' + old + '/messages').json()[0]['content'] == 'My original question'
    new_book = client.get('/api/books/' + new).json()
    assert len(new_book['sections']) == 244
    assert new_book['title']=='CS329Z：AI Agent 工程（中文教程）'
    assert all('reading-demo' not in x['chapter'] for x in new_book['sections'])
    assert new_book['replacement_id'] is None
    assert s.one('SELECT count(*) n FROM books WHERE source=?',(name,))['n'] == 1
    assert next(b for b in client.get('/api/books').json() if b['id'] == old)['replacement_id'] == new


def test_same_filename_and_title_does_not_replace_private_work(env):
    _, _, _, _ = env
    bid, _ = ingest.import_file('reading-demo.zh.md', '# My own article\nPrivate content'.encode())
    with s.db() as c:c.execute("UPDATE books SET title='和 AI 一起阅读' WHERE id=?",(bid,))
    ingest.seed()
    assert s.one('SELECT title FROM books WHERE id=?',(bid,))['title'] == '和 AI 一起阅读'
    assert not s.one('SELECT * FROM example_replacements WHERE old_book_id=?',(bid,))
