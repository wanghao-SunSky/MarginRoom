import {useState} from 'react';
import {ChevronDown,ChevronRight} from 'lucide-react';

export type PdfBookmark={title:string,page?:number,depth:number,parent:number|null,section_id:string};

export default function PdfOutline({items,current,query,onNavigate,english}:{items:PdfBookmark[],current?:string,query:string,onNavigate:(id:string)=>void,english:boolean}){
 const [expanded,setExpanded]=useState(()=>new Set(items.map((x,i)=>x.depth===0?i:-1)));
 const children=new Map<number|null,number[]>();
 items.forEach((x,i)=>children.set(x.parent,[...(children.get(x.parent)||[]),i]));
 const matches=new Set<number>();
 if(query)items.forEach((x,i)=>{if(x.title.toLowerCase().includes(query.toLowerCase())){let parent:number|null=i;while(parent!==null){matches.add(parent);parent=items[parent].parent;}}});
 function render(parent:number|null):React.ReactNode{return (children.get(parent)||[]).filter(i=>!query||matches.has(i)).map(i=>{
  const item=items[i],branch=children.has(i),open=expanded.has(i)||!!query;
  return <div key={i} className="pdf-toc-node"><div className={'pdf-toc-row '+(item.section_id===current?'selected':'')}>
   {branch?<button className="pdf-toc-toggle" aria-label={(open?(english?'Collapse ':'收起 '):(english?'Expand ':'展开 '))+item.title} aria-expanded={open} onClick={()=>setExpanded(old=>{const next=new Set(old);next.has(i)?next.delete(i):next.add(i);return next;})}>{open?<ChevronDown size={12}/>:<ChevronRight size={12}/>}</button>:<span className="pdf-toc-spacer"/>}
   <button className="pdf-toc-link" onClick={()=>onNavigate(item.section_id)} title={item.title}><span>{item.title}</span><small>{item.page}</small></button>
  </div>{branch&&open&&<div className="pdf-toc-children">{render(i)}</div>}</div>;
 });}
 return <nav aria-label={english?'Book contents':'书籍目录'} className="pdf-toc">{render(null)}</nav>;
}
