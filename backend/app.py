from __future__ import annotations
import asyncio
import csv
import html
import io
import json
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, StreamingResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import store as s
from .ingest import seed, import_file
from .agent import run_agent, safe_section, search
from .dialogue import readable_content
from .i18n import tr, request_language

load_dotenv(s.ROOT/'.env')
TASKS: dict[str, asyncio.Task] = {}

@asynccontextmanager
async def lifespan(app):
    s.init()
    seed(s.ROOT.parent)
    yield
    for task in list(TASKS.values()):task.cancel()
    if TASKS:await asyncio.gather(*TASKS.values(),return_exceptions=True)

app=FastAPI(title='阅间',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=os.getenv('READING_ALLOWED_HOSTS','localhost,127.0.0.1,testserver').split(','))

@app.exception_handler(HTTPException)
async def localized_http_error(request:Request,exc:HTTPException):
    return JSONResponse({'detail':tr(exc.detail,request_language(request))},status_code=exc.status_code,headers=exc.headers)

@app.middleware('http')
async def local_origin(request: Request, call_next):
    if request.url.path=='/api/import':
        try:too_large=int(request.headers.get('content-length','0'))>21*1024*1024
        except ValueError:too_large=True
        if too_large:return JSONResponse({'detail':'单份文件最大 20 MB。 / Maximum file size: 20 MB.'},413)
    origin=request.headers.get('origin')
    allowed={str(request.base_url).rstrip('/')}
    allowed.update({'http://localhost:8765','http://127.0.0.1:8765','http://localhost:5178','http://127.0.0.1:5178'})
    if request.method not in ('GET','HEAD','OPTIONS'):
        if (origin and origin not in allowed) or request.headers.get('sec-fetch-site')=='cross-site':
            return Response('Origin not allowed',403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Robots-Tag']='noindex, nofollow'
    return response

def require_book(bid):
    row=s.one('SELECT * FROM books WHERE id=?',(bid,))
    if not row:raise HTTPException(404,'资料不存在')
    return row

@app.get('/api/status')
def status(request:Request):
    load_dotenv(s.ROOT/'.env',override=True)
    return {'configured':bool(os.getenv('DEEPSEEK_API_KEY')),'provider':'DeepSeek official' if request_language(request)=='en' else 'DeepSeek 官方','model':os.getenv('DEEPSEEK_MODEL','deepseek-flash'),'version':'0.1.0'}

@app.get('/api/books')
def books():
    return s.all_rows('''SELECT b.id,b.title,b.subtitle,b.format,b.color,b.created_at,b.missing_pages,
        (SELECT COUNT(*) FROM sections WHERE book_id=b.id) section_count,
        (SELECT COUNT(*) FROM sections x JOIN marks m ON m.section_id=x.id WHERE x.book_id=b.id) read_count,
        (SELECT COUNT(DISTINCT chapter) FROM sections WHERE book_id=b.id) chapter_count,
        (SELECT section_id FROM positions WHERE book_id=b.id) last_section,
        (SELECT new_book_id FROM example_replacements WHERE old_book_id=b.id) replacement_id
        FROM books b ORDER BY created_at''')

@app.get('/api/books/{bid}')
def book(bid:str):
    b=require_book(bid)
    replacement=s.one('SELECT new_book_id FROM example_replacements WHERE old_book_id=?',(bid,))
    b['replacement_id']=replacement['new_book_id'] if replacement else None
    b.pop('file_path',None);b.pop('source',None)
    pdf=s.one('SELECT * FROM pdf_documents WHERE book_id=?',(bid,))
    if pdf:
        b.update({key:json.loads(pdf[key]) for key in ('outline','blank_pages','image_pages')})
    ebook=s.one('SELECT outline,warnings FROM ebook_documents WHERE book_id=?',(bid,))
    if ebook:
        b.update({key:json.loads(ebook[key]) for key in ('outline','warnings')})
    b['sections']=s.all_rows('''SELECT x.id,x.title,x.chapter,x.ordinal,x.page,LENGTH(x.content) chars,
        EXISTS(SELECT 1 FROM marks WHERE section_id=x.id) is_read
        FROM sections x WHERE book_id=? ORDER BY ordinal''',(bid,))
    return b

@app.get('/api/sections/{sid}')
def section(sid:str):
    r=s.one('SELECT * FROM sections WHERE id=?',(sid,))
    if not r:raise HTTPException(404,'段落不存在')
    return r

@app.post('/api/import')
async def upload(request:Request,file:UploadFile=File(...)):
    raw=await file.read(20*1024*1024+1)
    if len(raw)>20*1024*1024:raise HTTPException(413,'单份文件最大 20 MB。')
    try:
        bid,created=await asyncio.to_thread(import_file,file.filename or 'untitled.md',raw,request_language(request))
    except ValueError as e:raise HTTPException(422,str(e))
    except asyncio.TimeoutError:raise HTTPException(422,'文件整理超时，请拆分后重试。 / Parsing timed out. Please split this file.')
    return {'id':bid,'created':created}

@app.get('/api/books/{bid}/file')
def original(bid:str):
    b=require_book(bid)
    if not b['file_path']:raise HTTPException(404,'这份资料没有 PDF 原文件')
    return FileResponse(b['file_path'],media_type='application/pdf')

@app.get('/api/books/{bid}/assets/{name}')
def ebook_asset(bid:str,name:str):
    require_book(bid)
    row=s.one('SELECT mime,content FROM book_assets WHERE book_id=? AND name=?',(bid,name))
    if not row:raise HTTPException(404,'图片不存在 / Image not found')
    return Response(row['content'],media_type=row['mime'],headers={
        'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store',
        'Content-Security-Policy':"default-src 'none'; sandbox"})

class Position(BaseModel):
    section_id:str
@app.put('/api/books/{bid}/position')
def position(bid:str,body:Position):
    try:safe_section(body.section_id,bid)
    except ValueError as e:raise HTTPException(404,str(e))
    with s.db() as c:c.execute('INSERT INTO positions VALUES(?,?,?) ON CONFLICT(book_id) DO UPDATE SET section_id=excluded.section_id,updated_at=excluded.updated_at',(bid,body.section_id,s.now()))
    return {'ok':True}

class Mark(BaseModel):
    read:bool
@app.put('/api/sections/{sid}/read')
def mark(sid:str,body:Mark):
    section(sid)
    with s.db() as c:
        if body.read:c.execute('INSERT OR IGNORE INTO marks VALUES(?,?)',(sid,s.now()))
        else:c.execute('DELETE FROM marks WHERE section_id=?',(sid,))
    return {'ok':True}

@app.get('/api/books/{bid}/messages')
def messages(bid:str):
    require_book(bid)
    rows=s.all_rows('SELECT m.*,r.status run_status,r.error run_error,r.language run_language FROM messages m LEFT JOIN runs r ON r.id=m.run_id WHERE m.book_id=? ORDER BY m.created_at',(bid,))
    for row in rows:
        if row['role']=='assistant':row['content']=tr(readable_content(row['content'],bid),row.get('run_language'))
    return rows

@app.get('/api/books/{bid}/history')
def history(bid:str,q:str=''):
    require_book(bid)
    return search(bid,q[:300],True) if q else []

@app.get('/api/books/{bid}/artifacts')
def artifacts(bid:str):
    require_book(bid)
    return s.all_rows('SELECT * FROM artifacts WHERE book_id=? ORDER BY created_at DESC',(bid,))

class ArtifactBody(BaseModel):
    kind:Literal['note','summary','review']='note'
    title:str=Field(min_length=1,max_length=160)
    content:str=Field(min_length=1,max_length=60000)
    section_id:str
@app.post('/api/books/{bid}/artifacts')
def artifact(bid:str,body:ArtifactBody):
    require_book(bid)
    try:return s.save_artifact(bid,body.kind,body.title,body.content,body.section_id)
    except ValueError as e:raise HTTPException(422,str(e))

class EditArtifact(BaseModel):
    title:str=Field(min_length=1,max_length=160)
    content:str=Field(min_length=1,max_length=60000)
    expected_content:str
@app.patch('/api/artifacts/{aid}')
def edit_artifact(aid:str,body:EditArtifact):
    with s.db() as c:
        old=c.execute('SELECT * FROM artifacts WHERE id=?',(aid,)).fetchone()
        if not old:raise HTTPException(404,'记录不存在')
        if not body.title.strip() or not body.content.strip():raise HTTPException(422,'标题或内容为空')
        if old['content']!=body.expected_content:raise HTTPException(409,'内容已变化，请重新打开后编辑。')
        if old['kind']=='cards':
            try:
                cards=json.loads(body.content);previous=json.loads(old['content'])
                if not isinstance(cards,list) or len(cards)!=len(previous) or len({x['id'] for x in cards})!=len(cards) or {x['id'] for x in cards}!={x['id'] for x in previous}:raise ValueError()
                for card in cards:
                    if not isinstance(card['front'],str) or not card['front'].strip() or len(card['front'])>1000 or not isinstance(card['back'],str) or not card['back'].strip() or len(card['back'])>6000:raise ValueError()
                    if not c.execute('SELECT 1 FROM sections WHERE id=? AND book_id=?',(card['section_id'],old['book_id'])).fetchone():raise ValueError()
            except (ValueError,KeyError,TypeError):raise HTTPException(422,'卡片格式或来源无效')
        c.execute('UPDATE artifacts SET title=?,content=? WHERE id=?',(body.title,body.content,aid))
    return {'ok':True}

def public_base_url(request:Request):
    # Use deployment configuration, never a client-supplied forwarded host.
    configured=os.getenv('READING_PUBLIC_URL','') or os.getenv('READING_PUBLIC_ORIGINS','').split(',')[0]
    if configured.strip():
        url=urlsplit(configured.strip())
        if url.scheme in ('https','http') and url.netloc and not url.username and not url.password:
            return f'{url.scheme}://{url.netloc}'
    return str(request.base_url).rstrip('/')

@app.get('/api/books/{bid}/export/anki')
def export_anki(bid:str,request:Request):
    require_book(bid)
    rows=s.all_rows("SELECT * FROM artifacts WHERE book_id=? AND kind='cards' ORDER BY created_at",(bid,))
    english=request_language(request)=='en'
    output=io.StringIO();output.write('#separator:Tab\n#html:true\n#columns:'+('ID\tQuestion\tAnswer\tSource\tTags' if english else 'ID\t问题\t答案\t来源\t标签')+'\n')
    writer=csv.writer(output,delimiter='\t',lineterminator='\n')
    def escape(t):return html.escape(t).replace('\n','<br>')
    for row in rows:
        for card in json.loads(row['content']):
            source=f'{public_base_url(request)}/?book={bid}&section={card["section_id"]}'
            writer.writerow([card['id'],escape(card['front']),escape(card['back']),f'<a href="{source}">{"View source" if english else "返回原文"}</a>','reading'])
    return Response(output.getvalue(),media_type='text/tab-separated-values; charset=utf-8',headers={'Content-Disposition':'attachment; filename="yuejian-anki.tsv"'})

@app.get('/api/books/{bid}/export/notes')
def export_notes(bid:str,request:Request):
    b=require_book(bid)
    records=s.all_rows("SELECT * FROM artifacts WHERE book_id=? AND kind<>'cards' ORDER BY created_at",(bid,))
    english=request_language(request)=='en'
    sections={r['id']:r['title'] for r in s.all_rows('SELECT id,title FROM sections WHERE book_id=?',(bid,))}
    def source_url(sid):return f'{public_base_url(request)}/?book={bid}&section={sid}'
    def linked_content(content):
        # Downloaded Markdown has no /section route. Rewrite real citations,
        # while keeping fenced and inline code examples exactly as authored.
        out=[];fence=None;inline=0
        for line in content.splitlines(keepends=True):
            marker=re.match(r'^ {0,3}(`{3,}|~{3,})(.*?)(?:\r?\n)?$',line)
            if fence:
                if marker and marker[1][0]==fence[0] and len(marker[1])>=fence[1] and not marker[2].strip():fence=None
                out.append(line);continue
            if marker and not inline:
                fence=(marker[1][0],len(marker[1]));out.append(line);continue
            i=0
            while i<len(line):
                if line[i]=='\\' and not inline:
                    out.append(line[i:i+2]);i+=2;continue
                if line[i]=='`':
                    end=i+1
                    while end<len(line) and line[end]=='`':end+=1
                    count=end-i
                    if not inline:inline=count
                    elif inline==count:inline=0
                    out.append(line[i:end]);i=end;continue
                link=re.match(r'\]\(/section/([^\s)]+)\)',line[i:]) if not inline and line[i]==']' else None
                if link and link[1] in sections:
                    out.append(f']({source_url(link[1])})');i+=len(link[0]);continue
                out.append(line[i]);i+=1
        return ''.join(out)
    out=f'# {b["title"]} · {"Reading notes" if english else "学习记录"}\n\n'
    for r in records:
        out+=f'## {r["title"]}\n\n{linked_content(r["content"])}\n\n'
        if r['section_id'] in sections:
            title=sections[r['section_id']].replace('\\','\\\\').replace('[','\\[').replace(']','\\]')
            out+=f'{"Source" if english else "原文"}: [{title}]({source_url(r["section_id"])})\n\n'
    out+='## '+('Conversation' if english else '原始对话')+'\n\n'
    for r in messages(bid):
        speaker=('You' if r['role']=='user' else 'MarginRoom') if english else ('我' if r['role']=='user' else '阅间')
        out+=f'### {speaker}\n\n{linked_content(r["content"])}\n\n'
    return Response(out,media_type='text/markdown; charset=utf-8',headers={'Content-Disposition':'attachment; filename="reading-notes.md"'})

class RunBody(BaseModel):
    id:str=Field(min_length=8,max_length=100)
    book_id:str
    section_id:str
    client_id:str=Field(min_length=1,max_length=100)
    question:str=Field(min_length=1,max_length=5000)
    selected_text:str=Field(default='',max_length=5000)
    view_revision:int=Field(default=0,ge=0)
    language:Literal['zh','en']='zh'
    task_kind:Literal['chat','chapter_summary','section_cards']='chat'

@app.post('/api/runs')
async def start_run(body:RunBody,request:Request):
    request.state.language=body.language
    if not body.question.strip():raise HTTPException(422,'问题不能为空白')
    load_dotenv(s.ROOT/'.env',override=True)
    if not os.getenv('DEEPSEEK_API_KEY'):raise HTTPException(503,'DeepSeek 官方 API Key 尚未接入。当前可以导入、阅读、做笔记；接入后即可提问。')
    try:safe_section(body.section_id,body.book_id)
    except ValueError as e:raise HTTPException(422,str(e))
    old=s.one('SELECT * FROM runs WHERE id=?',(body.id,))
    if old:
        if any(old[k]!=getattr(body,k) for k in ('book_id','client_id','question','section_id','selected_text','view_revision','language','task_kind')):raise HTTPException(409,'请求编号已用于另一次提问。')
        return {'id':old['id'],'status':old['status']}
    try:
        with s.db() as c:
            c.execute('INSERT INTO runs(id,book_id,client_id,question,status,created_at,selected_text,section_id,view_revision,language,task_kind) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (body.id,body.book_id,body.client_id,body.question,'running',s.now(),body.selected_text,body.section_id,body.view_revision,body.language,body.task_kind))
            c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(s.uid(),body.book_id,body.id,'user',body.question,body.section_id,s.now()))
    except sqlite3.IntegrityError:
        raise HTTPException(409,'这本资料有一条回答正在进行，请先等待或停止。')
    key=body.id
    task=asyncio.create_task(bounded_run(body.id));TASKS[key]=task
    task.add_done_callback(lambda _:TASKS.pop(key,None))
    return {'id':body.id,'status':'running'}

async def bounded_run(rid):
    await asyncio.wait_for(run_agent(rid),timeout=300)

@app.get('/api/runs/{rid}')
def get_run(rid:str):
    r=s.one('SELECT * FROM runs WHERE id=?',(rid,))
    if not r:raise HTTPException(404,'任务不存在')
    return r

@app.get('/api/runs/{rid}/events')
async def events(rid:str,request:Request,after:int=0):
    get_run(rid)
    try:after=max(after,int(request.headers.get('last-event-id','0')))
    except ValueError:pass
    async def generate():
        cursor=after
        for _ in range(1500):
            if await request.is_disconnected():return
            rows=s.all_rows('SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id',(rid,cursor))
            for row in rows:
                cursor=row['id']
                yield f'id: {cursor}\nevent: {row["type"]}\ndata: {row["data"]}\n\n'
            state=s.one('SELECT status,error FROM runs WHERE id=?',(rid,))
            if state['status']!='running':
                # Drain any event committed between the fetch and the status read.
                for row in s.all_rows('SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id',(rid,cursor)):
                    cursor=row['id']
                    yield f'id: {cursor}\nevent: {row["type"]}\ndata: {row["data"]}\n\n'
                yield 'event: terminal\ndata: '+json.dumps(state,ensure_ascii=False)+'\n\n'
                return
            yield ': keepalive\n\n'
            await asyncio.sleep(.25)
    return StreamingResponse(generate(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.post('/api/runs/{rid}/cancel')
async def cancel(rid:str):
    get_run(rid)
    with s.db() as c:c.execute("UPDATE runs SET status='cancelled' WHERE id=? AND status='running'",(rid,))
    key=rid
    if key in TASKS:TASKS[key].cancel()
    return {'ok':True}

class Ack(BaseModel):
    client_id:str
    status:Literal['applied','stale','empty_stack','expired']
    section_id:str|None=None
    view_revision:int=Field(ge=0)

@app.post('/api/commands/{cid}/ack')
def ack(cid:str,body:Ack):
    with s.db() as c:
        cmd=c.execute('SELECT * FROM commands WHERE id=?',(cid,)).fetchone()
        if not cmd:raise HTTPException(404,'指令不存在')
        if cmd['client_id']!=body.client_id:raise HTTPException(403,'指令不属于这个阅读窗口')
        if cmd['status']!='pending':return json.loads(cmd['result'] or '{}')
        run=c.execute('SELECT * FROM runs WHERE id=?',(cmd['run_id'],)).fetchone()
        state=body.status
        if cmd['expires_at']<s.now() or run['status']!='running':state='expired'
        if state=='applied':
            target=c.execute('SELECT 1 FROM sections WHERE id=? AND book_id=?',(body.section_id,run['book_id'])).fetchone()
            if not target:raise HTTPException(422,'目标不属于当前书籍')
            if cmd['action']=='navigate' and body.section_id!=cmd['section_id']:raise HTTPException(422,'目标与导航指令不一致')
            if body.view_revision<=cmd['expected_revision']:raise HTTPException(422,'页面版本没有前进')
        result={**body.model_dump(),'status':state}
        c.execute('UPDATE commands SET status=?,result=? WHERE id=?',(state,json.dumps(result,ensure_ascii=False),cid))
    return result

DIST=Path(os.getenv('READING_WEB_DIST',s.ROOT/'web/dist'))
if (DIST/'assets').exists():app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')

@app.get('/{path:path}')
def frontend(path:str,request:Request):
    if path.startswith('api/'):raise HTTPException(404,'接口不存在')
    if not (DIST/'index.html').exists():return Response('Frontend not built. Run: cd web && npm run build.\n前端尚未构建。请运行 cd web && npm run build。',503)
    return FileResponse(DIST/'index.html')
