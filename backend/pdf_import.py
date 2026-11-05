"""Local PDF structure extraction. Page IDs remain stable when re-importing."""
from __future__ import annotations

import io
import re
from pypdf import PdfReader


def outline_entries(reader):
    entries = []

    def walk(items, depth=0, parent=None):
        last = parent
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1, last)
                continue
            try:
                page = reader.get_destination_page_number(item)
                title = re.sub(r'\s+', ' ', str(item.title)).strip()
            except (ValueError, KeyError, AttributeError, TypeError):
                continue
            if page is None or not 0 <= page < len(reader.pages) or not title:
                continue
            last = len(entries)
            entries.append({'title': title, 'page': page + 1, 'depth': depth, 'parent': parent})

    walk(reader.outline)
    # Explicit Part containers contain chapters; ordinary root bookmarks are chapters.
    part = re.compile(r'^(第.{1,12}(?:部分|部|篇)|part\s+[\divx]+\b)', re.I)
    for index, entry in enumerate(entries):
        chain, current = [], index
        while current is not None:
            chain.append(current)
            current = entries[current]['parent']
        chain.reverse()
        chosen = chain[0]
        for ancestor in chain:
            chosen = ancestor
            if not part.match(entries[ancestor]['title']):
                break
        entry['chapter'] = entries[chosen]['title']
    return entries


def paragraphs(layout, headings):
    """Keep PDF vertical paragraph gaps; join wrapped lines without flattening blocks."""
    normalized = lambda value: re.sub(r'\s+', '', value)
    def is_heading(text):
        return any(normalized(text).endswith(normalized(h['title'])) and len(normalized(text)) <= len(normalized(h['title'])) + 12 for h in headings)
    lines = []
    for line in layout.splitlines():
        if line.strip() and is_heading(line):
            lines.extend(['', line, ''])
        elif re.match(r'^\s*[•●▪]\s*', line):
            lines.extend(['', re.sub(r'^\s*[•●▪]\s*', '- ', line)])
        else:
            lines.append(line)
    # Standalone page numerals at the edge are furniture, not prose.
    nonempty = [i for i, line in enumerate(lines) if line.strip()]
    for i in (nonempty[:1] + nonempty[-1:]):
        if re.fullmatch(r'(?:\d+|[ivxlcdm]+)', lines[i].strip(), re.I):
            lines[i] = ''
    blocks = re.split(r'\n\s*\n', '\n'.join(lines))
    result = []
    for block in blocks:
        parts = [line.strip() for line in block.splitlines() if line.strip()]
        if not parts:
            continue
        # Preserve obvious table columns instead of running cells into prose.
        if sum(bool(re.search(r'\S\s{3,}\S', line.strip())) for line in block.splitlines()) >= 2:
            result.append('```text\n' + '\n'.join(line.rstrip() for line in block.splitlines()) + '\n```')
            continue
        text = parts[0]
        for line in parts[1:]:
            if re.search(r'[\u3400-\u9fff，。；：！？、）]$', text) or re.match(r'^[\u3400-\u9fff，。；：！？、）]', line):
                text += line
            else:
                text += ' ' + line
        match = next((h for h in headings if normalized(text).endswith(normalized(h['title'])) and len(normalized(text)) <= len(normalized(h['title'])) + 12), None)
        result.append(('## ' if match else '') + text)
    return '\n\n'.join(result)


def parse_pdf(raw, title, language='zh', hosted=False):
    reader = PdfReader(io.BytesIO(raw))
    en = language == 'en'
    if reader.is_encrypted:
        raise ValueError('请先解除 PDF 的密码保护再导入。')
    if hosted and len(reader.pages) > 200:
        raise ValueError('在线版单份 PDF 最多 200 页，请拆分后导入。 / Online PDFs support up to 200 pages.')
    if len(reader.pages) > 600:
        raise ValueError('体验版单份 PDF 最多 600 页，请先拆分。')
    if not reader.pages:
        raise ValueError('没有可阅读内容')
    try:
        outline = outline_entries(reader)
    except (ValueError, KeyError, TypeError, RecursionError):
        outline = []  # Broken bookmarks must not prevent readable pages from importing.
    by_page = {}
    for entry in outline:
        by_page.setdefault(entry['page'], []).append(entry)
    pages, missing, text_pages = [], 0, 0
    chapter = 'Front matter' if en else '封面与目录'
    for number, page in enumerate(reader.pages, 1):
        headings = by_page.get(number, [])
        if headings:
            chapter = min(headings, key=lambda x: x['depth'])['chapter']
        # Layout mode already extracts text. Avoid a second font/content-stream pass.
        try:
            raw_text = page.extract_text(extraction_mode='layout') or ''
        except Exception:
            raw_text = page.extract_text() or ''
        if not raw_text.strip():
            raw_text = page.extract_text() or ''
        contents = page.get_contents()
        painting = {b'S', b's', b'f', b'F', b'f*', b'B', b'B*', b'b', b'b*', b'Do', b'sh',
                    b'Tj', b'TJ', b"'", b'"', b'INLINE IMAGE'}
        blank = not raw_text.strip() and not page.get('/Annots') and (
            contents is None or not any(op in painting for _, op in contents.operations))
        if raw_text.strip():
            text_pages += 1
            content = paragraphs(raw_text, headings)
        elif blank:
            content = '*Blank page in the original PDF.*' if en else '*原书空白页。*'
        else:
            missing += 1
            content = '*This page has no extractable text. View the original PDF.*' if en else '*本页没有可提取文字，请查看原版 PDF。*'
        label = ('Page ' if en else '第 ') + str(number) + ('' if en else ' 页')
        name = ' · '.join(x['title'] for x in headings if x['depth'] == min(h['depth'] for h in headings)) if headings else label
        pages.append({'page': number, 'chapter': chapter if outline else title, 'title': name,
                      'content': content, 'blank': blank, 'missing': not blank and not raw_text.strip()})
    if hosted and not text_pages:
        raise ValueError('这份 PDF 没有可提取文字；暂不支持扫描件或 OCR。 / Scanned PDFs and OCR are not supported yet.')
    return pages, outline, missing
