"""Terminal dialogue acts: express an answer, without another model round."""
import json
import re
from . import store as s

def form(name, description, properties):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{
        'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}}

SOURCES={'type':'array','items':{'type':'string'},'description':'支持这次解释的真实原文section_id；只用当前书内已取得的来源。'}
RESPONSE_TOOLS=[
    form('clarify_meaning','读者问词、符号或表述的意思时，以释义解开当前疑问。这是最终回复，程序直接呈现后结束。',{
        'meaning':{'type':'string','description':'填入“这个词指的是___”中的定义成分：它所指的事物或关系。不是整段回复，不附带价值评价、使用步骤或其他概念。'},
        'example':{'type':'string','description':'填入“例如原文中的___”中的实例成分，给出原文里对应的那件事或那条返回。不是复述案例的整个过程；没有适合的实例则为空。'},
        'sources':SOURCES}),
    form('connect_reason','读者追问为什么或纠正一个理解时，补上所问的因果连接。这是最终回复，程序直接呈现后结束。',{
        'cause':{'type':'string','description':'填入“原因是___”中的直接原因或纠正判断，定位这次疑问所指的那个事实。不是整段回复。'},
        'connection':{'type':'string','description':'把上面的原因连接到读者所问结果的因果关系。只补这个缺口，保留影响该判断的条件；不是案例全程、原理背景或相邻问题的解释。'},
        'sources':SOURCES}),
    form('map_chapter','读者要章节概括或主旨时，建立问题、核心思路与边界的地图，不逐节重讲。这是最终回复，程序直接呈现后结束。',{
        'problem':{'type':'string','description':'本章试图解决的问题或澄清的混淆。'},
        'central_idea':{'type':'string','description':'贯穿本章的关键思路，以及它如何回应上面的问题；不是逐节目录复述。'},
        'boundary':{'type':'string','description':'忽略后会误解主旨的适用条件或资料缺口；没有则为空。不追加完整的学习计划或自测。'},
        'sources':SOURCES}),
    form('explain_requested_scope','读者明确要完整过程、逐项详解、推导、方案或系统比较时，覆盖所请求的范围。这是最终回复，程序直接呈现后结束。',{
        'answer':{'type':'string','description':'完成明确任务的Markdown回复，保留关键步骤、条件、例外与真实原文链接；不因表达工具而省略必要内容。'}}),
]
RESPONSE_NAMES={t['function']['name'] for t in RESPONSE_TOOLS}
FIELDS={'clarify_meaning':('meaning','example'),'connect_reason':('cause','connection'),
        'map_chapter':('problem','central_idea','boundary'),'explain_requested_scope':('answer',)}

def parse_text_reply(text):
    """Recover only a whole, known presentation envelope, never operation tools.

    This is not an HTML sanitizer: code fences, inline examples and ordinary
    prose stay untouched. Field bodies are Markdown, not XML entities.
    """
    stripped=text.strip()
    name=next((n for n in FIELDS if stripped.startswith(f'<{n}>')),None)
    if not name:return None
    closing=f'</{name}>'
    if not stripped.endswith(closing):raise ValueError('回复格式未完整结束')
    body=stripped[len(name)+2:-len(closing)]
    args={};pos=0
    pattern=re.compile(r'\s*<([a-z_]+)>(.*?)</\1>\s*',re.S)
    while pos<len(body):
        match=pattern.match(body,pos)
        if not match or match[1] in args:raise ValueError('回复字段格式无效')
        args[match[1]]=match[2];pos=match.end()
    expected=set(FIELDS[name])|({'sources'} if name!='explain_requested_scope' else set())
    if set(args)!=expected:raise ValueError('回复字段不完整')
    if 'sources' in args:args['sources']=json.loads(args['sources'])
    return name,args

def text_reply_start(text, *, partial=False, final=True):
    """Locate reserved expression tags outside Markdown fenced/inline code.

    A possible tag prefix at the end of a chunk is held until disambiguated.
    Rescan the bounded model response so chunk boundaries cannot alter parsing.
    """
    tags=[f'<{n}>' for n in FIELDS]
    fence=None;inline=0;offset=0
    for line in text.splitlines(keepends=True):
        marker=re.match(r'^ {0,3}(`{3,}|~{3,})(.*?)(?:\r?\n)?$',line)
        if fence:
            if marker and marker[1][0]==fence[0] and len(marker[1])>=fence[1] and not marker[2].strip() and (line.endswith('\n') or final):fence=None
            offset+=len(line);continue
        if marker and not inline:
            fence=(marker[1][0],len(marker[1]));offset+=len(line);continue
        i=0
        while i<len(line):
            if line[i]=='\\' and not inline:i+=2;continue
            if line[i]=='`':
                end=i+1
                while end<len(line) and line[end]=='`':end+=1
                count=end-i
                if not inline:inline=count
                elif count==inline:inline=0
                i=end;continue
            if not inline and line[i]=='<':
                probe=text[offset+i:]
                if any(probe.startswith(tag) or (partial and tag.startswith(probe)) for tag in tags):return offset+i
            i+=1
        offset+=len(line)
    return None

class TextReplyGate:
    """Hold an ambiguous prefix before any protocol bytes reach the reader.

    Normal prose streams immediately once distinguishable. An accidental text
    envelope waits for full validation; genuine tool arguments still stream.
    """
    def __init__(self):self.text='';self.emitted=0;self.prelude='';self.tail=''
    def feed(self,text):
        self.text+=text
        start=text_reply_start(self.text,partial=True,final=False)
        stop=len(self.text) if start is None else start
        out=self.text[self.emitted:stop];self.emitted=stop
        return out
    def finish(self):
        start=text_reply_start(self.text,partial=True)
        if start is not None and self.text[start:]!='<':
            self.prelude=self.text[:start]
            parsed=parse_text_reply(self.text[start:])
            if not parsed:raise ValueError('回复格式未完整结束')
            return parsed
        self.tail=self.text[self.emitted:]
        return None

def readable_content(text,book_id):
    """Read-time compatibility for old assistant records; retain raw storage."""
    try:
        start=text_reply_start(text)
        if start is None:return text
        parsed=parse_text_reply(text[start:])
        return text[:start]+render(*parsed,book_id)
    except (ValueError,TypeError,KeyError):
        return '这条旧回复的格式或引用不完整，请重新提问。'

def render(name, args, book_id):
    if name not in FIELDS or not isinstance(args,dict):raise ValueError('回复格式无效')
    # Missing optional prose is not a failed reading task. Accept a separate
    # sources list on every presentation, but validate every supplied source.
    args=dict(args)
    for field in {'clarify_meaning':('example',),'map_chapter':('boundary',)}.get(name,()):
        args.setdefault(field,'')
    args.setdefault('sources',[])
    expected=set(FIELDS[name])|{'sources'}
    if set(args)!=expected:raise ValueError('回复字段不完整')
    for field in FIELDS[name]:
        if not isinstance(args[field],str):raise ValueError('回复正文必须为文字')
    if not args[FIELDS[name][0]].strip():raise ValueError('回复没有回答当前问题')
    text='\n\n'.join(args[field] for field in FIELDS[name] if args[field])
    ids=args.get('sources',[])
    if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids):raise ValueError('回复来源格式无效')
    links=[]; unconfirmed=False
    for sid in dict.fromkeys(ids):
        section=s.one('SELECT title FROM sections WHERE id=? AND book_id=?',(sid,book_id))
        if not section:
            unconfirmed=True
            continue
        title=section['title'].replace('\\','\\\\').replace('[','\\[').replace(']','\\]')
        links.append(f'[{title}](/section/{sid})')
    def check_link(match):
        nonlocal unconfirmed
        label,sid=match.groups()
        if s.one('SELECT id FROM sections WHERE id=? AND book_id=?',(sid,book_id)):
            return match.group(0)
        unconfirmed=True
        return label+'（来源链接不可用）'
    text=re.sub(r'\[([^\]]*)\]\(/section/([^\s)]+)\)',check_link,text)
    if links:text+='\n\n'+' · '.join(links)
    if unconfirmed:
        text+='\n\n来源提示：部分引用无法在当前资料中定位，已禁用对应链接；回答的来源尚未确认。有效章节链接也只表示章节存在，不代表逐句事实已核验。'
    return text

