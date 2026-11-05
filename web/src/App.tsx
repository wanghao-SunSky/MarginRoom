import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import {flushSync} from 'react-dom';
import { ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUp, BookOpen, Bookmark, Check, ChevronDown, ChevronRight, FileText, Layers, Library, LoaderCircle, MessageSquare, PanelLeftClose, Plus, Search, Square, X } from 'lucide-react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import PdfPage from './PdfPage';
import PdfOutline,{type PdfBookmark} from './PdfOutline';
import {selectedReadingText} from './selection';
import {PageTurnGesture,atReadingEnd,showIncomplete} from './page-turn';
import {getLanguage,translate,type Language} from './i18n';

type Book={id:string,title:string,subtitle:string,format:string,color:string,section_count:number,read_count:number,chapter_count:number,last_section?:string,missing_pages:number,replacement_id?:string|null};
type Section={id:string,book_id:string,title:string,chapter:string,ordinal:number,content:string,page:number|null,is_read:number};
type Detail=Book&{sections:Section[],outline?:PdfBookmark[],blank_pages?:number[],image_pages?:number[],warnings?:string[]};
type Message={id:string,role:string,content:string,section_id:string,run_status?:string,run_error?:string};
type Artifact={id:string,kind:string,title:string,content:string,section_id:string};
type Card={id:string,front:string,back:string,section_id:string};
type Command={id:string,client_id:string,action:string,section_id:string,expected_revision:number};
async function api<T=any>(url:string,body?:unknown,method='POST'):Promise<T>{
 const res=await fetch('/api'+url,body===undefined?{headers:{'X-Reading-Language':getLanguage()}}:{method,headers:{'Content-Type':'application/json','X-Reading-Language':getLanguage()},body:JSON.stringify(body)});

 if(!res.ok){let d;try{d=await res.json();}catch{throw Error(translate(getLanguage(),'服务连接失败，请确认本地服务正在运行。'));}throw Error(typeof d.detail==='string'?d.detail:translate(getLanguage(),'请求参数无效，请重试。'));}return res.json();
}
const uid=()=>crypto.randomUUID();
const CLIENT=sessionStorage.getItem('reading-client')||uid();sessionStorage.setItem('reading-client',CLIENT);
const toolNames:Record<string,string>={get_reading_state:'查看已读记录',get_outline:'查看目录',read_section:'阅读原文',read_chapter:'阅读整章',search_book:'搜索书中内容',search_history:'查找过去的讨论',read_history:'回看原始对话',navigate:'等待页面跳转',return_to:'返回阅读位置',save_artifact:'保存学习记录',create_cards:'整理复习卡片'};
const labels:Record<string,string>={note:'笔记',summary:'章节小结',review:'学习回顾'};
export default function App(){
 const [language,setLanguage]=useState<Language>(getLanguage);
 const t=(text:string,values:Record<string,string|number>={})=>translate(language,text,values);
 function changeLanguage(next:Language){localStorage.setItem('reading-language',next);setLanguage(next);window.dispatchEvent(new Event('reading-language'));}
 useEffect(()=>{document.documentElement.lang=language==='zh'?'zh-CN':'en';document.title=language==='zh'?'阅间 · 和 AI 一起读懂':'MarginRoom · Read difficult things, together';},[language]);
 const [books,setBooks]=useState<Book[]>([]),[book,setBook]=useState<Detail|null>(null),[section,setSection]=useState<Section|null>(null);
 const [messages,setMessages]=useState<Message[]>([]),[artifacts,setArtifacts]=useState<Artifact[]>([]),[configured,setConfigured]=useState(false);
 const [library,setLibrary]=useState(false),[left,setLeft]=useState(false),[mobile,setMobile]=useState('read'),[tab,setTab]=useState('chat');
 const [query,setQuery]=useState(''),[collapsed,setCollapsed]=useState<Set<string>>(new Set()),[draft,setDraft]=useState(''),[selection,setSelection]=useState('');
 const [highlighted,setHighlighted]=useState(false),[saving,setSaving]=useState(false),savingRef=useRef(false);
 const cardSaves=useRef(new Map<string,Promise<void>>()),cardVersions=useRef(new Map<string,string>());
 const searchVersion=useRef(0),recordsVersion=useRef(0);
 const [idleSeconds,setIdleSeconds]=useState(0),lastProgress=useRef(Date.now());
 const [busy,setBusy]=useState(''),[stream,setStream]=useState(''),[trace,setTrace]=useState<string[]>([]),[error,setError]=useState(''),[importError,setImportError]=useState(''),[notice,setNotice]=useState('');
 const [uploading,setUploading]=useState(false),[pdf,setPdf]=useState(true),[editing,setEditing]=useState<Artifact|null>(null),[editText,setEditText]=useState(''),[editTitle,setEditTitle]=useState('');
 const [historyQuery,setHistoryQuery]=useState(''),[historyResults,setHistoryResults]=useState<Message[]|null>(null),[revealed,setRevealed]=useState<Set<string>>(new Set());
 const view=useRef({book:'',section:'',revision:Number(sessionStorage.getItem('reading-revision')||0)}),stack=useRef<string[]>([]),streamRef=useRef<{close:()=>void}|null>(null),active=useRef('');
 const paper=useRef<HTMLDivElement>(null),chatScroll=useRef<HTMLDivElement>(null),composer=useRef<HTMLTextAreaElement>(null),file=useRef<HTMLInputElement>(null),navPending=useRef(new Set<string>());
 const follow=useRef(true),lastChatTop=useRef(0);
 const [readingPaused,setReadingPaused]=useState(false);
 const [autoPage,setAutoPage]=useState(()=>localStorage.getItem('reading-scroll-turn')!=='off');
 const pageGesture=useRef(new PageTurnGesture()),turning=useRef(false),touchStart=useRef<{y:number,atEnd:boolean}|null>(null);
 const [streamStatus,setStreamStatus]=useState('');
 const [pdfReady,setPdfReady]=useState('');
 function toggleAutoPage(){setAutoPage(value=>{localStorage.setItem('reading-scroll-turn',value?'off':'on');return !value;});pageGesture.current.reset();}
 function canTurn(){const ready=book?.format!=='pdf'||!pdf||book.blank_pages?.includes(section?.page||0)||pdfReady===view.current.section;return ready&&autoPage&&!turning.current&&!library&&!editing&&!!paper.current?.clientHeight&&!selectedReadingText(paper.current,window.getSelection());}
 async function turnNext(){if(!canTurn()||!book)return;const index=book.sections.findIndex(x=>x.id===view.current.section);if(index<0||index>=book.sections.length-1)return;turning.current=true;try{await go(book.sections[index+1].id,false);}finally{turning.current=false;}}
 function pauseReading(){follow.current=false;setReadingPaused(true);}
 function followLatest(){follow.current=true;setReadingPaused(false);const el=chatScroll.current;if(el){el.scrollTop=el.scrollHeight;lastChatTop.current=el.scrollTop;}}
 function clearSelection(){setSelection('');setHighlighted(false);window.getSelection()?.removeAllRanges();}
 function captureSelection(){const text=selectedReadingText(paper.current,window.getSelection());setSelection(text);setHighlighted(!!text);}
 function openLibrary(){clearSelection();setLibrary(true);void refreshLibrary().catch(showError);}
 function closeEditor(){if(savingRef.current)return;setEditing(null);clearSelection();}
 useEffect(()=>{const update=()=>{const text=selectedReadingText(paper.current,window.getSelection());setHighlighted(!!text);if(text)setSelection(text);};document.addEventListener('selectionchange',update);return()=>document.removeEventListener('selectionchange',update);},[]);
 const stacksKey=(bid:string)=>'return-'+CLIENT+'-'+bid;
 function bump(){view.current.revision++;sessionStorage.setItem('reading-revision',String(view.current.revision));}
 function saveStack(){sessionStorage.setItem(stacksKey(view.current.book),JSON.stringify(stack.current));}
 async function refreshLibrary(){const rows=await api<Book[]>('/books');setBooks(rows);return rows;}
 async function refreshRecords(bid:string){if(view.current.book!==bid)return;const version=++recordsVersion.current;const [ms,as]=await Promise.all([api<Message[]>(`/books/${bid}/messages`),api<Artifact[]>(`/books/${bid}/artifacts`)]);if(view.current.book===bid&&recordsVersion.current===version){setMessages(ms);setArtifacts(as);}}
 function showError(e:unknown){setError(e instanceof Error?e.message:String(e));}
 async function openBook(bid:string,sid?:string){
  followLatest();streamRef.current?.close();active.current='';setBusy('');setStream('');setTrace([]);bump();view.current.book=bid;view.current.section='';setBook(null);setSection(null);setMessages([]);setArtifacts([]);clearSelection();searchVersion.current++;setHistoryResults(null);setHistoryQuery('');setQuery('');setError('');
  try{const b=await api<Detail>('/books/'+bid);if(view.current.book!==bid)return;setBook(b);setCollapsed(new Set(b.sections.map(x=>x.chapter).filter((_,i)=>i>0)));stack.current=JSON.parse(sessionStorage.getItem(stacksKey(bid))||'[]');
   const target=(b.sections.some(x=>x.id===sid)?sid:undefined)||books.find(x=>x.id===bid)?.last_section||b.sections[0]?.id;if(target)await go(target,false);
   await refreshRecords(bid);if(view.current.book!==bid)return;setLibrary(false);setLeft(false);
   const run=sessionStorage.getItem('run-'+bid);if(run){const r=await api('/runs/'+run);if(view.current.book!==bid)return;if(r.status==='running')connect(run,bid);else{sessionStorage.removeItem('run-'+bid);if(r.error)setError(r.error);}}
  }catch(e){showError(e);}
 }
 async function go(sid:string,push=true){
  const bid=view.current.book,old=view.current.section;bump();const rev=view.current.revision;
  try{const next=await api<Section>('/sections/'+sid);if(next.book_id!==bid||view.current.book!==bid||view.current.revision!==rev)return false;
   if(push&&old&&old!==sid){stack.current.push(old);saveStack();}
   view.current.section=sid;setSection(next);setBooks(rows=>rows.map(b=>b.id===bid?{...b,last_section:sid}:b));clearSelection();setLeft(false);setCollapsed(v=>{const n=new Set(v);n.delete(next.chapter);return n;});
   paper.current?.scrollTo({top:0});history.replaceState(null,'',`?book=${bid}&section=${sid}`);
   await api(`/books/${bid}/position`,{section_id:sid},'PUT');return true;
  }catch(e){showError(e);return false;}
 }
 async function back(){const id=stack.current.at(-1);if(!id){setNotice(t('还没有可返回的阅读位置'));return;}if(await go(id,false)){stack.current.pop();saveStack();}}
 async function handleNavigation(cmd:Command,bid:string){
  if(cmd.client_id!==CLIENT||navPending.current.has(cmd.id))return;navPending.current.add(cmd.id);
  const cache=sessionStorage.getItem('ack-'+cmd.id);if(cache){try{await api(`/commands/${cmd.id}/ack`,JSON.parse(cache));}finally{navPending.current.delete(cmd.id);}return;}
  let status='stale',ackRevision=view.current.revision;let target=cmd.action==='return_to'?stack.current.at(-1):cmd.section_id;
  if(view.current.book===bid&&view.current.revision===cmd.expected_revision){
   if(!target)status='empty_stack';else{
    try{const next=await api<Section>('/sections/'+target);
     if(view.current.book===bid&&view.current.revision===cmd.expected_revision&&next.book_id===bid){
      const old=view.current.section;bump();const appliedRev=view.current.revision;view.current.section=target;
      // Commit the reader DOM without waiting for animation frames, which
      // browsers suspend in background tabs. Acknowledge this exact revision.
      flushSync(()=>setSection(next));setBooks(rows=>rows.map(b=>b.id===bid?{...b,last_section:target}:b));clearSelection();setCollapsed(v=>{const n=new Set(v);n.delete(next.chapter);return n;});
      if(view.current.revision===appliedRev){status='applied';ackRevision=appliedRev;if(cmd.action==='return_to')stack.current.pop();else if(old!==target)stack.current.push(old);saveStack();history.replaceState(null,'',`?book=${bid}&section=${target}`);await api(`/books/${bid}/position`,{section_id:target},'PUT');setNotice(cmd.action==='return_to'?t('已回到之前的位置'):t('已跳转 · 可以随时返回'));}
     }
    }catch{status='stale';}
   }
  }
  const ack={client_id:CLIENT,status,section_id:status==='applied'?target:null,view_revision:ackRevision};sessionStorage.setItem('ack-'+cmd.id,JSON.stringify(ack));try{await api(`/commands/${cmd.id}/ack`,ack);}finally{navPending.current.delete(cmd.id);}
 }
 function connect(rid:string,bid:string){
  streamRef.current?.close();active.current=rid;setBusy(rid);setStream('');setStreamStatus('running');setTrace([]);lastProgress.current=Date.now();setIdleSeconds(0);sessionStorage.setItem('run-'+bid,rid);
  const es=new EventSource('/api/runs/'+rid+'/events');const seen=new Set<string>();
  let polling=false;
  const close=()=>{es.close();clearInterval(poll);};
  const finish=(d:any)=>{if(active.current!==rid)return;close();active.current='';setStreamStatus(d.status);setBusy('');sessionStorage.removeItem('run-'+bid);if(d.error)setError(d.error);void refreshRecords(bid).then(()=>{if(d.status==='complete'&&view.current.book===bid&&!active.current)setStream('');}).catch(showError);};
  const poll=setInterval(async()=>{if(polling||active.current!==rid)return;polling=true;try{const res=await fetch('/api/runs/'+rid,{signal:AbortSignal.timeout(5000),headers:{'X-Reading-Language':getLanguage()}});if(res.ok){const r=await res.json();if(r.status!=='running')finish(r);}}catch{/* The visible waiting timer remains active during reconnection. */}finally{polling=false;}},10000);
  streamRef.current={close};
  const listen=(type:string,fn:(d:any)=>void)=>es.addEventListener(type,(ev)=>{const e=ev as MessageEvent;if(typeof e.data!=='string')return;if(e.lastEventId&&seen.has(e.lastEventId))return;if(e.lastEventId)seen.add(e.lastEventId);if(active.current!==rid)return;fn(JSON.parse(e.data));});
  listen('delta',d=>{lastProgress.current=Date.now();setIdleSeconds(0);setStream(v=>v+d.text);});
  listen('replace',d=>{lastProgress.current=Date.now();setIdleSeconds(0);setStream(d.text);});
  listen('tool',d=>{lastProgress.current=Date.now();setIdleSeconds(0);if(d.status==='running')setTrace(v=>[...v,d.name]);});
  listen('navigation',d=>{void handleNavigation(d,bid).catch(showError);});
  listen('artifact',()=>{void refreshRecords(bid).catch(showError);});
  listen('error',d=>setError(d.message));
  listen('cancelled',d=>setNotice(d.message));
  listen('terminal',finish);
  es.onerror=(event)=>{if('data' in event)return;if(active.current===rid)setNotice(t('连接中断，正在恢复回答；也可以停止本次请求。'));};
 }
 async function send(text=draft,task_kind='chat'){
  if(!text.trim()||busy||!section||!book)return;followLatest();lastProgress.current=Date.now();setIdleSeconds(0);setBusy('pending');setStream('');setTrace([]);setStreamStatus('running');setError('');setNotice('');setTab('chat');setMobile('chat');
  const bid=book.id,rid=uid(),question=text.trim();
  try{await api('/runs',{id:rid,book_id:bid,section_id:view.current.section,client_id:CLIENT,question,selected_text:selection,language,task_kind,view_revision:view.current.revision});sessionStorage.setItem('run-'+bid,rid);if(view.current.book!==bid)return;setDraft('');clearSelection();await refreshRecords(bid);if(view.current.book===bid)connect(rid,bid);}catch(e){if(view.current.book===bid){setBusy('');showError(e);}}
 }
 async function markRead(){if(!book||!section)return;const bid=book.id,sid=section.id,read=!book.sections.find(x=>x.id===sid)?.is_read;await api('/sections/'+sid+'/read',{read},'PUT');setBook(current=>current?.id===bid?{...current,sections:current.sections.map(x=>x.id===sid?{...x,is_read:read?1:0}:x)}:current);await refreshLibrary();}
 async function importFile(f?:File){if(!f)return;setUploading(true);setImportError('');setNotice('');try{const data=new FormData();data.append('file',f);const res=await fetch('/api/import',{method:'POST',body:data,headers:{'X-Reading-Language':language}});const d=await res.json();if(!res.ok)throw Error(d.detail);await refreshLibrary();await openBook(d.id);setNotice(d.created?t('资料已导入，可以开始阅读'):t('这份资料已在书架，已为你打开'));}catch(e){setImportError(e instanceof Error?e.message:String(e));}finally{setUploading(false);if(file.current)file.current.value='';}}
 function newNote(){if(!section)return;setEditing({id:'',kind:'note',title:section.title,content:'',section_id:section.id});setEditTitle(section.title);setEditText(selection?selection.split('\n').map(line=>'> '+line).join('\n')+'\n\n':'');clearSelection();}
 async function saveEdit(){
  if(!editing||!book||savingRef.current)return;const bid=book.id;savingRef.current=true;setSaving(true);
  try{if(editing.id)await api('/artifacts/'+editing.id,{title:editTitle,content:editText,expected_content:editing.content},'PATCH');else await api('/books/'+bid+'/artifacts',{kind:'note',title:editTitle,content:editText,section_id:editing.section_id});
   setEditing(null);clearSelection();await refreshRecords(bid);if(view.current.book===bid){setTab('notes');setMobile('chat');setNotice(t('笔记已保存'));}
  }catch(e){showError(e);}finally{savingRef.current=false;setSaving(false);}
 }
 function editCard(a:Artifact,c:Card,field:'front'|'back',value:string){
  const bid=view.current.book;
  const pending=(cardSaves.current.get(a.id)||Promise.resolve()).catch(()=>{}).then(async()=>{
   const previous=cardVersions.current.get(a.id)||a.content;
   const cards:Card[]=JSON.parse(previous);const content=JSON.stringify(cards.map(x=>x.id===c.id?{...x,[field]:value}:x));
   try{await api('/artifacts/'+a.id,{title:a.title,content,expected_content:previous},'PATCH');cardVersions.current.set(a.id,content);await refreshRecords(bid);}
   catch(e){cardVersions.current.delete(a.id);throw e;}
  });cardSaves.current.set(a.id,pending);void pending.finally(()=>{if(cardSaves.current.get(a.id)===pending){cardSaves.current.delete(a.id);cardVersions.current.delete(a.id);}}).catch(()=>{});return pending;
 }
 async function searchHistory(){if(!book)return;const bid=book.id,version=++searchVersion.current;try{const rows=await api<Message[]>(`/books/${bid}/history?q=${encodeURIComponent(historyQuery)}`);if(view.current.book===bid&&version===searchVersion.current)setHistoryResults(rows);}catch(e){if(view.current.book===bid&&version===searchVersion.current)showError(e);}}

 useEffect(()=>{void (async()=>{try{const [list,status]=await Promise.all([refreshLibrary(),api('/status')]);setConfigured(status.configured);const q=new URLSearchParams(location.search);const b=list.find(x=>x.id===q.get('book'))||list.find(x=>x.last_section&&!x.replacement_id)||list.find(x=>x.title===(language==='zh'?'和 AI 一起阅读':'Reading with AI'))||list[0];if(b)await openBook(b.id,q.get('section')||b.last_section);else setLibrary(true);}catch(e){showError(e);}})();return()=>streamRef.current?.close();},[]);
 useEffect(()=>{if(!busy)return;const timer=setInterval(()=>setIdleSeconds(Math.floor((Date.now()-lastProgress.current)/1000)),1000);return()=>clearInterval(timer);},[busy]);
 useLayoutEffect(()=>{paper.current?.scrollTo({top:0});setPdfReady('');},[section?.id]);
 useLayoutEffect(()=>{
  const el=chatScroll.current;if(!el||historyResults)return;
  if(follow.current){el.scrollTop=el.scrollHeight;lastChatTop.current=el.scrollTop;}
 },[stream,messages,busy,trace,tab,mobile,historyResults]);
 useEffect(()=>{if(!notice)return;const t=setTimeout(()=>setNotice(''),4500);return()=>clearTimeout(t);},[notice]);
 useEffect(()=>{const f=(e:KeyboardEvent)=>{if(e.key==='Escape'){if(savingRef.current)return;setLibrary(false);setEditing(null);setLeft(false);clearSelection();}};window.addEventListener('keydown',f);return()=>window.removeEventListener('keydown',f);},[]);
 const currentIndex=book?.sections.findIndex(x=>x.id===section?.id)??0;
 const groups=book?Array.from(new Set(book.sections.map(x=>x.chapter))):[];
 const readCount=book?.sections.filter(x=>x.is_read).length||0;
 const cards=artifacts.filter(a=>a.kind==='cards');const cardCount=cards.reduce((n,a)=>n+JSON.parse(a.content).length,0);
 function md(content:string,cls=''){return <div className={'markdown '+cls}><Markdown remarkPlugins={[remarkGfm,remarkMath]} rehypePlugins={[[rehypeKatex,{strict:false,trust:false}]]} components={{a:({href,children})=>href?.startsWith('/section/')?<button className="source-link" onClick={()=>void go(href.slice(9))}>{children}</button>:<a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,img:({src,alt})=>cls==='book-text'&&src?.startsWith(`/api/books/${book?.id}/assets/`)?<img className="ebook-image" src={src} alt={alt||''} loading="lazy"/>:<span className="image-placeholder">[{t('插图：{alt}，请在原资料中查看',{alt:alt||t('外部图片')})}]</span>}}>{content}</Markdown></div>;}
 const button=(title:string,icon:ReactNode,fn:()=>void,disabled=false)=><button className="icon-button" title={title} aria-label={title} onClick={fn} disabled={disabled}>{icon}</button>;
 return <div className={'app mobile-'+mobile}>
  <header className="topbar"><button className="brand" onClick={openLibrary}><span className="brand-mark"><BookOpen size={20}/></span><strong>{t('阅间')}</strong><span className="brand-sub">{t('把难懂的，读进去。')}</span></button><div className="top-actions"><div className="language-switch" role="group" aria-label={t('界面语言')}>
    <button type="button" lang="zh-CN" aria-label="切换为中文" aria-pressed={language==='zh'} onClick={()=>changeLanguage('zh')}>中文</button>
    <span className="language-divider" aria-hidden="true"/>
    <button type="button" lang="en" aria-label="Switch to English" aria-pressed={language==='en'} onClick={()=>changeLanguage('en')}>EN</button>
   </div><span className="local-tag">{t('个人阅读空间')}</span><button className="quiet" onClick={openLibrary}><Library size={16}/> {t('我的书架')}</button><button className="import-button" onClick={()=>file.current?.click()} disabled={uploading}><Plus size={16}/>{uploading?t('正在导入…'):t('导入资料')}</button></div></header>
  <input ref={file} type="file" accept=".md,.txt,.pdf,.epub,.mobi,.azw3" hidden onChange={e=>void importFile(e.target.files?.[0])}/>
  <nav className="mobile-nav"><button onClick={()=>setLeft(!left)}>{t('目录')}</button><button className={mobile==='read'?'active':''} onClick={()=>setMobile('read')}>{t('阅读')}</button><button className={mobile==='chat'?'active':''} onClick={()=>setMobile('chat')}>{t('同读与笔记')}</button></nav>
  <div className="workspace">
   <aside className={'outline '+(left?'visible':'')}>
    <div className="outline-top"><span className="eyebrow">{t('正在阅读')}</span>{button(t('收起目录'),<PanelLeftClose size={16}/>,()=>setLeft(false))}</div>
    <button className={'current-book '+(book?.color||'teal')} onClick={openLibrary}><div className="mini-cover"><BookOpen size={20}/></div><span><b>{book?.title||t('选择一本资料')}</b><small>{book?.format==='pdf'?t('PDF 文档'):t('学习资料')}</small></span><ChevronDown size={15}/></button>
    <div className="progress-label"><span>{book?.format==='pdf'?(language==='zh'?`已读 ${readCount} / ${book.sections.length} 页`:`Read ${readCount} / ${book.sections.length} pages`):t('已读 {count} / {total} 节',{count:readCount,total:book?.sections.length||0})}</span><span>{book?Math.round(readCount/book.sections.length*100):0}%</span></div><div className="progress-track"><div style={{width:`${book?readCount/book.sections.length*100:0}%`}}/></div>
    <label className="outline-search"><Search size={14}/><input aria-label={t('搜索目录')} placeholder={t('搜索目录')} value={query} onChange={e=>setQuery(e.target.value)}/><kbd>{t('目录')}</kbd></label>
    <div className="toc">{book?.outline?.length?<PdfOutline key={book.id} items={book.outline} current={section?.id} query={query} onNavigate={id=>void go(id)} english={language==='en'}/>:groups.map((g,i)=>{const children=book!.sections.filter(x=>x.chapter===g&&(!query||x.title.toLowerCase().includes(query.toLowerCase())||g.toLowerCase().includes(query.toLowerCase())));if(!children.length)return null;const closed=collapsed.has(g)&&!query;return <div className="toc-group" key={g}><button className="chapter" onClick={()=>setCollapsed(v=>{const n=new Set(v);n.has(g)?n.delete(g):n.add(g);return n;})}><span className="chapter-no">{String(i+1).padStart(2,'0')}</span><span>{g.replace(/^第\s*\d+\s*[讲课章]\s*[：:]?\s*/,'')}</span>{closed?<ChevronRight size={13}/>:<ChevronDown size={13}/>}</button>{!closed&&children.map(x=><button key={x.id} className={'toc-section '+(x.id===section?.id?'selected':'')} onClick={()=>void go(x.id)}><span className={'read-dot '+(x.is_read?'done':'')}>{x.is_read?<Check size={9}/>:null}</span><span>{x.title}</span></button>)}</div>;})}</div>
    <div className="outline-bottom"><span className="status-dot"/>{t('位置自动保存')}<span>{t('本机存储')}</span></div>
   </aside>
   <main className="reader">
    <div className="reader-toolbar"><div className="breadcrumb">{button(t('显示目录'),<BookOpen size={17}/>,()=>setLeft(!left))}<span>{section?.chapter||t('阅读，从一个问题开始')}</span></div><div className="reader-controls"><button className="scroll-turn-toggle" aria-pressed={autoPage} title={t('页底继续滚动即可翻到下一节')} onClick={toggleAutoPage}>{t('滚动翻页')}</button>{button(t('返回阅读位置'),<ArrowLeft size={16}/>,()=>void back(),!stack.current.length)}<span>{section?currentIndex+1:0}<i> / {book?.sections.length||0}</i></span>{button(t('上一节'),<ChevronRight className="rotate" size={17}/>,()=>void go(book!.sections[currentIndex-1].id,false),!book||currentIndex<=0)}{button(t('下一节'),<ChevronRight size={17}/>,()=>void go(book!.sections[currentIndex+1].id,false),!book||currentIndex>=book.sections.length-1)}</div></div>
    {book?.replacement_id&&<div className="example-update"><span>{t('这份入门示例已有新版，旧笔记与讨论保留在这里。')}</span><button onClick={()=>void openBook(book.replacement_id!)}>{t('打开新版入门')} <ArrowRight size={15}/></button></div>}
    <div className="paper-scroll" ref={paper} tabIndex={0} aria-label={t('阅读正文')}
     onWheel={e=>{if(canTurn()&&pageGesture.current.wheel(atReadingEnd(e.currentTarget),e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?e.currentTarget.clientHeight:1),performance.now()))void turnNext();}}
     onTouchStart={e=>{touchStart.current=e.touches.length===1?{y:e.touches[0].clientY,atEnd:atReadingEnd(e.currentTarget)}:null;}}
     onTouchEnd={e=>{const start=touchStart.current;touchStart.current=null;captureSelection();if(start?.atEnd&&e.changedTouches.length===1&&start.y-e.changedTouches[0].clientY>70&&atReadingEnd(e.currentTarget))void turnNext();}}
     onKeyDown={e=>{if(e.target===e.currentTarget&&!e.shiftKey&&(e.key==='PageDown'||e.key===' ')&&atReadingEnd(e.currentTarget)&&canTurn()){e.preventDefault();void turnNext();}}}
     onMouseUp={captureSelection} onKeyUp={captureSelection}>
     {section?<><div className="reading-meta"><span className="eyebrow">{book?.format==='pdf'?`PAGE ${section.page}`:`SECTION ${String(currentIndex+1).padStart(2,'0')}`}</span><span>{t('{count} 分钟阅读',{count:Math.max(1,Math.ceil(section.content.length/500))})}{book?.format==='pdf'&&<button onClick={()=>setPdf(!pdf)}>{pdf?t('查看提取文本'):t('查看原版 PDF')}</button>}</span></div>
      {book?.warnings?.map((message,i)=><p className="pdf-text-hint" key={i}>{message}</p>)}
      {book?.missing_pages? <div className="coverage-note">{t('这份 PDF 有 {count} 页未提取到文字，AI 无法阅读这些页面。原版仍可查看。',{count:book.missing_pages})}</div>:null}
      {book?.format==='pdf'&&!pdf&&!book.blank_pages?.includes(section.page||0)&&<p className="pdf-text-hint">{language==='zh'?'文字视图不包含图表，可切换原版 PDF 对照。':'Text view does not include figures. Switch to the original PDF to view them.'}</p>}
      <article className="paper">{book?.blank_pages?.includes(section.page||0)?<div className="pdf-blank"><BookOpen size={30}/><p>{language==='zh'?'这是原书的空白页':'This page is blank in the original book'}</p>{book.sections.slice(currentIndex+1).find(x=>!book.blank_pages?.includes(x.page||0))&&<button className="quiet" onClick={()=>{const next=book.sections.slice(currentIndex+1).find(x=>!book.blank_pages?.includes(x.page||0));if(next)void go(next.id,false);}}>{language==='zh'?'继续阅读下一页内容':'Continue to the next page with content'} <ArrowRight size={15}/></button>}</div>:book?.format==='pdf'&&pdf?<PdfPage book={book.id} page={section.page||1} language={language} onReady={()=>setPdfReady(section.id)}/>:book?.format==='text'?<div className="book-text plain-text">{section.content}</div>:md(section.content,'book-text')}</article>
      <div className="reading-end"><span className="end-rule"/><span>{t('停一下，试着用自己的话解释。')}</span><span className="end-rule"/></div>
      <div className="reading-footer"><button className={'quiet '+(book?.sections[currentIndex]?.is_read?'is-read':'')} onClick={()=>void markRead().catch(showError)}><Check size={16}/>{book?.sections[currentIndex]?.is_read?t('已标记读完'):t('标记本节已读')}</button><button className="next-section" disabled={!book||currentIndex>=book.sections.length-1} onClick={()=>void go(book!.sections[currentIndex+1].id,false)}>{autoPage?t('继续滚动 · 下一节'):t('继续下一节')} <ArrowRight size={16}/></button></div>
     </>:<div className="loading-paper">{books.length?<><LoaderCircle className="spin"/>{t('正在打开阅读资料…')}</>:<><BookOpen size={40}/><h2>{t('让一本难书，变得读得下去。')}</h2><p>{t('导入你的书籍、论文或教程，开始一段有来有回的阅读。')}</p><button className="primary" onClick={()=>file.current?.click()}>{t('导入第一份资料')}</button></>}</div>}
    </div>
    {selection&&highlighted&&<div className="selection-bar" onMouseDown={e=>e.preventDefault()}><span>{t('已选 {count} 字',{count:selection.length})}</span><button onClick={()=>void send(t('请解释我选中的这段话，先讲直觉，再举一个具体例子。'))}>{t('解释这段')} <ArrowUp size={14}/></button><button onClick={newNote}><Bookmark size={14}/>{t('记笔记')}</button>{button(t('取消选中'),<X size={14}/>,clearSelection)}</div>}
   </main>
   <aside className="companion"><div className="companion-tabs">{[['chat',t('同读'),MessageSquare],['notes',t('笔记'),FileText],['cards',t('复习卡'),Layers]].map(([k,n,Icon])=><button key={String(k)} className={tab===k?'active':''} onClick={()=>setTab(String(k))}><Icon size={15}/>{String(n)}{k==='cards'&&cardCount>0?<span className="count">{cardCount}</span>:null}</button>)}</div>
    {tab==='chat'?<><div className="companion-context"><span className="status-dot"/><span>{t('一起读到')}</span><b title={section?.title}>{section?.title||t('等待打开资料')}</b></div>
     <div className="chat-viewport"><div className="chat-scroll" ref={chatScroll} tabIndex={0} aria-label={t('对话阅读区')}
      onPointerDown={pauseReading} onTouchStart={pauseReading}
      onWheel={e=>{if(e.deltaY<0)pauseReading();}}
      onKeyDown={e=>{if(['ArrowUp','PageUp','Home'].includes(e.key)||(e.key===' '&&e.shiftKey))pauseReading();}}
      onScroll={e=>{const top=e.currentTarget.scrollTop;if(top<lastChatTop.current-2)pauseReading();lastChatTop.current=top;}}><div className="history-search"><Search size={14}/><input aria-label={t('查找本书对话')} placeholder={t('找回以前讨论过的问题')} value={historyQuery} onChange={e=>{searchVersion.current++;setHistoryQuery(e.target.value);if(!e.target.value)setHistoryResults(null);}} onKeyDown={e=>{if(e.key==='Enter')void searchHistory();}}/>{historyResults&&button(t('关闭历史搜索'),<X size={14}/>,()=>{searchVersion.current++;setHistoryResults(null);setHistoryQuery('');})}</div>
      {historyResults?<><p className="small-muted">{t('找到 {count} 条原始记录',{count:historyResults.length})}</p>{historyResults.map(m=><div className="message" key={m.id}><div className="message-label">{m.role==='user'?t('你'):t('阅间')} · {t('历史片段')}</div>{md(m.content)}<button className="text-button" onClick={()=>void go(m.section_id)}>{t('回到讨论原文')}</button></div>)}</>:<>
      {!messages.length&&!busy&&<div className="welcome"><div className="companion-symbol"><BookOpen size={25}/><span>↗</span></div><span className="eyebrow">{t('你的阅读搭档')}</span><h2>{t('难的地方，')}<br/>{t('我们一起拆开。')}</h2><p>{t('告诉我这次想读懂什么。我会查原文和旧讨论，也能带你跳转、保存笔记与复习卡。')}</p><div className="suggestions">{[[t('先讲直觉，再看细节'),t('用大白话解释这一节的核心概念，先讲直觉，再给一个具体例子。')],[t('这一章在解决什么问题？'),t('请读取这一章并总结：它在解决什么问题，关键思路是什么？')],[t('后面会学到什么？'),t('请看目录，告诉我当前章节之后会学到什么，以及和现在内容的联系。')]].map(([label,q])=><button key={label} onClick={()=>void send(q)}>{label}<ArrowUp size={15}/></button>)}</div></div>}
      {messages.map(m=><div className={'message '+m.role} key={m.id}><div className="message-label">{m.role==='user'?t('你'):t('阅间')}{m.role==='assistant'&&<span>{t('基于当前资料')}</span>}</div>{md(m.content)}{m.role==='user'&&['failed','interrupted','cancelled'].includes(m.run_status||'')&&<p className="message-failure">{m.run_error||t('这次回答已停止，可以重新提问。')}</p>}</div>)}
      {(busy||stream)&&<div className="message assistant streaming"><div className="message-label">{t('阅间')}{busy&&<LoaderCircle size={12} className="spin"/>}</div>{trace.length>0&&<details className="trace"><summary>{t(toolNames[trace.at(-1)!]||trace.at(-1)!)}{busy?'…':t(' · 过程记录')}</summary>{trace.map((t,i)=><div key={i}>{i+1}. {translate(language,toolNames[t]||t)}</div>)}</details>}{stream?md(stream):<p className="thinking">{t('正在读原文，组织解释…')}</p>}{busy&&idleSeconds>=10&&<p className="waiting-status" role="status">{idleSeconds>=25?t('回答暂时没有新内容，仍在等待模型；可以停止后重试。'):t('正在等待模型继续输出…')} <span>{t('已等 {count} 秒',{count:idleSeconds})}</span></p>}{!busy&&showIncomplete(streamStatus)&&<small className="small-muted">{t('本次回答未完成，以上为已收到的片段。')}</small>}</div>}</>}
     </div>{readingPaused&&<button className="jump-latest" onClick={followLatest}><ArrowDownToLine size={14}/>{busy?t('回答仍在生成 · 回到最新'):t('回到最新')}</button>}</div>
     <div className="composer-area">{error&&!busy&&<div className="run-feedback" role="alert"><span>{error}</span><button onClick={()=>{setDraft([...messages].reverse().find(m=>m.role==='user')?.content||draft);setError('');composer.current?.focus();}}>{t('重新填写问题')}</button></div>}<div className="quick-actions"><button onClick={()=>void send(t('请根据这一节生成 3 张复习卡片，问题要检验理解，不要只考名词。'),'section_cards')} disabled={!!busy}><Layers size={13}/>{t('出复习卡')}</button><button onClick={()=>void send(t('请读取这一章，整理章节小结并保存到笔记。'),'chapter_summary')} disabled={!!busy}><FileText size={13}/>{t('存章节小结')}</button></div>
      {selection&&<div className="selected-quote"><span>{t('引用原文')}</span>{selection.slice(0,120)}{selection.length>120?'…':''}{button(t('移除引用'),<X size={13}/>,clearSelection)}</div>}
      <div className="composer"><textarea ref={composer} aria-label={t('向阅读伙伴提问')} placeholder={t('提问，或让我找原文、跳章节、记笔记…')} value={draft} onChange={e=>setDraft(e.target.value)} rows={3} onKeyDown={e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();void send();}}}/><div className="composer-footer"><span>{busy?t('可以停止，已保存的内容会保留'):t('⌘ Enter 发送')}</span>{busy?<button className="send stop" aria-label={t('停止回答')} disabled={busy==='pending'} onClick={()=>void api('/runs/'+busy+'/cancel',{}).catch(showError)}><Square size={14}/></button>:<button className="send" aria-label={t('发送问题')} disabled={!draft.trim()||!section} onClick={()=>void send()}><ArrowUp size={19}/></button>}</div></div>
      <div className="model-line"><span className={'status-dot '+(!configured?'offline':'')}/>{configured?t('DeepSeek 官方 · Flash'):t('DeepSeek 尚未配置')}<span>{t('回答请对照原文')}</span></div>
     </div></>:tab==='notes'?<div className="artifact-pane"><div className="pane-actions"><button className="quiet" onClick={newNote}><Plus size={15}/>{t('写笔记')}</button><a className="quiet" href={book?`/api/books/${book.id}/export/notes?language=${language}`:'#'} download><ArrowDownToLine size={15}/>{t('导出')}</a></div>{!artifacts.filter(x=>x.kind!=='cards').length&&<div className="empty-artifact"><Bookmark size={30}/><h3>{t('读过的，留下来。')}</h3><p>{t('选中文字记下想法，或让阅间保存章节小结。原始对话始终保留。')}</p></div>}{artifacts.filter(a=>a.kind!=='cards').map(a=><div className="note" key={a.id}><span className="eyebrow">{t(labels[a.kind]||a.kind)}</span><h3>{a.title}</h3>{md(a.content)}<div className="note-actions"><button onClick={()=>void go(a.section_id)}>{t('查看原文')}</button><button onClick={()=>{clearSelection();setEditing(a);setEditTitle(a.title);setEditText(a.content);}}>{t('编辑')}</button></div></div>)}<button className="archive-button" onClick={()=>void send(t('请结合我们已有的讨论、原文以及已读记录，整理并保存一份学习回顾：学到了什么，哪些问题尚未解决，下一步该复习什么。不要声称我已经掌握未验证的知识。'))}>{t('整理这本书的学习回顾')} <ArrowRight size={15}/></button></div>:<div className="artifact-pane"><div className="pane-actions"><span className="small-muted">{t('{count} 张理解型卡片',{count:cardCount})}</span><a className="quiet" href={book?`/api/books/${book.id}/export/anki?language=${language}`:'#'} download><ArrowDownToLine size={15}/>Anki TSV</a></div>{!cardCount&&<div className="empty-artifact"><Layers size={30}/><h3>{t('把理解变成长期记忆。')}</h3><p>{t('每张卡片只问一个问题。先尝试回答，再翻看解释。')}</p><button className="primary" disabled={!!busy} onClick={()=>void send(t('请为当前这一节生成 3 张检验理解的复习卡片。'),'section_cards')}>{t('生成本节复习卡')}</button></div>}{cards.flatMap(a=>(JSON.parse(a.content) as Card[]).map((c,i)=><div className="flashcard" key={c.id}><div className="flashcard-head"><span>RECALL / {String(i+1).padStart(2,'0')}</span><button onClick={()=>void go(c.section_id)}>{t('原文 ↗')}</button></div><textarea className="card-question" aria-label={t('编辑卡片问题')} key={c.id+'f'+c.front} defaultValue={c.front} onBlur={e=>{if(e.target.value!==c.front)void editCard(a,c,'front',e.target.value).catch(showError);}}/>{revealed.has(c.id)?<textarea className="card-answer" aria-label={t('编辑卡片答案')} key={c.id+'b'+c.back} defaultValue={c.back} onBlur={e=>{if(e.target.value!==c.back)void editCard(a,c,'back',e.target.value).catch(showError);}}/>:<button className="reveal" onClick={()=>setRevealed(v=>new Set([...v,c.id]))}>{t('想好了，查看答案')} <ChevronDown size={14}/></button>}</div>))}{cardCount>0&&<p className="export-help">{t('问题与答案可直接编辑，失去焦点时保存。导入 Anki 时使用自建笔记类型，字段依次为 ID、问题、答案、来源、标签；以 ID 为第一字段去重。')}</p>}</div>}
   </aside>
  </div>
  {(importError||error||notice)&&<div className={'toast '+(importError||error?'error':'')} role={importError||error?'alert':'status'}><span>{importError||error||notice}</span><button aria-label={t('关闭提示')} onClick={()=>{setImportError('');setError('');setNotice('');}}><X size={16}/></button></div>}
  {library&&<div className="modal-shade" onClick={()=>book&&setLibrary(false)}><section className="library-modal" role="dialog" aria-modal="true" aria-label={t('我的书架')} onClick={e=>e.stopPropagation()}><div className="library-header"><div><span className="eyebrow">YOUR READING ROOM</span><h1>{t('每一次理解，都从这里开始。')}</h1><p>{t('带着问题读，带着自己的解释离开。')}</p></div>{book&&button(t('关闭书架'),<X size={22}/>,()=>setLibrary(false))}</div><div className="book-grid">{books.map(b=><button className="book-tile" key={b.id} onClick={()=>void openBook(b.id,b.last_section)}><div className={'book-cover '+b.color}><div className="cover-rule"/><span className="cover-category">{b.format==='pdf'?'PAPER & BOOK':'LEARNING NOTES'}</span><h2>{b.title}</h2><span className="cover-author">{b.subtitle}</span><BookOpen size={28}/><span className="cover-edition">{t('个人学习藏书')} / {String(b.chapter_count).padStart(2,'0')} CHAPTERS</span></div><div className="book-caption"><b>{b.title}</b><span>{b.read_count?t('已读 {count} / {total} 节',{count:b.read_count,total:b.section_count}):b.last_section?t('继续阅读'):t('等待第一次翻开')}<ArrowRight size={15}/></span></div></button>)}<button className="import-tile" onClick={()=>file.current?.click()} disabled={uploading}><Plus size={30}/><b>{uploading?t('正在整理资料…'):t('添加自己的资料')}</b><span>PDF · EPUB · MOBI · AZW3 · Markdown · TXT</span><small>{t('单份不超过 20 MB')}<br/>{t('PDF 最多 {count} 页',{count:600})}</small></button></div><div className="library-foot"><span className="status-dot"/>{t('资料与学习记录保存在本机，提问时将相关原文发送到 DeepSeek 官方接口。')}</div></section></div>}
  {editing&&<div className="modal-shade"><section className="edit-modal" role="dialog" aria-modal="true" aria-label={t('编辑笔记')}><div className="pane-actions"><h2>{editing.id?t('编辑笔记'):t('记下此刻的理解')}</h2>{button(t('关闭编辑'),<X size={20}/>,closeEditor,saving)}</div><input aria-label={t('笔记标题')} value={editTitle} onChange={e=>setEditTitle(e.target.value)} placeholder={t('笔记标题')}/><textarea aria-label={t('笔记内容')} value={editText} onChange={e=>setEditText(e.target.value)} placeholder={t('用自己的话，说说你理解了什么…')}/><div className="edit-footer"><span>{t('支持 Markdown，保留原文位置')}</span><button className="primary" onClick={()=>void saveEdit()} disabled={saving||!editText.trim()||!editTitle.trim()}>{saving?t('保存中…'):t('保存笔记')}</button></div></section></div>}
 </div>;
}
