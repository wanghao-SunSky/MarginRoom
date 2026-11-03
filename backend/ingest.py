from __future__ import annotations
import hashlib
import re
from pathlib import Path
from .store import db, uid, now, DATA, ROOT


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


def import_file(filename: str, raw: bytes, language: str = 'zh'):
    suffix = Path(filename).suffix.lower()
    if suffix not in {'.md', '.txt', '.pdf'}:
        raise ValueError('这版支持 Markdown、TXT 和 PDF。')
    if not raw:
        raise ValueError('文件为空')
    digest = hashlib.sha256(raw).hexdigest()
    title = Path(filename).stem[:180]
    missing = 0
    if suffix == '.pdf':
        import io
        from pypdf import PdfReader
        try:
            pdf = PdfReader(io.BytesIO(raw))
            if pdf.is_encrypted:
                raise ValueError('请先解除 PDF 的密码保护再导入。')
            if len(pdf.pages) > 600:
                raise ValueError('体验版单份 PDF 最多 600 页，请先拆分。')
            pieces = []
            for i, page in enumerate(pdf.pages):
                txt = page.extract_text() or ''
                if not txt.strip():
                    missing += 1
                    txt = ('No text could be extracted from this page. View the original PDF; the AI cannot read this page.' if language=='en' else '这一页未提取到文本。请切换到原版 PDF 查看；AI 无法读取本页内容。')
                pieces.append((f'Page {i+1}' if language=='en' else f'第 {i+1} 页', txt, i+1))
        except ValueError:
            raise
        except Exception as e:
            raise ValueError('PDF 无法解析，请确认文件完整且未加密。') from e
        DATA.mkdir(parents=True, exist_ok=True)
        path = DATA / f'{digest}.pdf'
        path.write_bytes(raw)
        return add_book(title, (f'Imported PDF · {len(pieces)} pages' if language=='en' else f'导入的 PDF · {len(pieces)} 页'), 'pdf', filename, digest, [(title,pieces)], str(path), 'plum', missing)
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as e:
        raise ValueError('文本需为 UTF-8 编码，请转换后重试。') from e
    if not text.strip():raise ValueError('没有可阅读内容')
    pieces=markdown_sections(text,title)
    # A Markdown book may use one title followed by level-2 chapter headings.
    levels=[len(re.match(r'^(#{1,3})\s', content)[1]) if re.match(r'^(#{1,3})\s',content) else 0 for _,content in pieces]
    chapter_level=1 if levels.count(1)>1 else (2 if levels.count(2)>1 else 0)
    chapters=[]; current=title; group=[]
    for (name,content),level in zip(pieces,levels):
        if chapter_level and level==chapter_level:
            if group:chapters.append((current,group))
            current=name;group=[]
        group.append((name,content,None))
    if group:chapters.append((current,group))
    return add_book(title,'Imported reading material' if language=='en' else '我的阅读资料','markdown',filename,digest,chapters,color='gold')
