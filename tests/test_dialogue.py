import asyncio
import json
import httpx
import pytest
from backend import agent,dialogue,store as s
from test_reading import env,make_run

@pytest.mark.parametrize('ascii_only',[False,True])
def test_prefix_at_every_character_boundary_and_reordered_fields(ascii_only):
    data={'sources':['internal-secret-id'],'example':'例子 "quoted" \\ path\n```py\nx=1\n```','meaning':'观察😀：环境反馈'}
    raw=json.dumps(data,ensure_ascii=ascii_only)
    expected=data['meaning']+'\n\n'+data['example']
    previous=''
    for end in range(len(raw)+1):
        prefix=dialogue.stream_prefix('clarify_meaning',raw[:end])
        assert prefix.startswith(previous)
        assert expected.startswith(prefix)
        assert 'internal-secret-id' not in prefix
        assert not any(0xD800<=ord(c)<=0xDFFF for c in prefix)
        previous=prefix
    assert previous==expected

def test_full_explanation_streams_before_the_json_string_closes():
    raw=json.dumps({'answer':'开始解释\n\n公式：$x^2$\n\n继续推导'},ensure_ascii=False)
    prefix=dialogue.stream_prefix('explain_requested_scope',raw[:raw.index('继续')])
    assert prefix=='开始解释\n\n公式：$x^2$\n\n'

def test_chapter_map_keeps_semantic_order_with_optional_boundary(env):
    _,bid,_,sections=env
    args={'boundary':'','sources':[sections[0]['id']],
          'central_idea':'关键机制','problem':'要解决的问题'}
    raw=json.dumps(args,ensure_ascii=False)
    previous=''
    for end in range(len(raw)+1):
        prefix=dialogue.stream_prefix('map_chapter',raw[:end])
        assert prefix.startswith(previous)
        previous=prefix
    assert previous=='要解决的问题\n\n关键机制'
    assert dialogue.render('map_chapter',args,bid).startswith(previous+'\n\n[')

def test_renderer_validates_sources_without_limiting_depth(env):
    _,bid,other,sections=env
    foreign=s.one('SELECT id FROM sections WHERE book_id=?',(other,))['id']
    assert '来源尚未确认' in dialogue.render('clarify_meaning',{'meaning':'解释','example':'','sources':[foreign]},bid)
    assert f'/section/{foreign}' not in dialogue.render('explain_requested_scope',{'answer':f'[来源](/section/{foreign})'},bid)
    explanation='完整推导\n'*2000
    assert dialogue.render('explain_requested_scope',{'answer':explanation},bid)==explanation
    result=dialogue.render('clarify_meaning',{'meaning':'反馈','example':'','sources':[sections[0]['id']]},bid)
    assert result.startswith('反馈\n\n[')
    assert '{' not in result

class ToolStream(httpx.AsyncByteStream):
    def __init__(self,arguments,extra=None):self.arguments=arguments;self.extra=extra
    async def __aiter__(self):
        def event(delta,finish=None):
            return ('data: '+json.dumps({'choices':[{'delta':delta,'finish_reason':finish}]})+'\n\n').encode()
        yield event({'tool_calls':[{'index':0,'id':'final1','function':{'name':'clarify_meaning','arguments':''}}]})
        for char in self.arguments:
            yield event({'tool_calls':[{'index':0,'function':{'arguments':char}}]})
            await asyncio.sleep(0)
        if self.extra:yield event({'tool_calls':[self.extra]})
        yield event({},'tool_calls')
        yield b'data: [DONE]\n\n'
    async def aclose(self):pass

def install(monkeypatch,stream):
    real=httpx.AsyncClient;requests=[]
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,stream=stream)
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))
    return requests

def test_terminal_reply_is_streamed_saved_and_never_sent_back_to_model(env,monkeypatch):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    args={'meaning':'环境反馈😀','example':'搜索返回的结果','sources':[sections[0]['id']]}
    requests=install(monkeypatch,ToolStream(json.dumps(args,ensure_ascii=True)))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    assert len(requests)==1
    assert requests[0]['max_tokens']==5000
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='complete'
    message=s.one("SELECT content FROM messages WHERE run_id=? AND role='assistant'",(run['id'],))['content']
    assert message==dialogue.render('clarify_meaning',args,bid)
    deltas=[json.loads(e['data'])['text'] for e in s.all_rows("SELECT data FROM events WHERE run_id=? AND type='delta' ORDER BY id",(run['id'],))]
    assert ''.join(deltas)==message
    assert len(deltas)>3
    assert all('sources' not in d for d in deltas)