def _string_prefix(raw, start):
    """Decode only complete characters of an unfinished JSON string."""
    out=[];i=start+1
    escapes={'"':'"','\\':'\\','/':'/','b':'\b','f':'\f','n':'\n','r':'\r','t':'\t'}
    while i<len(raw):
        char=raw[i]
        if char=='"':return ''.join(out),i+1,True
        if char!='\\':
            if ord(char)<32:break
            out.append(char);i+=1;continue
        if i+1>=len(raw):break
        escape=raw[i+1]
        if escape in escapes:out.append(escapes[escape]);i+=2;continue
        if escape!='u' or i+6>len(raw):break
        try:code=int(raw[i+2:i+6],16)
        except ValueError:break
        if 0xD800<=code<=0xDBFF:
            if i+12>len(raw) or raw[i+6:i+8]!='\\u':break
            try:low=int(raw[i+8:i+12],16)
            except ValueError:break
            if not 0xDC00<=low<=0xDFFF:break
            out.append(chr(0x10000+(code-0xD800)*1024+low-0xDC00));i+=12
        elif 0xDC00<=code<=0xDFFF:break
        else:out.append(chr(code));i+=6
    return ''.join(out),i,False

def stream_prefix(name, raw):
    """Render flat string fields in semantic order, even if keys arrive out of order.

    Source IDs stay private; complete citations are validated and added by render().
    Final JSON validation remains mandatory before the run can complete.
    """
    if name not in FIELDS:return ''
    values={};complete=set();decoder=json.JSONDecoder();i=0
    while i<len(raw) and raw[i].isspace():i+=1
    if i>=len(raw) or raw[i]!='{':return ''
    i+=1
    while i<len(raw):
        while i<len(raw) and (raw[i].isspace() or raw[i]==','):i+=1
        if i>=len(raw) or raw[i]!='"':break
        try:key,end=decoder.raw_decode(raw,i)
        except ValueError:break
        i=end
        while i<len(raw) and raw[i].isspace():i+=1
        if i>=len(raw) or raw[i]!=':':break
        i+=1
        while i<len(raw) and raw[i].isspace():i+=1
        if i>=len(raw):break
        if raw[i]=='"':
            value,i,done=_string_prefix(raw,i)
            if key in FIELDS[name]:values[key]=value
            if not done:break
            complete.add(key)
        else:
            try:_,i=decoder.raw_decode(raw,i)
            except ValueError:break
    parts=[]
    for field in FIELDS[name]:
        if field not in values:break
        if values[field]:parts.append(values[field])
        if field not in complete:break
    return '\n\n'.join(parts)
