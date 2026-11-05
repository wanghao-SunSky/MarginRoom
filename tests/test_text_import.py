"""Generated documents exercised through the local upload route."""
import pytest
from fastapi.testclient import TestClient
from backend import app as web, store as s, ingest

MARKDOWN = '''# Agent 入门 / Getting started

这是一份测试资料，不涉及真实用户数据。

## 第一章 工具调用

### 工作原理

模型决定，工具执行。English and 中文都应保留。

```python
# 代码注释不是章节
print("hello")
```

| 名称 | 作用 |
| --- | --- |
| 工具 | 执行 |

公式：$a^2 + b^2 = c^2$。

### 一个例子

- 查询天气
- 检查结果

## 第二章 阅读进度

回到刚才读到的位置。文末校验：END-中文-42。
'''
PLAIN = '''普通文本阅读样本
第一行：<agent> 不是 HTML 标签。
第二行：**星号**、_下划线_、$price$ 均应原样显示。
# 这是原文中的井号，不是目录
    四个空格需要保留

English final line. 文末校验：TXT-END-42。
'''


@pytest.fixture
def upload_client(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'DATA', tmp_path)
    monkeypatch.setattr(ingest, 'DATA', tmp_path)
    monkeypatch.setattr(web, 'load_dotenv', lambda *a, **k: None)
    monkeypatch.setattr(web, 'seed', lambda _: None)
    with TestClient(web.app) as client:
        yield client


def upload(client, name, raw):
    r = client.post('/api/import', files={'file': (name, raw)})
    assert r.status_code == 200, r.text
    result = r.json()
    book = client.get('/api/books/' + result['id']).json()
    rows = [client.get('/api/sections/' + x['id']).json() for x in book['sections']]
    return result, book, rows


@pytest.mark.parametrize('name,encoding,newline', [
    ('中文课程.md', 'utf-8', '\n'), ('English.MD', 'utf-8-sig', '\r\n')])
def test_markdown_real_content_and_chapter_boundaries(upload_client, name, encoding, newline):
    _, book, rows = upload(upload_client, name, MARKDOWN.replace('\n', newline).encode(encoding))
    assert book['format'] == 'markdown'
    assert len(rows) == 4
    assert [r['title'] for r in rows] == ['Agent 入门 / Getting started', '工作原理', '一个例子', '第二章 阅读进度']
    assert rows[1]['chapter'] == rows[2]['chapter'] == '第一章 工具调用'
    assert rows[3]['chapter'] == '第二章 阅读进度'
    combined = '\n'.join(r['content'] for r in rows)
    for expected in ['# 代码注释不是章节', '| 工具 | 执行 |', '$a^2 + b^2 = c^2$', 'END-中文-42']:
        assert expected in combined


@pytest.mark.parametrize('name,raw', [('plain.txt', PLAIN.encode()), ('中文.TXT', PLAIN.replace('\n', '\r\n').encode('utf-8-sig'))])
def test_txt_stays_literal_and_complete(upload_client, name, raw):
    _, book, rows = upload(upload_client, name, raw)
    assert book['format'] == 'text'
    assert len(rows) == 1
    assert rows[0]['content'] == raw.decode('utf-8-sig')


def test_same_bytes_different_formats_and_repeat_preserve_notes(upload_client):
    client = upload_client
    raw = b'# Example\n**Literal or bold?**\n'
    first, book, rows = upload(client, 'example.md', raw)
    text, text_book, _ = upload(client, 'example.txt', raw)
    assert first['id'] != text['id']
    assert text_book['format'] == 'text'
    sid = rows[0]['id']
    assert client.put(f'/api/books/{book["id"]}/position', json={'section_id': sid}).status_code == 200
    assert client.put(f'/api/sections/{sid}/read', json={'read': True}).status_code == 200
    note = client.post(f'/api/books/{book["id"]}/artifacts', json={'kind': 'note', 'title': '测试笔记', 'content': '重导应保留', 'section_id': sid}).json()
    again, _, after = upload(client, 'renamed.MD', raw)
    assert again == {'id': first['id'], 'created': False}
    assert [r['id'] for r in after] == [r['id'] for r in rows]
    assert client.get(f'/api/books/{book["id"]}/artifacts').json()[0]['id'] == note['id']
    found = next(b for b in client.get('/api/books').json() if b['id'] == book['id'])
    assert found['last_section'] == sid and found['read_count'] == 1


@pytest.mark.parametrize('name,raw', [
    ('empty.md', b''), ('blank.txt', b' \r\n\t'), ('bom.txt', b'\xef\xbb\xbf'),
    ('gbk.txt', '中文内容'.encode('gbk')), ('utf16.txt', '中文内容'.encode('utf-16')),
    ('binary.txt', b'hello\x00world'), ('page.html', b'<p>Unsupported</p>'),
    ('book.epub', b'PK\x03\x04'), ('book.docx', b'PK\x03\x04')])
def test_invalid_inputs_are_rejected_without_partial_book(upload_client, name, raw):
    before = upload_client.get('/api/books').json()
    r = upload_client.post('/api/import', files={'file': (name, raw)})
    assert r.status_code == 422, r.text
    assert isinstance(r.json()['detail'], str) and r.json()['detail']
    assert upload_client.get('/api/books').json() == before


def test_large_plain_text_retains_end(upload_client):
    text = ('中文 English 123。\n' * 6000) + 'LAST-LINE-完整'
    _, _, rows = upload(upload_client, 'large.txt', text.encode())
    assert ''.join(r['content'] for r in rows) == text


def test_file_size_limit_does_not_leave_partial_book(upload_client):
    before = upload_client.get('/api/books').json()
    r = upload_client.post('/api/import', files={'file': ('oversize.txt', b'x' * (20 * 1024**2 + 1))})
    assert r.status_code == 413
    assert upload_client.get('/api/books').json() == before


def test_local_large_text_retains_all_characters(upload_client):
    _, _, rows = upload(upload_client, 'large.txt', b'a' * 2_000_001)
    assert len(rows[0]['content']) == 2_000_001


def test_legacy_txt_reimport_keeps_section_ids_and_separates_markdown(tmp_path, monkeypatch):
    import hashlib
    monkeypatch.setattr(s, 'DATA', tmp_path)
    s.init()
    raw = b'# Old TXT\n**Preserve my records**'
    bid, _ = ingest.add_book('Old TXT', '', 'markdown', 'old.TXT', hashlib.sha256(raw).hexdigest(),
                            [('Old TXT', [('Old TXT', raw.decode(), None)])])
    before = s.all_rows('SELECT id FROM sections WHERE book_id=?', (bid,))
    assert ingest.import_file('renamed.txt', raw) == (bid, False)
    assert s.one('SELECT format FROM books WHERE id=?', (bid,))['format'] == 'text'
    assert s.all_rows('SELECT id FROM sections WHERE book_id=?', (bid,)) == before
    md, created = ingest.import_file('same.md', raw)
    assert created and md != bid
    assert ingest.import_file('same.md', raw) == (md, False)
