from __future__ import annotations
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any
import httpx
from . import store as s
from . import dialogue
from .i18n import tr

API_URL = 'https://api.deepseek.com/chat/completions'
MAX_ROUNDS = 6
MAX_TOOLS = 12
MODEL_PROGRESS_TIMEOUT = 45
MODEL_CALL_TIMEOUT = 120
MODEL_RETRY_DELAY = .4
MAX_CONTEXT_CHARS = 100000
MAX_REPLY_REPAIRS = 2
LOGGER = logging.getLogger(__name__)


class TransientProviderError(RuntimeError):
    pass


def compact_context(messages):
    """Bound one request, not the sum of billable tokens across tool rounds.

    Keep the current source and latest tool result. Older source payloads may
    be re-read; never discard action receipts or break tool-call pairing.
    """
    messages=[dict(m) for m in messages]
    def size():return len(json.dumps(messages,ensure_ascii=False))
    if size()<=MAX_CONTEXT_CHARS:return messages
    latest_user=max(i for i,m in enumerate(messages) if m['role']=='user')
    messages=[m for i,m in enumerate(messages) if i==0 or i>=latest_user]
    calls={c['id']:c['function']['name'] for m in messages for c in m.get('tool_calls',[])}
    read_names={'read_section','read_chapter','get_outline','search_book','search_history','read_history','get_reading_state'}
    tool_indices=[i for i,m in enumerate(messages) if m['role']=='tool']
    for i in tool_indices[:-1]:
        if size()<=MAX_CONTEXT_CHARS:break
        if calls.get(messages[i]['tool_call_id']) in read_names:
            messages[i]['content']=json.dumps({'context_compacted':True,'detail':'Earlier source text omitted to keep the request bounded. Read it again if needed; do not claim it is still present.'})
    return messages


def bounded_outline(rows, bookmarks):
    result={'sections':rows[:240],'total':len(rows),'bookmarks':bookmarks[:600],'bookmarks_total':len(bookmarks)}
    # Large PDF outlines used to repeat tens of thousands of characters on
    # every subsequent call. Keep a usable directory with explicit coverage.
    while len(json.dumps(result,ensure_ascii=False))>36000:
        key=max(('sections','bookmarks'),key=lambda k:len(json.dumps(result[k],ensure_ascii=False)))
        result[key]=result[key][:max(0,len(result[key])-10)]
    result['truncated']=len(result['sections'])<len(rows)
    result['bookmarks_truncated']=len(result['bookmarks'])<len(bookmarks)
    return result


def requested_effects(question):
    """Postconditions for unambiguous reader commands; never execute from text.

    General questions and requests to avoid an action remain ordinary dialogue.
    The model still resolves targets/contents and must use the actual tools.
    """
    expected=set()
    for clause in re.split(r'[，,。；;\n]',question.lower()):
        clause=clause.strip()
        if re.search(r'不要|不用|无需|不需要|别|don\x27t|do not|without',clause):continue
        if re.match(r'^(?:请问|为什么|怎么|如何|什么|how\b|what\b|why\b)',clause):continue
        prefix=r'^(?:请|帮我|麻烦|再|现在|先|然后|能不能|可以|一下|为我|\s)*'
        conversational_return=re.search(r'回到.*(?:问题|话题)',clause) and not re.search(r'原文|章节|阅读|页',clause)
        if not conversational_return and (re.match(prefix+r'(?:跳(?:转)?(?:到|去)|回到|返回(?:到|上|前|刚|之|原|阅读|$)|带我(?:到|去|看))',clause) or re.match(r'^(?:please\s+)?(?:go (?:to|back)|jump to|navigate to|return(?: to|$)|take me)',clause)):expected.add('navigation')
        write_command=re.match(prefix+r'(?:把|将|给|生成|制作|做|拆|出|整理|转成|记|保存|存)',clause) or re.match(r'^(?:please\s+)?(?:create|make|turn|generate|save)\b',clause)
        if write_command and re.search(r'anki|卡片|复习卡|闪卡|flashcards?',clause) and re.search(r'生成|制作|做|拆|出|整理|转成|记住|create|make|turn|generate',clause):expected.add('cards')
        if write_command and ((re.search(r'保存|存成|存为|记成|记为|记下|save',clause) and re.search(r'笔记|小结|总结|回顾|note|summary|review',clause)) or re.match(prefix+r'(?:记|做)(?:个|一份|一下)?笔记',clause)):expected.add('note')
    return expected