@pytest.mark.parametrize('failure',['invalid_source','malformed_json','mixed_calls'])
def test_terminal_reply_degrades_bad_sources_but_rejects_invalid_protocol(env,monkeypatch,failure):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    args={'meaning':'反馈','example':'','sources':['missing' if failure=='invalid_source' else sections[0]['id']]}
    raw=json.dumps(args)
    if failure=='malformed_json':raw=raw[:-1]
    extra={'index':1,'id':'nav1','function':{'name':'navigate','arguments':json.dumps({'section_id':sections[0]['id']})}} if failure=='mixed_calls' else None
    install(monkeypatch,ToolStream(raw,extra))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']==('complete' if failure=='invalid_source' else 'failed')
    assert not s.all_rows('SELECT * FROM commands WHERE run_id=?',(run['id'],))
    text=s.one("SELECT content FROM messages WHERE run_id=? AND role='assistant'",(run['id'],))['content']
    assert '反馈' in text and '<clarify_meaning>' not in text
    if failure=='invalid_source':assert '来源尚未确认' in text and '/section/missing' not in text

class TextStream(httpx.AsyncByteStream):
    def __init__(self,text):self.text=text
    async def __aiter__(self):
        for char in self.text:
            yield ('data: '+json.dumps({'choices':[{'delta':{'content':char}}]})+'\n\n').encode()
        yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        yield b'data: [DONE]\n\n'
    async def aclose(self):pass

def test_quoted_question_xml_reply_never_leaks_into_stream_or_saved_message(env,monkeypatch):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    with s.db() as c:c.execute('UPDATE runs SET selected_text=? WHERE id=?',('规划与推理：行动前分解目标',run['id']))
    raw='<clarify_meaning>\n<meaning>行动前分解目标。</meaning>\n<example>先想再行动。</example>\n<sources>'+json.dumps([sections[0]['id']])+'</sources>\n</clarify_meaning>'
    requests=install(monkeypatch,TextStream(raw))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    deltas=''.join(json.loads(e['data'])['text'] for e in s.all_rows("SELECT data FROM events WHERE run_id=? AND type='delta' ORDER BY id",(run['id'],)))
    assert '<clarify_meaning>' not in deltas
    assert '<sources>' not in deltas
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='complete'
    expected=dialogue.render('clarify_meaning',{'meaning':'行动前分解目标。','example':'先想再行动。','sources':[sections[0]['id']]},bid)
    assert deltas==expected
    assert s.one("SELECT content FROM messages WHERE run_id=? AND role='assistant'",(run['id'],))['content']==expected
    assert len(requests)==1

@pytest.mark.parametrize('text',[
    '普通回答：a < b，`<meaning>` 是代码。',
    '```xml\n<clarify_meaning><meaning>合法代码示例</meaning></clarify_meaning>\n```',
    '<article>HTML 教材内容 & 普通标签</article>',
])
def test_ordinary_prose_and_code_still_stream_unchanged(env,monkeypatch,text):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    install(monkeypatch,TextStream(text))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='complete'
    deltas=[json.loads(e['data'])['text'] for e in s.all_rows("SELECT data FROM events WHERE run_id=? AND type='delta' ORDER BY id",(run['id'],))]
    assert ''.join(deltas)==text
    assert len(deltas)>2

@pytest.mark.parametrize('variant',['truncated','invalid_source','duplicate_field','extra_field','trailing_operation'])
def test_text_protocol_rejects_broken_structure_and_degrades_foreign_source(env,monkeypatch,variant):
    _,bid,other,sections=env;run=make_run(bid,sections[0]['id'])
    sid=sections[0]['id']
    if variant=='invalid_source':sid=s.one('SELECT id FROM sections WHERE book_id=?',(other,))['id']
    raw='<clarify_meaning><meaning>定义</meaning><example></example><sources>'+json.dumps([sid])+'</sources></clarify_meaning>'
    if variant=='truncated':raw=raw[:-8]
    if variant=='duplicate_field':raw=raw.replace('<example>','<meaning>重复</meaning><example>')
    if variant=='extra_field':raw=raw.replace('<example>','<execute>删除</execute><example>')
    if variant=='trailing_operation':raw+='<navigate><section_id>'+sid+'</section_id></navigate>'
    install(monkeypatch,TextStream(raw))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    state=s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']
    assert state==('complete' if variant=='invalid_source' else 'failed')
    rows=s.all_rows("SELECT * FROM messages WHERE run_id=? AND role='assistant'",(run['id'],))
    if variant=='invalid_source':
        assert '定义' in rows[0]['content'] and '来源尚未确认' in rows[0]['content']
        assert '/section/'+sid not in rows[0]['content'] and '<clarify_meaning>' not in rows[0]['content']
    else:
        assert not s.all_rows("SELECT * FROM events WHERE run_id=? AND type='delta'",(run['id'],))
        assert not rows
    assert not s.all_rows('SELECT * FROM commands WHERE run_id=?',(run['id'],))

