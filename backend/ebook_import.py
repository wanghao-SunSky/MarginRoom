"""Bounded EPUB reading and MOBI conversion; content is data, never executable HTML."""
from __future__ import annotations
import hashlib
import io
import json
import os
import posixpath
import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit
from bs4 import BeautifulSoup
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from markdownify import markdownify
from . import store as s

MAX_EXPANDED = 60 * 1024**2
MAX_ASSETS = 20 * 1024**2
MAX_TEXT = 2_000_000


def local_path(base, href):
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or '\\' in href or '\x00' in href:
        return None
    path = unquote(parsed.path)
    if path.startswith('/'):
        return None
    path = posixpath.normpath(posixpath.join(posixpath.dirname(base), path)) if path else base
    if path == '..' or path.startswith('../'):
        return None
    return path, unquote(parsed.fragment)


def xml(raw):
    # DTD declarations in older EPUBs are common, but entities are never resolved.
    return ET.fromstring(raw)


def convert_mobi(raw, suffix):
    if len(raw) < 86 or raw[60:68] != b'BOOKMOBI':
        raise ValueError('不是有效的 MOBI/AZW3 文件。 / Invalid MOBI/AZW3 file.')
    offset = struct.unpack_from('>I', raw, 78)[0]
    if offset + 16 > len(raw):
        raise ValueError('MOBI 文件不完整。 / Incomplete MOBI file.')
    if struct.unpack_from('>H', raw, offset + 12)[0]:
        raise ValueError('这本书受 DRM 加密保护，请导入未加密版本。 / Please import a DRM-free edition.')
    command = os.getenv('READING_MOBITOOL') or shutil.which('mobitool')
    if not command:
        raise ValueError('MOBI 转换组件尚未安装，请先转换为 EPUB。 / Install libmobi-tools or import EPUB.')
    with tempfile.TemporaryDirectory(prefix='reading-mobi-') as folder:
        source = Path(folder) / ('book' + suffix)
        source.write_bytes(raw)
        try:
            result = subprocess.run([command, '-e', '-o', folder, str(source)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        except subprocess.TimeoutExpired as exc:
            raise ValueError('MOBI 转换超时，请改用 EPUB。 / Conversion timed out; please use EPUB.') from exc
        output = list(Path(folder).glob('*.epub'))
        if result.returncode or len(output) != 1:
            raise ValueError('MOBI/AZW3 无法转换，请确认文件完整且未加密。 / Cannot convert this ebook; check that it is complete and DRM-free.')
        if output[0].stat().st_size > 30 * 1024**2:
            raise ValueError('转换后的电子书过大。 / Converted ebook is too large.')
        return output[0].read_bytes()


def parse_epub(raw, fallback_title, book_id):
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        entries = archive.infolist()
        if len(entries) > 3000 or sum(x.file_size for x in entries) > MAX_EXPANDED:
            raise ValueError('电子书展开后过大，请拆分后导入。 / Expanded ebook is too large.')
        names = {x.filename for x in entries}
        if len(names) != len(entries):
            raise ValueError('电子书包含重复文件路径。 / Duplicate ebook paths.')
        for entry in entries:
            if entry.flag_bits & 1 or local_path('', entry.filename) is None:
                raise ValueError('电子书包含加密内容或无效路径。 / Encrypted content or invalid ebook path.')
        def read(name):
            if name not in names:
                raise ValueError('电子书缺少正文或资源文件。 / An ebook content/resource file is missing.')
            return archive.read(name)
        container = xml(read('META-INF/container.xml'))
        rootfile = container.find('.//{*}rootfile')
        if rootfile is None:
            raise ValueError('电子书缺少内容清单。 / Missing EPUB package.')
        package_path = local_path('', rootfile.get('full-path', ''))
        if not package_path:
            raise ValueError('电子书目录路径无效。 / Invalid EPUB package path.')
        opf_path = package_path[0]
        package = xml(read(opf_path))
        title_node = package.find('.//{*}metadata/{*}title')
        title = ''.join(title_node.itertext()).strip()[:180] if title_node is not None else fallback_title
        metadata = package.findall('.//{*}metadata/{*}meta')
        if any(x.get('property') == 'rendition:layout' and (x.text or '').strip() == 'pre-paginated' for x in metadata):
            raise ValueError('暂不支持固定版式电子书，请使用 PDF 或流式 EPUB。 / Fixed-layout ebooks are not supported; use PDF or reflowable EPUB.')
        manifest = {}
        for item in package.findall('.//{*}manifest/{*}item'):
            target = local_path(opf_path, item.get('href', ''))
            if target:
                manifest[item.get('id')] = dict(path=target[0], media=item.get('media-type', ''), properties=item.get('properties', '').split())
        # Font obfuscation is allowed; encrypted text/images are not.
        if 'META-INF/encryption.xml' in names:
            for item in xml(read('META-INF/encryption.xml')).findall('.//{*}CipherReference'):
                target = local_path('', item.get('URI', ''))
                resource = next((x for x in manifest.values() if target and x['path'] == target[0]), None)
                if not resource or not ('font' in resource['media'] or resource['path'].lower().endswith(('.otf', '.ttf', '.woff', '.woff2'))):
                    raise ValueError('这本书受 DRM 加密保护，请导入未加密版本。 / Please import a DRM-free edition.')
        nav = []
        nav_item = next((x for x in manifest.values() if 'nav' in x['properties']), None)
        if nav_item:
            soup = BeautifulSoup(read(nav_item['path']), 'html.parser')
            toc = next((x for x in soup.find_all('nav') if 'toc' in x.get('epub:type', '').split() or x.get('role') == 'doc-toc'), None)
            def walk_list(ol, parent=None, depth=0):
                if ol is None or depth > 12:
                    return
                for li in ol.find_all('li', recursive=False):
                    link = li.find('a', href=True)
                    next_parent = parent
                    if link:
                        target = local_path(nav_item['path'], link['href'])
                        if target:
                            next_parent = len(nav)
                            nav.append(dict(title=link.get_text(' ', strip=True)[:180], target=target, parent=parent, depth=depth))
                    walk_list(li.find('ol', recursive=False), next_parent, depth + 1)
            if toc:walk_list(toc.find('ol'))
        if not nav:
            ncx = next((x for x in manifest.values() if x['media'] == 'application/x-dtbncx+xml'), None)
            if ncx:
                def walk_ncx(node, parent=None, depth=0):
                    if depth > 12:return
                    for item in node.findall('{*}navPoint'):
                        label = item.find('{*}navLabel/{*}text'); content = item.find('{*}content')
                        target = local_path(ncx['path'], content.get('src', '')) if content is not None else None
                        if target:
                            index = len(nav)
                            nav.append(dict(title=''.join(label.itertext()).strip()[:180] if label is not None else 'Section', target=target, parent=parent, depth=depth))
                            walk_ncx(item, index, depth + 1)
                navmap = xml(read(ncx['path'])).find('.//{*}navMap')
                if navmap is not None:walk_ncx(navmap)
        spine = package.find('{*}spine')
        if spine is None:raise ValueError('电子书没有阅读顺序。 / Missing reading order.')
        paths = []
        for ref in spine.findall('{*}itemref'):
            item = manifest.get(ref.get('idref'))
            if not item:raise ValueError('电子书正文清单不完整。 / Incomplete EPUB spine.')
            if item['media'] not in ('application/xhtml+xml', 'text/html') or 'nav' in item['properties']:continue
            if item['path'] not in paths:paths.append(item['path'])
        if not paths or len(paths) > 800:raise ValueError('电子书章节为空或过多。 / Missing or excessive ebook chapters.')
        # Split at headings and referenced anchors so notes and TOC links are navigable.
        docs, targets, sections = [], {}, []
        total_text = 0
        source_docs = []
        anchors = {n['target'] for n in nav}
        for path in paths:
            soup = BeautifulSoup(read(path), 'html.parser')
            for tag in soup(['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'link', 'meta', 'head', 'noscript']):tag.decompose()
            body = soup.body or soup
            total_text += len(body.get_text())
            if total_text > MAX_TEXT:raise ValueError('电子书文字过多，请拆分后导入。 / Please split this large ebook.')
            for link in body.find_all('a', href=True):
                target = local_path(path, link['href'])
                if target:anchors.add(target)
            source_docs.append((path, body))
        for path, body in source_docs:
            entry = next((n for n in nav if n['target'][0] == path), None)
            heading = body.find(['h1', 'h2', 'h3'])
            chapter = entry['title'] if entry else (heading.get_text(' ', strip=True)[:180] if heading else (body.get_text(' ', strip=True)[:48] or Path(path).stem))
            pieces = []
            def flatten(node, inherited=()):
                ids = tuple(inherited) + ((node.get('id'),) if getattr(node, 'attrs', None) and node.get('id') else ())
                if getattr(node, 'name', None) in ('[document]', 'body', 'div', 'section', 'article', 'main', 'aside') and any(getattr(x, 'name', None) in ('div', 'section', 'article', 'main', 'aside', 'p', 'h1', 'h2', 'h3', 'pre', 'table', 'ul', 'ol', 'blockquote', 'figure') for x in node.contents):
                    children = [x for x in node.contents if str(x).strip()]
                    for i, child in enumerate(children):flatten(child, ids if i == 0 else ())
                else:pieces.append((node, ids))
            flatten(body)
            current = None
            for node, ids in pieces:
                child_ids = [x['id'] for x in node.find_all(attrs={'id': True})] if hasattr(node, 'find_all') else []
                all_ids = list(ids) + child_ids
                is_heading = getattr(node, 'name', None) in ('h1', 'h2', 'h3')
                boundary = is_heading or any((path, key) in anchors for key in ids)
                if current is None or (boundary and current['html'] and (is_heading or current['body_started'])):
                    nav_entry = next((n for n in nav if n['target'][0] == path and n['target'][1] in ids), None)
                    name = nav_entry['title'] if nav_entry else (node.get_text(' ', strip=True)[:180] if getattr(node, 'name', None) in ('h1', 'h2', 'h3') else chapter)
                    current = dict(id=s.uid(), title=name, chapter=chapter, ordinal=len(sections), content='', html=[], body_started=False)
                    sections.append(current)
                    targets.setdefault((path, ''), current['id'])
                    docs.append((path, current))
                current['html'].append(str(node))
                if not is_heading:current['body_started'] = True
                for key in all_ids:targets[(path, key)] = current['id']
        if len(sections) > 2000:raise ValueError('电子书分节过多。 / Too many ebook sections.')
        docs = [(path, BeautifulSoup(''.join(section.pop('html')), 'html.parser')) for path, section in docs]
        assets, warnings = {}, set()
        asset_size = 0
        for (path, body), section in zip(docs, sections):
            for image in body.find_all(['img', 'image']):
                src = image.get('src') or image.get('href') or image.get('xlink:href') or ''
                target = local_path(path, src)
                content = read(target[0]) if target and target[0] in names else b''
                mime = ('image/png' if content.startswith(b'\x89PNG\r\n\x1a\n') else
                        'image/jpeg' if content.startswith(b'\xff\xd8\xff') else
                        'image/gif' if content[:6] in (b'GIF87a', b'GIF89a') else
                        'image/webp' if content[:4] == b'RIFF' and content[8:12] == b'WEBP' else None)
                if mime and len(content) <= 5 * 1024**2:
                    name = hashlib.sha256(content).hexdigest()
                    if name not in assets:
                        asset_size += len(content)
                        if asset_size > MAX_ASSETS:raise ValueError('电子书图片过大，请压缩后导入。 / Ebook images exceed the size limit.')
                        assets[name] = (mime, content)
                    image.name = 'img'; image.attrs = {'src': f'/api/books/{book_id}/assets/{name}', 'alt': image.get('alt', '')}
                else:
                    warnings.add('部分图片未能显示（缺失、外链或不支持的格式）。 / Some images are missing, external, or unsupported.')
                    image.replace_with('[Illustration: ' + (image.get('alt') or 'unavailable') + ']')
            for link in body.find_all('a'):
                href = link.get('href', ''); target = local_path(path, href)
                sid = targets.get(target) or (targets.get((target[0], '')) if target else None)
                if sid:link['href'] = '/section/' + sid
                elif urlsplit(href).scheme not in ('https', 'http', 'mailto'):link.attrs.pop('href', None)
            for tag in body.find_all(['svg', 'math']):
                if tag.name == 'math':
                    alt = tag.get('alttext') or tag.get_text(' ', strip=True)
                    tag.replace_with(' ' + alt + ' ')
                    warnings.add('部分数学公式按文字显示。 / Some mathematical notation is shown as text.')
                elif not tag.find('img'):
                    warnings.add('部分矢量插图未能显示。 / Some vector illustrations are unsupported.')
                    tag.replace_with('[Vector illustration]')
                else:
                    for child in list(tag.contents):tag.insert_before(child.extract())
                    tag.decompose()
            section['content'] = markdownify(str(body), heading_style='ATX', bullets='-', escape_underscores=True).strip()
        if not any(x['content'].strip() for x in sections):raise ValueError('没有可阅读内容。 / No readable content.')
        outline, index_map = [], {}
        for index, entry in enumerate(nav):
            target = entry['target'];sid = targets.get(target) or targets.get((target[0], ''))
            if not sid:continue
            parent = entry['parent']
            while parent is not None and parent not in index_map:parent = nav[parent]['parent']
            mapped = index_map.get(parent);index_map[index] = len(outline)
            outline.append(dict(title=entry['title'], section_id=sid, parent=mapped, depth=(outline[mapped]['depth'] + 1 if mapped is not None else 0)))
        seen = {x['section_id'] for x in outline}
        for section in sections:
            if section['id'] not in seen:outline.append(dict(title=section['title'], section_id=section['id'], parent=None, depth=0))
        return title or fallback_title, sections, outline, assets, sorted(warnings)
    except (zipfile.BadZipFile, ET.ParseError, DefusedXmlException, KeyError, UnicodeError, RuntimeError, RecursionError) as exc:
        raise ValueError('EPUB 无法解析，请确认文件完整。 / Invalid or incomplete EPUB.') from exc


def import_ebook(filename, raw, language='zh'):
    suffix = Path(filename).suffix.lower()
    digest = hashlib.sha256(suffix.encode() + b'\x00' + raw).hexdigest()
    old = s.one('SELECT id FROM books WHERE content_hash=?', (digest,))
    if old:return old['id'], False
    bid = s.uid()
    epub = raw if suffix == '.epub' else convert_mobi(raw, suffix)
    title, sections, outline, assets, warnings = parse_epub(epub, Path(filename).stem, bid)
    with s.db() as c:
        old = c.execute('SELECT id FROM books WHERE content_hash=?', (digest,)).fetchone()
        if old:return old['id'], False
        subtitle = f'{suffix[1:].upper()} · {len(sections)} ' + ('sections' if language == 'en' else '节')
        c.execute('INSERT INTO books VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (bid, title, subtitle, suffix[1:], None, filename, 'teal', digest, s.now(), 0))
        for section in sections:
            c.execute('INSERT INTO sections VALUES(?,?,?,?,?,?,?)',
                      (section['id'], bid, section['chapter'], section['title'], section['ordinal'], section['content'], None))
        c.execute('INSERT INTO ebook_documents VALUES(?,?,?)', (bid, json.dumps(outline, ensure_ascii=False), json.dumps(warnings, ensure_ascii=False)))
        for name, (mime, content) in assets.items():c.execute('INSERT INTO book_assets VALUES(?,?,?,?)', (bid, name, mime, content))
    return bid, True
