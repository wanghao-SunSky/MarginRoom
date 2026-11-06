"""Pinned, owner-authorized course content. No hosted identity dependencies."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
from urllib.parse import unquote, quote, urlsplit
from . import store as s

GENERATOR_VERSION='cs329z-markdown-v1'
COURSE_DIR=Path(__file__).resolve().parents[1]/'examples/cs329z'
TITLE='CS329Z：AI Agent 工程（中文教程）'


def slug(text):
    # GitHub's heading anchors retain Chinese and remove punctuation.
    text=re.sub(r'<[^>]+>','',text).strip().lower().replace(' ','-')
    return ''.join(c for c in text if c.isalnum() or c in '_-')


def prose_parts(text,inline=True):
    """Yield ordinary markdown separately from fenced/indented/inline code."""
    fence=None
    for line in text.splitlines(keepends=True):
        marker=re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$',line.rstrip('\n'))
        if fence:
            yield False,line
            if marker and marker[1][0]==fence[0] and len(marker[1])>=fence[1] and not marker[2].strip():fence=None
        elif marker:
            fence=(marker[1][0],len(marker[1]));yield False,line
        elif line.startswith(('    ','\t')):yield False,line
        elif not inline:yield True,line
        else:
            end=0
            for code in re.finditer(r'(`+)(.*?)\1',line):
                if code.start()>end:yield True,line[end:code.start()]
                yield False,code[0];end=code.end()
            yield True,line[end:]


def load_manifest():
    manifest=json.loads((COURSE_DIR/'manifest.json').read_text())
    files={}
    for name,digest in manifest['files'].items():
        raw=(COURSE_DIR/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise RuntimeError('Bundled course checksum mismatch: '+name)
        files[name]=raw.decode('utf-8')
    if len(manifest['chapters'])!=19:raise RuntimeError('Bundled course requires nineteen ordered lessons')
    return manifest,files


def seed_course(namespace=""):
    from .ingest import markdown_sections
    manifest,files=load_manifest()
    # Optional clone namespace preserves distinct reading records without
    # depending on hosted identity modules in the ordinary local edition.
    digest=hashlib.sha256((json.dumps(manifest,sort_keys=True,ensure_ascii=False)+GENERATOR_VERSION+namespace).encode()).hexdigest()
    base=manifest['source']+'/blob/'+manifest['revision']+'/'
    entries=[];targets={};anchors={}
    for name in manifest['chapters']+manifest['appendices']:
        text=files[name];chapter=text.splitlines()[0].lstrip('# ').strip()
        if name not in manifest['chapters']:chapter='附录 · '+chapter
        counts={}
        for title,content in markdown_sections(text,chapter):
            sid=s.uid();entries.append({'id':sid,'name':name,'chapter':chapter,'title':title,'content':content})
            targets.setdefault(name,sid)
            for ordinary,part in prose_parts(content,inline=False):
                if not ordinary:continue
                heading=re.match(r'^#{1,6}\s+(.+?)\s*#*\s*$',part.strip())
                if heading:
                    key=slug(heading[1]);n=counts.get(key,0);counts[key]=n+1
                    anchors[(name,key+(f'-{n}' if n else ''))]=sid
    def rewrite(content,name):
        def link(match):
            target=match[2];parts=urlsplit(target)
            if parts.scheme or parts.netloc or target.startswith(('/','mailto:')):return match[0]
            path=posixpath.normpath(posixpath.join(posixpath.dirname(name),unquote(parts.path))) if parts.path else name
            fragment=unquote(parts.fragment)
            if path in targets:
                sid=anchors.get((path,fragment)) if fragment else targets[path]
                if not sid:raise RuntimeError(f'Unknown course heading: {name} -> {target}')
                dest='/section/'+sid
            else:
                # Auxiliary HTML/code links stay pinned to the original repo.
                directory=parts.path.endswith('/') or any(p.startswith(path+'/') for p in files)
                prefix=manifest['source']+'/tree/'+manifest['revision']+'/' if directory else base
                dest=prefix+quote(path,safe='/')+('#'+quote(fragment) if fragment else '')
            return match[1]+dest+match[3]
        return ''.join(re.sub(r'(\]\()([^\s)]+)(\))',link,part) if ordinary else part for ordinary,part in prose_parts(content))
    bid=s.uid();now=s.now()
    attribution='## 来源与使用说明\n\n'+manifest['attribution']+'\n\n'+manifest['rights']+'\n\n固定来源：'+manifest['source']+'/tree/'+manifest['revision']+'\n\n原始章节未作内容纠错；第11–19讲、TBA扩展与已知待修订问题请读附录《编写说明》。原始文件逐项SHA256见随包manifest.json。'
    entries.append({'id':s.uid(),'name':'_source','chapter':'来源与使用说明','title':'来源与使用说明','content':attribution})
    with s.db() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT id FROM books WHERE content_hash=?',(digest,)).fetchone()
        if old:return old['id'],False
        c.execute('INSERT INTO books VALUES(?,?,?,?,?,?,?,?,?,?)',(bid,TITLE,'19讲中文教程 · 固定来源版本 · 非Stanford官方中文版','md',None,manifest['source']+'/tree/'+manifest['revision'],'teal',digest,now,0))
        for ordinal,item in enumerate(entries):
            content=rewrite(item['content'],item['name']) if item['name']!='_source' else item['content']
            c.execute('INSERT INTO sections VALUES(?,?,?,?,?,?,?)',(item['id'],bid,item['chapter'],item['title'],ordinal,content,None))
    return bid,True