def validate_action_claims(answer, run):
    """A conversational success claim is not a receipt from the reader.

    Check explicit first-person completion statements against this run's
    persisted effects, not similar statements in previous conversations.
    """
    run_id=run['id']
    required=requested_effects(run['question'])
    if run.get('task_kind')=='chapter_summary':required={'note'}
    if run.get('task_kind')=='section_cards':required={'cards'}
    for expected in required:
        if expected=='navigation':
            exists=s.one('SELECT id FROM commands WHERE run_id=? LIMIT 1',(run_id,))
            tool_name='navigate / return_to'
        else:
            kind_test="kind='cards'" if expected=='cards' else "kind IN ('note','summary','review')"
            exists=s.one(f'SELECT id FROM artifacts WHERE run_id=? AND {kind_test} LIMIT 1',(run_id,))
            tool_name='create_cards' if expected=='cards' else 'save_artifact'
        if not exists:raise ValueError(f'当前用户明确要求 {tool_name}，本轮尚未执行。请先调用对应工具，取得实际结果；文字回复不等于完成操作。')
    start=r'(?:^|[。！!?\n])\s*(?:(?:好的|好)[，,\s]*)?'
    navigation=start+r'(?:(?:我)?(?:已经|已)[^。\n]*(?:跳到|跳转|返回|回到)|(?:I(?: have|\x27ve)? )?(?:jumped|navigated|returned|moved you|taken you)\b)'
    if re.search(navigation,answer,re.I) and not s.one(
            "SELECT id FROM commands WHERE run_id=? AND status='applied' LIMIT 1",(run_id,)):
        raise ValueError('本轮没有成功的跳转回执。请调用 navigate 或 return_to 并等待结果；历史回复中的成功不代表本轮已执行。')
    saved=start+r'(?:(?:我|笔记|卡片|复习卡|小结|总结|记录)?(?:已经|已)[^。\n]*(?:保存|存好|记下)(?!的)|(?:I(?: have|\x27ve)? )?saved\b)'
    if re.search(saved,answer,re.I) and not s.one('SELECT id FROM artifacts WHERE run_id=? LIMIT 1',(run_id,)):
        raise ValueError('本轮没有已保存的记录。用户要求保存时请调用保存工具；不要把历史记录当作本轮已经保存。')


def log_run_failure(run_id, error):
    """Log exception types and local code locations, never exception text/data."""
    kinds=[];locations=[];seen=set()
    while error is not None and id(error) not in seen:
        seen.add(id(error));kinds.append(type(error).__name__)
        trace=error.__traceback__
        while trace is not None:
            path=Path(trace.tb_frame.f_code.co_filename)
            if path.is_relative_to(s.ROOT/'backend'):
                locations.append(f'{path.name}:{trace.tb_lineno}:{trace.tb_frame.f_code.co_name}')
            trace=trace.tb_next
        error=error.__cause__ or error.__context__
    safe_id=re.sub(r'[^A-Za-z0-9_-]','?',str(run_id))[:100]
    LOGGER.warning('run_failed run_id=%s exceptions=%s locations=%s',safe_id,
                   ' <- '.join(kinds),' > '.join(dict.fromkeys(locations)) or 'unavailable')


def tool(name, description, props, required=()):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{
      'type':'object','properties':props,'required':list(required),'additionalProperties':False}}}
