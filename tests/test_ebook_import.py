import asyncio
import os
import re
import shutil
import struct
import pytest
from fastapi.testclient import TestClient
from backend import app as web, store as s, ingest, agent
from ebook_samples import epub, mobi, png


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'DATA',tmp_path)
    monkeypatch.setattr(ingest,'DATA',tmp_path)
    monkeypatch.setattr(web,'load_dotenv',lambda *a,**k:None)
    monkeypatch.setattr(web,'seed',lambda _:None)
    with TestClient(web.app) as c:
        yield c


def imported(c,name,raw):
    r=c.post('/api/import',files={'file':(name,raw)});assert r.status_code==200,r.text
    b=c.get('/api/books/'+r.json()['id']).json()
    sections=[c.get('/api/sections/'+x['id']).json() for x in b['sections']]
    return b,sections


@pytest.mark.parametrize('version',[2,3])
def test_epub_order_images_links_and_roundtrip(client,version):
    raw=epub(version);b,sections=imported(client,'测试.EPUB',raw)
    assert b['title']=='Agent 阅读测试 / Reading test' and b['format']=='epub'
    assert len(sections)==4
    assert 'FIRST-CHAPTER' in sections[0]['content']
    assert 'SECOND-CHAPTER' in sections[2]['content']
    assert 'FOOTNOTE-END' in sections[3]['content']
    assert b['outline'][1]['parent']==0 and b['outline'][1]['section_id']==sections[1]['id']
    assert '/section/'+sections[3]['id'] in sections[1]['content']
    assert '/section/'+sections[1]['id'] in sections[3]['content']
    assert 'window.BAD_IMPORT' not in ''.join(x['content'] for x in sections)
    assert '| 模型 | 选择 |' in sections[1]['content']
    image=re.search(r'(/api/books/[^)]+)',sections[0]['content'])[1]
    response=client.get(image);assert response.status_code==200 and response.content==png()
    assert response.headers['content-type']=='image/png'
    assert 'no-store' in response.headers['cache-control']
    sid=sections[1]['id']
    assert client.put(f'/api/books/{b["id"]}/position',json={'section_id':sid}).status_code==200
    note=client.post(f'/api/books/{b["id"]}/artifacts',json={'kind':'note','title':'记录','content':'重导保留','section_id':sid}).json()
    again=client.post('/api/import',files={'file':('renamed.epub',raw)}).json()
    assert again=={'id':b['id'],'created':False}
    assert client.get(f'/api/books/{b["id"]}/artifacts').json()[0]['id']==note['id']


@pytest.mark.parametrize('extra',[
 {'META-INF/container.xml':b'<broken'},
 {'META-INF/container.xml':b'<!DOCTYPE x [<!ENTITY test SYSTEM "file:///etc/passwd">]><x>&test;</x>'},
 {'OPS/two.xhtml':None},
 {'../../escape.txt':b'no'},
 {'META-INF/encryption.xml':b'<encryption><EncryptedData><CipherReference URI="OPS/one.xhtml"/></EncryptedData></encryption>'},
])
def test_invalid_epub_is_atomic(client,extra):
    before=client.get('/api/books').json()
    r=client.post('/api/import',files={'file':('broken.epub',epub(extra=extra))})
    assert r.status_code==422,r.text
    assert client.get('/api/books').json()==before


def test_external_and_missing_images_do_not_fetch_network(client):
    raw=epub(extra={'OPS/one.xhtml':b'<html><body><h1>Images</h1><p>Readable text</p><img src="https://example.invalid/private"/><img src="missing.png"/></body></html>'})
    b,sections=imported(client,'images.epub',raw)
    assert b['warnings'] and '[Illustration:' in sections[0]['content']
    assert 'https://example.invalid' not in sections[0]['content']


def test_drm_mobi_rejected_before_conversion(client):
    raw=bytearray(mobi());struct.pack_into('>H',raw,96+12,2)
    r=client.post('/api/import',files={'file':('encrypted.mobi',bytes(raw))})
    assert r.status_code==422 and 'DRM' in r.json()['detail']


def test_mobi_real_conversion(client):
    if not (os.getenv('READING_MOBITOOL') or shutil.which('mobitool')):pytest.skip('libmobi required')
    b,sections=imported(client,'原创.mobi',mobi())
    assert b['format']=='mobi' and 'MOBI-ORIGINAL-END' in ''.join(x['content'] for x in sections)


def test_div_paragraphs_stay_separate(client):
    raw=epub(extra={'OPS/one.xhtml': b'<html><body><div>First paragraph.</div><div><span>Second paragraph.</span></div></body></html>'})
    _,rows=imported(client,'paragraphs.epub',raw)
    assert 'First paragraph.\n\nSecond paragraph.' in rows[0]['content']


def test_expansion_limit_is_checked_before_reading(monkeypatch):
    from backend import ebook_import as ebooks
    monkeypatch.setattr(ebooks,'MAX_EXPANDED',100)
    with pytest.raises(ValueError,match='Expanded ebook'):ebooks.parse_epub(epub(),'sample','book-id')
