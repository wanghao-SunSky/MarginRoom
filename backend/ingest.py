from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
from .store import db, uid, now, DATA, ROOT, data_dir


def markdown_sections(text: str, chapter: str):
    chunks, title, lines, fence = [], chapter, [], None
    for line in text.splitlines():
        marker=re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$',line)
        if fence:
            if marker and marker[1][0]==fence[0] and len(marker[1])>=fence[1] and not marker[2].strip():fence=None
        elif marker:fence=(marker[1][0],len(marker[1]))
        heading = re.match(r'^(#{1,3})\s+(.+?)\s*#*$', line) if not fence else None
        if heading:
            if '\n'.join(lines).strip():
                chunks.append((title, '\n'.join(lines).strip()))
            title = heading[2]
            lines = [line]
        else:
            lines.append(line)
    if '\n'.join(lines).strip():
        chunks.append((title, '\n'.join(lines).strip()))
    return chunks or [(chapter, text)]


def add_book(title, subtitle, fmt, source, digest, chapters, file_path=None, color='teal', missing=0):
    with db() as c:
        old = c.execute('SELECT id FROM books WHERE content_hash=?', (digest,)).fetchone()
        if old:
            return old['id'], False
        bid, ordinal = uid(), 0
        insert=c.execute('INSERT OR IGNORE INTO books VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (bid, title, subtitle, fmt, file_path, source, color, digest, now(), missing))
        if not insert.rowcount:
            return c.execute('SELECT id FROM books WHERE content_hash=?',(digest,)).fetchone()['id'],False
        for chapter, pieces in chapters:
            for name, content, page in pieces:
                c.execute('INSERT INTO sections VALUES(?,?,?,?,?,?,?)', (uid(), bid, chapter, name, ordinal, content, page))
                ordinal += 1
        if not ordinal:
            raise ValueError('没有可阅读内容')
        return bid, True


def seed(workspace: Path | None = None):
    """Seed only redistributable examples shipped with the app.

    The legacy workspace parameter is retained for callers, but deliberately
    ignored: startup must never collect private sibling folders for a release.
    Existing imported documents and reading records are left unchanged.
    """
    for name, language in [('reading-demo.en.md','en'),('reading-demo.zh.md','zh')]:
        path=ROOT/'examples'/name
        if path.is_file():
            bid,created=import_file(name,path.read_bytes(),language)
            if created:
                title='Reading with AI' if language=='en' else '和 AI 一起阅读'
                subtitle='Original quick-start sample' if language=='en' else '原创上手示例'
                with db() as c:c.execute('UPDATE books SET title=?,subtitle=? WHERE id=?',(title,subtitle,bid))
            # Exact shipped fingerprints, never a title match: a reader may
            # import their own document with the same name. Preserve old IDs
            # and text so notes, conversations and exported citations still work.
            legacy_hash = {
                'en':'0262ef5324f3158271283a4fc4e218d153e08a12d3998cbeb61d5f2e2c7d3c27',
                'zh':'66fd1979113a454cdb936a12c609222c73b312dbc24994befc1711fde6c250d1',
            }[language]
            with db() as c:
                old=c.execute('SELECT id FROM books WHERE source=? AND content_hash=? AND id<>?',(name,legacy_hash,bid)).fetchone()
                if old:
                    c.execute('INSERT OR REPLACE INTO example_replacements VALUES(?,?)',(old['id'],bid))
                    c.execute('UPDATE books SET title=?,subtitle=? WHERE id=?',(
                        'Previous getting-started sample' if language=='en' else '旧版入门示例',
                        'Your notes and conversations are preserved' if language=='en' else '已保留原文、笔记与讨论',old['id']))


def import_file(filename: str, raw: bytes, language: str = 'zh'):
    suffix = Path(filename).suffix.lower()
    if suffix not in {'.md', '.txt', '.pdf', '.epub', '.mobi', '.azw3'}:
        raise ValueError('支持 PDF、EPUB、MOBI、AZW3、Markdown 和 TXT。 / Supported: PDF, EPUB, MOBI, AZW3, Markdown and TXT.')
    if not raw:
        raise ValueError('文件为空')
    if suffix in {'.epub', '.mobi', '.azw3'}:
        from .ebook_import import import_ebook
        return import_ebook(filename, raw, language)
    digest = hashlib.sha256(raw).hexdigest()
    title = Path(filename).stem[:180]
    missing = 0
    if suffix == '.pdf':
        from .pdf_import import parse_pdf
        try:
            pages, outline, missing = parse_pdf(raw, title, language)
        except (ValueError, MemoryError):
            raise
        except Exception as exc:
            raise ValueError('PDF 无法解析，请确认文件完整且未加密。') from exc
        directory = DATA
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{digest}.pdf'
        path.write_bytes(raw)
        with db() as c:
            old = c.execute('SELECT id FROM books WHERE content_hash=?', (digest,)).fetchone()
            bid = old['id'] if old else uid()
            if old and c.execute("SELECT 1 FROM runs WHERE book_id=? AND status='running'", (bid,)).fetchone():
                raise ValueError('这本书正在回答问题，请回答结束后再整理。 / Please wait for the current answer before re-importing.')
            if not old:
                subtitle = f'Imported PDF · {len(pages)} pages' if language == 'en' else f'导入的 PDF · {len(pages)} 页'
                c.execute('INSERT INTO books VALUES(?,?,?,?,?,?,?,?,?,?)',
                          (bid, title, subtitle, 'pdf', str(path), filename, 'plum', digest, now(), missing))
            existing = {r['page']: r['id'] for r in c.execute('SELECT id,page FROM sections WHERE book_id=?', (bid,))}
            if old and set(existing) != {p['page'] for p in pages}:
                raise ValueError('原有页码与文件不一致，未修改已有阅读记录。 / Existing page mapping differs; reading records were kept unchanged.')
            ids = {}
            for ordinal, p in enumerate(pages):
                sid = existing.get(p['page'], uid())
                ids[p['page']] = sid
                if p['page'] in existing:
                    c.execute('UPDATE sections SET chapter=?,title=?,content=? WHERE id=?',
                              (p['chapter'], p['title'], p['content'], sid))
                else:
                    c.execute('INSERT INTO sections VALUES(?,?,?,?,?,?,?)',
                              (sid, bid, p['chapter'], p['title'], ordinal, p['content'], p['page']))
            for entry in outline:
                entry['section_id'] = ids[entry['page']]
            c.execute('UPDATE books SET missing_pages=? WHERE id=?', (missing, bid))
            c.execute('INSERT OR REPLACE INTO pdf_documents VALUES(?,?,?,?,?)',
                      (bid, 1, json.dumps(outline, ensure_ascii=False),
                       json.dumps([p['page'] for p in pages if p['blank']]),
                       json.dumps([p['page'] for p in pages if p['missing']])))
        return bid, not bool(old)
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as e:
        raise ValueError('文本需为 UTF-8 编码，请转换后重试。') from e
    if '\x00' in text:
        raise ValueError('文件包含二进制空字符，请导出为 UTF-8 文本后重试。 / Please export this file as UTF-8 text.')
    if not text.strip():raise ValueError('没有可阅读内容')
    if suffix == '.txt':
        # Keep old record IDs; new text files have a separate rendering identity.
        with db() as c:
            legacy = c.execute('SELECT id,source FROM books WHERE content_hash=?', (digest,)).fetchone()
            if legacy and Path(legacy['source']).suffix.lower() == '.txt':
                c.execute("UPDATE books SET format='text' WHERE id=?", (legacy['id'],))
                return legacy['id'], False
        digest = hashlib.sha256(b'text\x00' + raw).hexdigest()
        return add_book(title,'Imported reading material' if language=='en' else '我的阅读资料',
                        'text',filename,digest,[(title,[(title,text,None)])],color='gold')
    with db() as c:
        legacy = c.execute('SELECT source FROM books WHERE content_hash=?', (digest,)).fetchone()
        if legacy and Path(legacy['source']).suffix.lower() == '.txt':
            digest = hashlib.sha256(b'markdown\x00' + raw).hexdigest()
    pieces=markdown_sections(text,title)
    # A Markdown book may use one title followed by level-2 chapter headings.
    levels=[len(re.match(r'^(#{1,3})\s', content)[1]) if re.match(r'^(#{1,3})\s',content) else 0 for _,content in pieces]
    chapter_level=1 if levels.count(1)>1 else (2 if levels.count(2)>1 else 0)
    chapters=[]; current=title; group=[]
    for (name,content),level in zip(pieces,levels):
        if chapter_level and level==chapter_level:
            if group:chapters.append((current,group))
            current=name;group=[]
        # Keep structural headings for chapter grouping, but do not turn a
        # bare book/chapter heading into a separate, empty reading page.
        if level and not '\n'.join(content.splitlines()[1:]).strip():continue
        group.append((name,content,None))
    if group:chapters.append((current,group))
    return add_book(title,'Imported reading material' if language=='en' else '我的阅读资料','markdown',filename,digest,chapters,color='gold')