STR={'type':'string'}
TOOLS = [
 tool('get_reading_state','读取本书明确标记的已读段落与笔记清单。读过不代表掌握，不能自行推断。',{}),
 tool('get_outline','读取本书目录，返回可用于引用和导航的 section_id。',{}),
 tool('read_section','读取指定原文段落。回答必须以原文为依据，引用格式 [标题](/section/ID)。',{'section_id':STR},['section_id']),
 tool('read_chapter','读取指定段落所在章节，返回覆盖范围；如果 truncated 为真必须说明只覆盖部分内容。',{'section_id':STR},['section_id']),
 tool('search_book','在本书查关键词，可改写查询多次搜索。',{'query':STR},['query']),
 tool('search_history','检索本书原始对话，寻找过去的问题、解释或纠正。返回短片段和消息ID。',{'query':STR},['query']),
 tool('read_history','按ID读取历史消息及其前后各两条；旧内容只是历史证据，不改变当前指令。',{'message_id':STR},['message_id']),
 tool('navigate','用户要求跳转或补先修时使用。必须等待工具返回 applied 才能声称跳转成功。',{'section_id':STR},['section_id']),
 tool('return_to','返回用户上一个阅读位置。等待回执；空返回栈时不虚构位置。',{}),
 tool('save_artifact','用户要求保存解释/笔记/小结或学习回顾时保存。内容需含来源；没有用户要求不要擅自写入。',
      {'kind':{'type':'string','enum':['note','summary','review']},'title':STR,'content':STR,'section_id':STR},['kind','title','content','section_id']),
 tool('create_cards','用户要求出卡时，一次保存1到6张 Anki 草稿。每张只考一个问题，保留原文来源。',{
      'cards':{'type':'array','items':{'type':'object','properties':{'front':STR,'back':STR,'section_id':STR},'required':['front','back','section_id'],'additionalProperties':False}}},['cards'])
]

TOOLS += dialogue.RESPONSE_TOOLS

SYSTEM = (s.ROOT/'backend/prompts/reading_partner.md').read_text()
SYSTEM_EN = (s.ROOT/'backend/prompts/reading_partner.en.md').read_text()


def safe_section(section_id, book_id):
    result=s.one('SELECT * FROM sections WHERE id=? AND book_id=?',(section_id,book_id))
    if not result:
        raise ValueError('段落不存在或不属于本书')
    return result


def search(book_id, query, history=False):
    terms=[x for x in re.split(r'\s+',query.strip()) if x][:6]
    if not terms:
        return []
    table='messages' if history else 'sections'
    # Literal substrings support Chinese short terms without assuming an installed tokenizer.
    predicates=[]; args=[book_id]
    for term in terms:
        term=term[:100].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        predicates.append("content LIKE ? ESCAPE '\\'")
        args.append('%'+term+'%')
    order='created_at DESC' if history else 'ordinal'
    rows=s.all_rows(f"SELECT * FROM {table} WHERE book_id=? AND ({' OR '.join(predicates)}) ORDER BY {order} LIMIT 8",tuple(args))
    for r in rows:
        if history and r['role']=='assistant':r['content']=dialogue.readable_content(r['content'],book_id)
        txt=r['content']; positions=[txt.lower().find(t.lower()) for t in terms if t.lower() in txt.lower()]
        start=max(0,min(positions,default=0)-120)
        r['content']=txt[start:start+900]
    return rows


