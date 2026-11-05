"""Original deterministic ebook fixtures; no downloaded books required."""
import io
import struct
import zipfile
import zlib


def png():
    def chunk(name, data):return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
    width, height = 480, 140
    pixels = b''.join(b'\x00' + b''.join(bytes((43, 99, 112) if 20 < x < 210 and 20 < y < 120 else (204, 151, 74) if 270 < x < 460 and 20 < y < 120 else (244, 247, 248)) for x in range(width)) for y in range(height))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')


def epub(version=3, extra=None):
    files = {
        'mimetype': b'application/epub+zip',
        'META-INF/container.xml': b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'OPS/book.opf': f'''<package xmlns="http://www.idpf.org/2007/opf" version="{version}.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Agent 阅读测试 / Reading test</dc:title><dc:identifier id="id">original-qa-book</dc:identifier><dc:language>zh</dc:language></metadata><manifest><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="notes" href="notes.xhtml" media-type="application/xhtml+xml"/><item id="pic" href="images/diagram.png" media-type="image/png"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest><spine toc="ncx"><itemref idref="one"/><itemref idref="two"/><itemref idref="notes" linear="no"/></spine></package>'''.encode(),
        'OPS/nav.xhtml': b'<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol><li><a href="one.xhtml#start">1. Tools</a><ol><li><a href="one.xhtml#example">Example</a></li></ol></li><li><a href="two.xhtml">2. Memory</a></li></ol></nav></body></html>',
        'OPS/toc.ncx': b'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap><navPoint id="one"><navLabel><text>1. Tools</text></navLabel><content src="one.xhtml#start"/><navPoint id="example"><navLabel><text>Example</text></navLabel><content src="one.xhtml#example"/></navPoint></navPoint><navPoint id="two"><navLabel><text>2. Memory</text></navLabel><content src="two.xhtml"/></navPoint></navMap></ncx>',
        'OPS/one.xhtml': '''<html><body><section><h1 id="start">第一章 工具调用</h1><p>模型负责选择工具，软件执行并返回结果。FIRST-CHAPTER。</p><img src="images/diagram.png" alt="模型与工具示意图"/><h2 id="example">一个简单例子</h2><p id="reference">查询天气后再决定是否带伞。<a href="notes.xhtml#note">查看脚注</a></p><pre><code># 注释不是目录\nprint("hello")</code></pre><table><tr><th>角色</th><th>工作</th></tr><tr><td>模型</td><td>选择</td></tr></table><script>window.BAD_IMPORT=true</script><iframe src="https://example.invalid/private"></iframe></section></body></html>'''.encode(),
        'OPS/two.xhtml': '<html><body><h1>第二章 记忆</h1><p>保存已经得到的结果，避免反复询问。SECOND-CHAPTER。</p></body></html>'.encode(),
        'OPS/notes.xhtml': '<html><body><aside id="note"><p>脚注：工具调用可能失败，需要检查返回结果。FOOTNOTE-END。 <a href="one.xhtml#reference">返回正文</a></p></aside></body></html>'.encode(),
        'OPS/images/diagram.png': png(),
    }
    if version == 2:files['OPS/book.opf'] = files['OPS/book.opf'].replace(b' properties="nav"', b'')
    if extra:files.update(extra)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, data in files.items():
            if data is not None:z.writestr(path, data)
    return output.getvalue()


def mobi():
    """Minimal uncompressed MOBI6 with original UTF-8 HTML."""
    html = '<html><head><title>Original MOBI</title></head><body><h1>工具调用 / Tools</h1><p>模型选择工具。MOBI-ORIGINAL-END。</p></body></html>'.encode()
    title = b'Original MOBI QA'
    header = bytearray(232);header[:4] = b'MOBI'
    def word(offset, value):struct.pack_into('>I', header, offset, value)
    for offset, value in [(4,232),(8,2),(12,65001),(16,123456),(20,6),(64,248),(68,len(title)),(76,9),(88,0xffffffff),(92,0xffffffff),(112,0),(152,0xffffffff),(228,0xffffffff)]:word(offset,value)
    # Index pointers are absent, not record zero.
    for offset in range(24,64,4):word(offset,0xffffffff)
    record0 = struct.pack('>HHIHHHH',1,0,len(html),1,4096,0,0) + header + title
    palm = bytearray(78);palm[:len(title)] = title;palm[60:68] = b'BOOKMOBI';struct.pack_into('>H',palm,76,2)
    return bytes(palm) + struct.pack('>II',96,0) + struct.pack('>II',96+len(record0),1) + b'\x00\x00' + record0 + html
