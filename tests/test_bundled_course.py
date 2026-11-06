import hashlib
from pathlib import Path
import re
import pytest
from backend import store as s, bundled_course as course, ingest


def test_fixed_revision_files_order_and_code_math(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'DATA',tmp_path);s.init()
    manifest,files=course.load_manifest()
    assert manifest['revision']=='8cfcf5a4047f32270e07d5e60fcb98205de37fc0'
    assert len(manifest['chapters'])==19
    assert [int(Path(n).name[:2]) for n in manifest['chapters']]==list(range(1,20))
    assert all(hashlib.sha256((course.COURSE_DIR/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items())
    bid,created=course.seed_course();assert created
    sections=s.all_rows('SELECT * FROM sections WHERE book_id=? ORDER BY ordinal',(bid,))
    assert len(sections)==244
    chapters=list(dict.fromkeys(x['chapter'] for x in sections))
    assert chapters[:19]==[files[n].splitlines()[0].lstrip('# ').strip() for n in manifest['chapters']]
    body='\n'.join(x['content'] for x in sections)
    for name in manifest['chapters']:
        for block in re.findall(r'(?ms)^```.*?^```',files[name]):assert block in body
        for formula in re.findall(r'(?s)\$\$.*?\$\$',files[name]):assert formula in body
    assert '非官方' in body and '不为第三方材料重新指定许可' in body
    assert course.seed_course()==(bid,False)
    ingest.seed();assert s.one('SELECT COUNT(*) n FROM books')['n']==1


def test_all_cross_links_resolve_to_same_book_and_code_is_unchanged(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'DATA',tmp_path);s.init();bid,_=course.seed_course()
    rows=s.all_rows('SELECT id,content FROM sections WHERE book_id=?',(bid,));ids={r['id'] for r in rows}
    links=[]
    for row in rows:
        links.extend(re.findall(r'\]\(/section/([a-f0-9]+)\)',row['content']))
        for ordinary,part in course.prose_parts(row['content']):
            if ordinary:assert not re.search(r'\]\((?!https?://|/section/|mailto:)[^)]*\.md',part)
    assert len(links)==32 and set(links)<=ids
    assert any('/tree/'+course.load_manifest()[0]['revision']+'/exercises)' in r['content'] for r in rows)
    assert any('配套代码架构导读' in r['content'] for r in rows if r['id'] in links)


def test_hash_mismatch_fails_before_writing(tmp_path,monkeypatch):
    import shutil
    root=tmp_path/'bundle';shutil.copytree(course.COURSE_DIR,root)
    (root/'01-Agent基础与全景.md').write_text('changed')
    monkeypatch.setattr(course,'COURSE_DIR',root);monkeypatch.setattr(s,'DATA',tmp_path/'data');s.init()
    with pytest.raises(RuntimeError,match='checksum'):course.seed_course()
    assert s.one('SELECT COUNT(*) n FROM books')['n']==0