async def execute_tool(run, name: str, args: dict):
    bid=run['book_id']
    # Shortcut buttons carry an explicit task, not just another chat message.
    # Enforce the frozen target and effects before touching reader state.
    task=run.get('task_kind','chat')
    if task!='chat':
        allowed='save_artifact' if task=='chapter_summary' else 'create_cards'
        if name in ('navigate','return_to','save_artifact','create_cards') and name!=allowed:
            raise ValueError(f'This task only permits {allowed}; previous requests are already finished.')
        if name=='save_artifact' and args.get('section_id')!=run['section_id']:
            raise ValueError(f'Save this chapter summary at the requested reading position: {run["section_id"]}. Do not summarize a previous target.')
        if name=='create_cards' and any(c.get('section_id')!=run['section_id'] for c in args.get('cards',[]) if isinstance(c,dict)):
            raise ValueError(f'These cards must use the requested section: {run["section_id"]}.')
    if name=='get_reading_state':
        current=safe_section(run['section_id'],bid)
        return {'current_section':{k:current[k] for k in ('id','title','chapter')},'read_sections':s.all_rows('SELECT x.id,x.title,x.chapter FROM sections x JOIN marks m ON m.section_id=x.id WHERE x.book_id=? ORDER BY x.ordinal',(bid,)), 'artifacts':s.all_rows('SELECT id,kind,title,section_id FROM artifacts WHERE book_id=? ORDER BY created_at DESC LIMIT 40',(bid,))}
    if name=='get_outline':
        rows=s.all_rows('SELECT id,title,chapter,ordinal FROM sections WHERE book_id=? ORDER BY ordinal',(bid,))
        pdf=None
        # Optional format metadata must not make ordinary Markdown/TXT books
        # depend on a table introduced by a later import feature.
        for table in ('pdf_documents','ebook_documents'):
            if s.one("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)):
                pdf=s.one(f'SELECT outline FROM {table} WHERE book_id=?',(bid,))
                if pdf:break
        outline=json.loads(pdf['outline']) if pdf else []
        return bounded_outline(rows,outline)
    if name=='read_section':
        r=safe_section(str(args.get('section_id','')),bid)
        r['truncated']=len(r['content'])>14000
        r['content']=r['content'][:14000]
        return r
    if name=='read_chapter':
        r=safe_section(str(args.get('section_id','')),bid)
        rows=s.all_rows('SELECT id,title,content FROM sections WHERE book_id=? AND chapter=? ORDER BY ordinal',(bid,r['chapter']))
        chars=0; out=[]
        for row in rows:
            if chars+len(row['content'])>46000:
                if not out:out.append({**row,'content':row['content'][:46000],'truncated':True})
                break
            out.append(row);chars+=len(row['content'])
        return {'chapter':r['chapter'],'sections':out,'covered':len(out),'total':len(rows),'truncated':len(out)<len(rows) or any(x.get('truncated') for x in out)}
    if name in ('search_book','search_history'):
        return search(bid,str(args.get('query',''))[:300],name=='search_history')
    if name=='read_history':
        target=s.one('SELECT * FROM messages WHERE id=? AND book_id=?',(str(args.get('message_id','')),bid))
        if not target: raise ValueError('未找到当前书籍的这条历史')
        before=s.all_rows('SELECT * FROM messages WHERE book_id=? AND created_at<? ORDER BY created_at DESC LIMIT 2',(bid,target['created_at']))
        after=s.all_rows('SELECT * FROM messages WHERE book_id=? AND created_at>? ORDER BY created_at LIMIT 2',(bid,target['created_at']))
        rows=list(reversed(before))+[target]+after
        for r in rows:
            if r['role']=='assistant':r['content']=dialogue.readable_content(r['content'],bid)
        return [{**r,'content':r['content'][:2400]} for r in rows]
    if name in ('navigate','return_to'):
        target=args.get('section_id') if name=='navigate' else None
        if target: safe_section(target,bid)
        cmd={'id':s.uid(),'client_id':run['client_id'],'action':name,'section_id':target,'expected_revision':run['view_revision']}
        with s.db() as c:
            c.execute('INSERT INTO commands(id,run_id,client_id,action,section_id,expected_revision,expires_at) VALUES(?,?,?,?,?,?,?)',
                      (cmd['id'],run['id'],run['client_id'],name,target,run['view_revision'],s.now()+18))
        s.emit(run['id'],'navigation',cmd)
        for _ in range(90):
            await asyncio.sleep(.2)
            current=s.one('SELECT status FROM runs WHERE id=?',(run['id'],))
            if current['status']!='running': raise asyncio.CancelledError()
            row=s.one('SELECT status,result FROM commands WHERE id=?',(cmd['id'],))
            if row['status']!='pending':
                result=json.loads(row['result'] or '{}')
                if result.get('status')=='applied':
                    run['view_revision']=result.get('view_revision',run['view_revision']+1)
                    run['section_id']=result['section_id']
                    result['section_title']=safe_section(result['section_id'],bid)['title']
                return result
        with s.db() as c:c.execute("UPDATE commands SET status='expired' WHERE id=? AND status='pending'",(cmd['id'],))
        return {'status':'expired','detail':'没有收到当前阅读页面回执；请提供引用，不声称已跳转。'}
    if name=='save_artifact':
        kind=args.get('kind')
        if kind not in ('note','summary','review'): raise ValueError('无效产物类型')
        content=str(args.get('content',''))
        if not content.strip() or len(content)>60000: raise ValueError('内容为空或过长')
        row=s.save_artifact(bid,kind,str(args.get('title',''))[:160],content,args.get('section_id'),run['id'])
        s.emit(run['id'],'artifact',{'id':row['id'],'kind':kind,'title':row['title']})
        return {'saved':True,'id':row['id'],'title':row['title']}
    if name=='create_cards':
        cards=args.get('cards')
        if not isinstance(cards,list) or not 1<=len(cards)<=6: raise ValueError('每批需要1到6张卡片')
        # Whole batch validates before one transaction; its stored content is the immutable manifest.
        for card in cards:
            if not isinstance(card,dict) or not isinstance(card.get('front'),str) or not isinstance(card.get('back'),str):raise ValueError('卡片字段错误')
            if not card['front'].strip() or not card['back'].strip() or len(card['front'])>1000 or len(card['back'])>6000:raise ValueError('卡片内容为空或过长')
            safe_section(card.get('section_id'),bid)
        # Retrying the same batch is idempotent. A different batch in the same
        # run must not silently claim that the first batch was saved again.
        existing=s.one("SELECT * FROM artifacts WHERE run_id=? AND kind='cards' AND slot=0",(run['id'],))
        fields=('front','back','section_id')
        if existing:
            previous=json.loads(existing['content'])
            if [{k:x[k] for k in fields} for x in previous]!=[{k:x[k] for k in fields} for x in cards]:
                raise ValueError('本次请求已保存同类内容，不能用另一份内容覆盖；请另发请求。')
            return {'saved':True,'cards':previous}
        manifest=[{**{k:card[k] for k in fields},'id':s.uid()} for card in cards]
        row=s.save_artifact(bid,'cards',(f'{len(cards)} review cards' if run.get('language')=='en' else f'{len(cards)} 张复习卡片'),json.dumps(manifest,ensure_ascii=False),cards[0]['section_id'],run['id'])
        s.emit(run['id'],'artifact',{'id':row['id'],'kind':'cards','title':row['title']})
        return {'saved':True,'cards':json.loads(row['content'])}
    raise ValueError('未知工具')


async def stream_model(messages, api_key, emit, *, thinking=False):
    emitted=False
    def forward(text):
        nonlocal emitted
        if text:emitted=True
        emit(text)
    try:
        # A transport read timeout is reset by SSE keep-alives. Bound the whole
        # call as well as time without actual content/tool arguments below.
        async with asyncio.timeout(MODEL_CALL_TIMEOUT):
            for attempt in range(3):
                try:
                    return await _stream_model(messages,api_key,forward,thinking=thinking)
                except (TransientProviderError,httpx.RequestError):
                    # No reader-side tool runs until a full model response
                    # has arrived. Retrying this call cannot repeat effects.
                    if emitted or attempt==2:raise
                    await asyncio.sleep(MODEL_RETRY_DELAY*(2**attempt))
    except TimeoutError as e:
        raise RuntimeError('DeepSeek 本次回答超时，已停止等待。已收到的片段会保留，请稍后重试。') from e
    except httpx.TimeoutException as e:
        raise RuntimeError('连接 DeepSeek 超时，已停止等待，请稍后重试。') from e
    except httpx.RequestError as e:
        raise RuntimeError('与 DeepSeek 的连接中断或暂时无法建立，已停止本次回答。请检查网络后重试。') from e


async def _stream_model(messages, api_key, emit, *, thinking=False):
    # An already fulfilled write is no longer a useful next action. Keep
    # other tools available (e.g. saving a note and creating cards together).
    called={c['id']:c['function']['name'] for m in messages for c in m.get('tool_calls',[])}
    fulfilled=set()
    for message in messages:
        if message['role']!='tool':continue
        try:output=json.loads(message.get('content') or '{}')
        except (ValueError,TypeError):continue
        name=called.get(message.get('tool_call_id'))
        if isinstance(output,dict) and ((name in ('save_artifact','create_cards') and output.get('saved')) or (name in ('navigate','return_to') and output.get('status') in ('applied','stale','expired','empty_stack'))):fulfilled.add(name)
    available=[t for t in TOOLS if t['function']['name'] not in fulfilled]
    body={'model':os.getenv('DEEPSEEK_MODEL','deepseek-flash'),'messages':messages,'tools':available,
          'stream':True,'stream_options':{'include_usage':True},'max_tokens':5000,'thinking':{'type':'enabled' if thinking else 'disabled'}}
    if thinking:body['reasoning_effort']='high'
    parts=[]; reasoning=[]; calls={}; usage={}; finished=False; finish_reason=None; reader_visible=''
    text_gate=dialogue.TextReplyGate()
    async with httpx.AsyncClient(timeout=httpx.Timeout(100,connect=15),trust_env=False) as client:
        async with client.stream('POST',API_URL,headers={'Authorization':f'Bearer {api_key}'},json=body) as response:
            if response.status_code!=200:
                errors={401:'DeepSeek 密钥无效，请检查服务端配置。',402:'DeepSeek 账户余额不足，请在官方平台充值后重试。',429:'DeepSeek 请求频率受限，请稍后重试。',503:'DeepSeek 官方服务当前繁忙或暂时不可用，已停止本次请求。请稍后重试。'}
                error_type=TransientProviderError if response.status_code in (408,429,500,502,503,504) else RuntimeError
                raise error_type(errors.get(response.status_code,f'DeepSeek 暂时无法完成请求（HTTP {response.status_code}），请稍后重试。'))
            lines=response.aiter_lines().__aiter__()
            loop=asyncio.get_running_loop()
            progress_deadline=loop.time()+MODEL_PROGRESS_TIMEOUT
            while True:
                remaining=progress_deadline-loop.time()
                if remaining<=0:
                    raise RuntimeError('DeepSeek 暂无新内容，等待超时，已停止本次回答。已收到的片段会保留，请稍后重试。')
                try:
                    line=await asyncio.wait_for(anext(lines),timeout=remaining)
                except StopAsyncIteration:
                    break
                except TimeoutError as e:
                    raise RuntimeError('DeepSeek 暂无新内容，等待超时，已停止本次回答。已收到的片段会保留，请稍后重试。') from e
                if not line.startswith('data:'):continue
                raw=line[5:].strip()
                if raw=='[DONE]':
                    finished=True;break
                if not raw:continue
                event=json.loads(raw)
                if event.get('usage'):usage=event['usage']
                choices=event.get('choices') or []
                if not choices:continue
                if choices[0].get('finish_reason'):finish_reason=choices[0]['finish_reason']
                delta=choices[0].get('delta',{})
                progressed=False
                if delta.get('reasoning_content'):
                    reasoning.append(delta['reasoning_content']);progressed=True
                if delta.get('content'):
                    parts.append(delta['content']);visible=text_gate.feed(delta['content'])
                    if visible:emit(visible)
                    progressed=True
                for tc in delta.get('tool_calls',[]):
                    target=calls.setdefault(tc['index'],{'id':'','type':'function','function':{'name':'','arguments':''}})
                    if tc.get('id'):target['id']=tc['id']
                    fn=tc.get('function',{})
                    if fn.get('name'):target['function']['name']+=fn['name']
                    target['function']['arguments']+=fn.get('arguments','')
                    progressed=progressed or bool(fn.get('name') or fn.get('arguments'))
                response_calls=[c for c in calls.values() if c['function']['name'] in dialogue.RESPONSE_NAMES]
                if response_calls:
                    if len(calls)!=1:raise RuntimeError('模型混合了回复与操作，已停止；请重试。')
                    final=response_calls[0]['function']
                    prefix=dialogue.stream_prefix(final['name'],final['arguments'])
                    if not prefix.startswith(reader_visible):raise RuntimeError('回复结构发生变化，已停止；请重试。')
                    if len(prefix)>len(reader_visible):emit(prefix[len(reader_visible):]);reader_visible=prefix
                if progressed:progress_deadline=loop.time()+MODEL_PROGRESS_TIMEOUT
    if not finished or finish_reason not in ('stop','tool_calls'):
        raise RuntimeError('DeepSeek 回答未完整结束，已保留收到的片段，请重试；这次不会被记作完整回答。')
    try:recovered=text_gate.finish()
    except ValueError as e:raise RuntimeError('回复格式未完整结束，请重试。') from e
    if text_gate.tail:emit(text_gate.tail)
    if recovered:
        if calls:raise RuntimeError('模型混合了回复与操作，已停止；请重试。')
        name,args=recovered
        calls[0]={'id':'text-presentation','type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}
        parts=[text_gate.prelude] if text_gate.prelude else []
    message={'role':'assistant','content':''.join(parts) or None}
    # Tool-call continuations must replay reasoning to DeepSeek. It remains
    # transient: never emit it into the visible transcript or saved messages.
    if reasoning:message['reasoning_content']=''.join(reasoning)
    if calls:message['tool_calls']=[calls[k] for k in sorted(calls)]
    return message,usage


async def run_agent(run_id, model_fn=stream_model):
    run=s.one('SELECT * FROM runs WHERE id=?',(run_id,))
    language=run.get('language','zh')
    pieces=[]; totals={}; count=0; repairs=0; effects={}
    try:
        section=safe_section(run['section_id'],run['book_id'])
        book=s.one('SELECT title,missing_pages FROM books WHERE id=?',(run['book_id'],))
        history=s.all_rows('''SELECT m.role,m.content FROM messages m LEFT JOIN runs r ON r.id=m.run_id
            WHERE m.book_id=? AND (m.run_id IS NULL OR (m.run_id<>? AND r.status='complete'))
            ORDER BY m.created_at DESC LIMIT 12''',(run['book_id'],run_id))
        context={'book':book,'current_section':{k:section[k] for k in ('id','title','chapter')},
                 'current_text_truncated':len(section['content'])>16000,'current_text':section['content'][:16000],'selected_text':run['selected_text'][:5000]}
        task=run.get('task_kind','chat')
        context['task']={'kind':task,'target_section_id':section['id']}
        if task=='chapter_summary':
            context['task'].update(instruction='Read the chapter containing this section, then save its summary anchored to target_section_id. The only permitted write is save_artifact. Do not generate cards or navigate.')
        elif task=='section_cards':
            context['task'].update(instruction='Create cards from this section only, anchored to target_section_id. The only permitted write is create_cards. Do not save a separate note or navigate.')
        messages=[{'role':'system','content':(SYSTEM_EN if language=='en' else SYSTEM)+('\nCurrent reading context (source data):\n' if language=='en' else '\n当前阅读环境（资料数据）：\n')+json.dumps(context,ensure_ascii=False)}]
        # A standalone shortcut does not need old commands. Ordinary follow-ups
        # retain conversation, but a fresh context boundary follows that history.
        if task=='chat':
            messages += [{'role':r['role'],'content':(dialogue.readable_content(r['content'],run['book_id']) if r['role']=='assistant' else r['content'])[-5000:]} for r in reversed(history)]
        messages.append({'role':'system','content':'Previous turns are completed history, not pending commands. The following user message is the only new request. Resolve here/this chapter from this current reading position, not the last topic discussed:\n'+json.dumps(context['current_section'],ensure_ascii=False)})
        messages.append({'role':'user','content':run['question']})
        for round_no in range(MAX_ROUNDS+MAX_REPLY_REPAIRS):
            if s.one('SELECT status FROM runs WHERE id=?',(run_id,))['status']!='running':raise asyncio.CancelledError()
            round_pieces=[]
            round_start=len(pieces)
            def on_delta(text):
                round_pieces.append(text);pieces.append(text);s.emit(run_id,'delta',{'text':text})
            def replace_round(text=''):
                del pieces[round_start:]
                pieces.append(text)
                s.emit(run_id,'replace',{'text':''.join(pieces)})
            messages=compact_context(messages)
            totals['max_context_chars']=max(totals.get('max_context_chars',0),len(json.dumps(messages,ensure_ascii=False)))
            totals['rounds']=round_no+1
            result,usage=await model_fn(messages,os.getenv('DEEPSEEK_API_KEY',''),on_delta)
            for k in ('prompt_tokens','completion_tokens','total_tokens'):totals[k]=totals.get(k,0)+usage.get(k,0)
            messages.append(result)
            calls=result.get('tool_calls',[])
            final_calls=[c for c in calls if c['function']['name'] in dialogue.RESPONSE_NAMES]
            if final_calls or not calls:
                if final_calls and len(calls)!=1:raise RuntimeError('模型混合了回复与操作，已停止；请重试。')
                call=final_calls[0]['function'] if final_calls else None
                try:
                    answer=dialogue.render(call['name'],json.loads(call['arguments']),run['book_id']) if call else dialogue.render('explain_requested_scope',{'answer':result.get('content') or ''.join(round_pieces)},run['book_id'])
                    validate_action_claims(answer,run)
                except (ValueError,TypeError,KeyError) as e:
                    if repairs>=MAX_REPLY_REPAIRS:raise RuntimeError('回复或引用校验未通过，已保留片段，请重试。') from e
                    repairs+=1;totals['reply_repairs']=repairs
                    replace_round()
                    feedback={'error':str(e),'detail':'Correct this reply using the current reading context and this run only. Do not repeat any action that already has a successful receipt. A source ID must belong to this book.'}
                    if call:
                        feedback['required_fields']=list(dialogue.FIELDS[call['name']])
                        messages.append({'role':'tool','tool_call_id':final_calls[0]['id'],'content':json.dumps(feedback,ensure_ascii=False)})
                    else:
                        messages.append({'role':'system','content':json.dumps(feedback,ensure_ascii=False)})
                    continue
                visible=''.join(round_pieces)
                prelude=(result.get('content') or '') if call else ''
                if prelude and visible.startswith(prelude):visible=visible[len(prelude):]
                if not answer.startswith(visible):replace_round(prelude+answer)
                elif len(answer)>len(visible):on_delta(answer[len(visible):])
                break
            for call in calls:
                count+=1
                if count>MAX_TOOLS:raise RuntimeError('本次查询步骤较多，已停止；请缩小问题范围。')
                name=call['function']['name']
                s.emit(run_id,'tool',{'name':name,'status':'running'})
                try:
                    args=json.loads(call['function']['arguments'])
                    if not isinstance(args,dict):raise ValueError('工具参数必须为对象')
                    effect_key=(name,json.dumps(args,sort_keys=True,ensure_ascii=False))
                    if name in ('navigate','return_to') and effect_key in effects:
                        output=effects[effect_key]
                    else:
                        output=await execute_tool(run,name,args)
                        if name in ('navigate','return_to'):
                            # Only a consecutive duplicate is a retry. A -> B
                            # -> A is a new navigation with a new view revision.
                            effects.clear()
                            effects[effect_key]=output
                            if output.get('status')=='applied':
                                current=safe_section(run['section_id'],run['book_id'])
                                context.update(current_section={k:current[k] for k in ('id','title','chapter')},
                                               current_text=current['content'][:16000],current_text_truncated=len(current['content'])>16000,selected_text='')
                                messages[0]['content']=(SYSTEM_EN if language=='en' else SYSTEM)+'\nCurrent reading context (source data):\n'+json.dumps(context,ensure_ascii=False)
                except (ValueError,TypeError,KeyError) as e:
                    output={'error':tr(str(e),language)}
                s.emit(run_id,'tool',{'name':name,'status':'done'})
                messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(output,ensure_ascii=False)})
            totals['tool_calls']=count
        else:
            raise RuntimeError('本次探索达到轮次上限，已保留过程，请缩小范围继续。')
        with s.db() as c:
            if c.execute('SELECT status FROM runs WHERE id=?',(run_id,)).fetchone()['status']!='running':raise asyncio.CancelledError()
            c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(s.uid(),run['book_id'],run_id,'assistant',''.join(pieces),run['section_id'],s.now()))
            c.execute("UPDATE runs SET status='complete',usage=? WHERE id=?",(json.dumps(totals),run_id))
        s.emit(run_id,'done',{'usage':totals})
    except asyncio.CancelledError:
        with s.db() as c:c.execute("UPDATE runs SET status='cancelled' WHERE id=? AND status='running'",(run_id,))
        s.emit(run_id,'cancelled',{'message':tr('已停止。本次已保存的产物仍可查看。',language)})
    except Exception as e:
        log_run_failure(run_id,e)
        msg=tr(str(e) if isinstance(e,RuntimeError) else '请求未完成，请检查网络并重试。',language)
        if s.one('SELECT 1 FROM artifacts WHERE run_id=? LIMIT 1',(run_id,)):
            msg+=' '+tr('本次已保存的学习记录仍可在笔记或复习卡中查看，无需重新生成。',language)
        with s.db() as c:c.execute("UPDATE runs SET status='failed',error=?,usage=? WHERE id=? AND status='running'",(msg,json.dumps(totals),run_id))
        s.emit(run_id,'error',{'message':msg})
