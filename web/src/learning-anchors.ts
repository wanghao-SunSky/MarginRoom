export type Anchor={artifact_id:string,section_id:string,quote:string,prefix:string,suffix:string,start:number,version:string};
export function textVersion(text:string){let hash=2166136261;for(let i=0;i<text.length;i++)hash=Math.imul(hash^text.charCodeAt(i),16777619);return `${text.length}:${hash>>>0}`;}
export function locateAnchor(text:string,a:Anchor):number|null{
 if(textVersion(text)!==a.version)return null;
 const matches=(i:number)=>text.slice(i,i+a.quote.length)===a.quote&&text.slice(Math.max(0,i-a.prefix.length),i)===a.prefix&&text.slice(i+a.quote.length,i+a.quote.length+a.suffix.length)===a.suffix;
 return matches(a.start)?a.start:null;
}
export function captureAnchor(root:HTMLElement|null,selection:Selection|null):Omit<Anchor,'artifact_id'>|null{
 if(!root||!selection||selection.isCollapsed||!selection.rangeCount)return null;
 const range=selection.getRangeAt(0),node=range.startContainer instanceof Element?range.startContainer:range.startContainer.parentElement;
 const body=node?.closest<HTMLElement>('.book-text,.textLayer'),section=body?.closest<HTMLElement>('[data-section-id]');
 if(!body||!section||!root.contains(body)||!body.contains(range.endContainer))return null;
 const pre=range.cloneRange();pre.selectNodeContents(body);pre.setEnd(range.startContainer,range.startOffset);
 const text=body.textContent||'',start=pre.toString().length,quote=range.toString();
 if(!quote.trim()||quote.length>5000)return null;
 return {section_id:section.dataset.sectionId!,quote,prefix:text.slice(Math.max(0,start-48),start),suffix:text.slice(start+quote.length,start+quote.length+48),start,version:textVersion(text)};
}
export function anchorRange(body:HTMLElement,a:Anchor):Range|null{
 const start=locateAnchor(body.textContent||'',a);if(start===null)return null;
 const walker=document.createTreeWalker(body,NodeFilter.SHOW_TEXT);let offset=0,node:Node|null,first:Node|null=null,last:Node|null=null,from=0,to=0;
 while((node=walker.nextNode())){const end=offset+(node.textContent?.length||0);if(!first&&start<end){first=node;from=start-offset;}if(first&&start+a.quote.length<=end){last=node;to=start+a.quote.length-offset;break;}offset=end;}
 if(!first||!last)return null;const r=document.createRange();r.setStart(first,from);r.setEnd(last,to);return r;
}
const stop=new Set('this that with from have what when where which their there about could would should chapter section explain please reading book text does into your then than they them some also only using user note true false return const function string these those 如何 什么 为什么 这个 那个 一个 我们 可以 原文 解释 章节 笔记 内容 阅读 这里 以及 已经 这样'.split(' '));
export function distinctiveTerms(text:string){const words=text.toLowerCase().match(/[a-z][a-z0-9_]{3,}|[\u4e00-\u9fff]{2,}/g)||[];return [...new Set(words.flatMap(w=>/^[\u4e00-\u9fff]+$/.test(w)?Array.from({length:w.length-1},(_,i)=>w.slice(i,i+2)):[w]).filter(w=>!stop.has(w)))];}
export function relatedHistory<T extends {id:string,content:string,section_id:string}>(section:{id:string,content:string},rows:T[]){
 const terms=new Set(distinctiveTerms(section.content));return rows.map(row=>({row,score:distinctiveTerms(row.content).filter(t=>terms.has(t)).length})).filter(x=>x.row.section_id===section.id&&x.score>=2).sort((a,b)=>b.score-a.score).slice(0,2).map(x=>x.row);
}