@pytest.mark.parametrize('name',list(dialogue.FIELDS))
def test_text_fallback_supports_known_reply_forms_and_field_order(env,name):
    _,bid,_,sections=env
    args={field:'比较 x < y & z；'+field for field in dialogue.FIELDS[name]}
    if name!='explain_requested_scope':args['sources']=[sections[0]['id']]
    raw=f'<{name}>'+''.join(f'<{k}>{json.dumps(v) if k=="sources" else v}</{k}>' for k,v in reversed(list(args.items())))+f'</{name}>'
    assert dialogue.parse_text_reply(raw)==(name,args)
    assert dialogue.readable_content(raw,bid)==dialogue.render(name,args,bid)

def test_old_reply_is_readable_without_rewriting_storage_or_poisoning_history(env,monkeypatch):
    client,bid,_,sections=env;sid=sections[0]['id'];mid=s.uid()
    old=make_run(bid,sid,'old-reply')
    raw='<clarify_meaning><meaning>旧定义</meaning><example></example><sources>'+json.dumps([sid])+'</sources></clarify_meaning>'
    with s.db() as c:
        c.execute("UPDATE runs SET status='complete' WHERE id=?",(old['id'],))
        c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)',(mid,bid,old['id'],'assistant',raw,sid,s.now()-10))
    response=client.get('/api/books/'+bid+'/messages').json()[0]['content']
    assert response.startswith('旧定义\n\n[') and '<clarify_meaning>' not in response
    assert s.one('SELECT content FROM messages WHERE id=?',(mid,))['content']==raw
    assert '<clarify_meaning>' not in agent.search(bid,'旧定义',True)[0]['content']
    run=make_run(bid,sid)
    history=asyncio.run(agent.execute_tool(run,'read_history',{'message_id':mid}))
    assert '<clarify_meaning>' not in history[0]['content']
    requests=install(monkeypatch,TextStream('接着解释。'))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    replay=next(m['content'] for m in requests[0]['messages'] if m['role']=='assistant')
    assert replay==response

@pytest.mark.parametrize('prefix',['我来解释。\n','Here is the explanation: ','<p>A normal HTML preface.</p>\n'])
def test_text_protocol_after_preface_never_leaks(env,monkeypatch,prefix):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    args={'meaning':'定义','example':'实例','sources':[sections[0]['id']]}
    raw=prefix+'<clarify_meaning><meaning>定义</meaning><example>实例</example><sources>'+json.dumps(args['sources'])+'</sources></clarify_meaning>'
    install(monkeypatch,TextStream(raw))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    visible=''.join(json.loads(e['data'])['text'] for e in s.all_rows("SELECT data FROM events WHERE run_id=? AND type='delta' ORDER BY id",(run['id'],)))
    assert visible==prefix+dialogue.render('clarify_meaning',args,bid)
    assert '<sources>' not in visible and '<clarify_meaning>' not in visible
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='complete'
    assert dialogue.readable_content(raw,bid)==visible


def test_broken_protocol_after_preface_only_emits_preface(env,monkeypatch):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    raw='Preface.\n<clarify_meaning><meaning>incomplete</meaning><sources>["private-id"]'
    install(monkeypatch,TextStream(raw))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    visible=''.join(json.loads(e['data'])['text'] for e in s.all_rows("SELECT data FROM events WHERE run_id=? AND type='delta' ORDER BY id",(run['id'],)))
    assert visible=='Preface.\n'
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='failed'
    assert 'private-id' not in dialogue.readable_content(raw,bid)


@pytest.mark.parametrize('code',[
    'Example: `<clarify_meaning><sources>["id"]</sources></clarify_meaning>`.',
    'Example:\n```xml\n<clarify_meaning><sources>["id"]</sources></clarify_meaning>\n```',
    'Example:\n````md\n```xml\n<clarify_meaning><sources>["id"]</sources></clarify_meaning>\n```\n````',
    'Compare x < y. An unfinished inequality: x <',
])
def test_protocol_examples_in_code_and_plain_less_than_are_preserved(env,monkeypatch,code):
    _,bid,_,sections=env;run=make_run(bid,sections[0]['id'])
    install(monkeypatch,TextStream(code))
    asyncio.run(agent.run_agent(run['id'],agent.stream_model))
    visible=''.join(json.loads(e['data'])['text'] for e in s.all_rows("SELECT data FROM events WHERE run_id=? AND type='delta' ORDER BY id",(run['id'],)))
    assert visible==code
    assert dialogue.readable_content(code,bid)==code
    assert s.one('SELECT status FROM runs WHERE id=?',(run['id'],))['status']=='complete'
