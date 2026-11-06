import {useEffect,useLayoutEffect,useMemo,useRef,useState,type ReactNode,type RefObject} from 'react';
import PdfPage from './PdfPage';
import type {Language} from './i18n';
import {ReadingExposure} from './reading-exposure';

export type ReadingSection={id:string,book_id:string,title:string,chapter:string,ordinal:number,content:string,page:number|null,is_read:number,chars?:number,auto_read_blocked?:number};
type Props={sections:ReadingSection[],current:ReadingSection,target:{id:string,version:number},root:RefObject<HTMLDivElement|null>,format:string,pdf:boolean,language:Language,continuous:boolean,autoRead:boolean,readingActive:boolean,onAutoRead:(id:string)=>Promise<void>,onCurrent:(section:ReadingSection)=>void,load:(id:string)=>Promise<ReadingSection>,renderText:(section:ReadingSection)=>ReactNode,renderLearning?:(section:ReadingSection)=>ReactNode,onRead:(id:string)=>void};

export default function ContinuousReader(props:Props){
 const latest=useRef(props);latest.current=props;
 const content=useRef(new Map<string,ReadingSection>()),pending=useRef(new Map<string,Promise<ReadingSection>>());
 content.current.set(props.current.id,props.current);
 const refs=useRef(new Map<string,HTMLElement>()),tracking=useRef(false);
 const load=async(id:string)=>{
  const cached=content.current.get(id);if(cached)return cached;
  let task=pending.current.get(id);
  if(!task){task=latest.current.load(id).then(value=>{content.current.set(id,value);return value;}).finally(()=>pending.current.delete(id));pending.current.set(id,task);}
  return task;
 };
 useLayoutEffect(()=>{
  tracking.current=false;
  const root=props.root.current,el=refs.current.get(props.target.id);if(!root||!el)return;
  root.scrollTo({top:el.getBoundingClientRect().top-root.getBoundingClientRect().top+root.scrollTop-24,behavior:'instant'});
 },[props.target.version,props.continuous,props.pdf]);
 useEffect(()=>{
  const root=props.root.current;if(!root)return;let frame=0,generation=0;
  const update=()=>{
   frame=0;const p=latest.current;if(!p.continuous||!tracking.current)return;
   const line=root.getBoundingClientRect().top+Math.min(160,root.clientHeight*.25);
   let id=p.sections[0]?.id;
   for(const s of p.sections){const el=refs.current.get(s.id);if(!el)continue;if(el.getBoundingClientRect().top>line)break;id=s.id;}
   const version=++generation;if(!id||id===p.current.id)return;
   void load(id).then(value=>{if(generation===version&&tracking.current&&latest.current.target.version===p.target.version)latest.current.onCurrent(value);}).catch(()=>{/* Per-section retry is visible in the reader. */});
  };
  const scroll=()=>{if(tracking.current&&!frame)frame=requestAnimationFrame(update);};
  const interact=()=>{tracking.current=true;};
  const events=['wheel','touchmove','pointerdown','keydown'];
  const size=new ResizeObserver(()=>root.style.setProperty('--reader-height',`${root.clientHeight}px`));size.observe(root);
  root.style.setProperty('--reader-height',`${root.clientHeight}px`);
  root.addEventListener('scroll',scroll,{passive:true});events.forEach(name=>root.addEventListener(name,interact,{passive:true}));
  return()=>{generation++;cancelAnimationFrame(frame);size.disconnect();root.removeEventListener('scroll',scroll);events.forEach(name=>root.removeEventListener(name,interact));};
 },[props.root]);
 // Only rendered, foreground reading content contributes. The six nearby PDF
 // canvases may be prefetched, but offscreen pages never count as read.
 useEffect(()=>{
  const exposures=new Map<string,ReadingExposure>(),inFlight=new Set<string>(),retryAfter=new Map<string,number>();
  const timer=setInterval(()=>{
   const p=latest.current,root=p.root.current,now=performance.now();
   const active=p.autoRead&&p.readingActive&&document.visibilityState==='visible'&&document.hasFocus()&&!!root?.clientHeight;
   const seen=new Set<string>();
   if(root&&active){const viewport=root.getBoundingClientRect();
    for(const body of root.querySelectorAll<HTMLElement>('.section-body[data-ready="true"]')){
     const id=body.closest<HTMLElement>('[data-section-id]')!.dataset.sectionId!;
     const s=p.sections.find(x=>x.id===id);if(!s||s.is_read||s.auto_read_blocked||body.querySelector('[aria-busy="true"], [role="alert"]'))continue;
     const rect=body.getBoundingClientRect();if(rect.height<=0||rect.bottom<=viewport.top||rect.top>=viewport.bottom)continue;
     const from=Math.max(0,(viewport.top-rect.top)/rect.height),to=Math.min(1,(viewport.bottom-rect.top)/rect.height);
     let exposure=exposures.get(id);if(!exposure){exposure=new ReadingExposure(s.chars??content.current.get(id)?.content.length??0);exposures.set(id,exposure);}
     seen.add(id);const complete=exposure.observe(now,from,to,true);
     if(complete&&!inFlight.has(id)&&now>=(retryAfter.get(id)||0)){
      inFlight.add(id);void p.onAutoRead(id).catch(()=>retryAfter.set(id,performance.now()+30000)).finally(()=>inFlight.delete(id));
     }
    }
   }
   for(const [id,exposure] of exposures)if(!seen.has(id))exposure.observe(now,0,0,false);
  },500);
  return()=>clearInterval(timer);
 },[]);
 const shown=props.continuous?props.sections:props.sections.filter(s=>s.id===props.current.id);
 return <div className={'reading-sections '+(props.continuous?'continuous':'paged')}>
  {shown.map((s,index)=><SectionBlock key={s.id} section={s} number={props.continuous?index+1:props.sections.findIndex(x=>x.id===s.id)+1} root={props.root} continuous={props.continuous} register={el=>{if(el)refs.current.set(s.id,el);else refs.current.delete(s.id);}} load={load} initial={content.current.get(s.id)} pdf={props.format==='pdf'&&props.pdf} language={props.language} renderText={props.renderText} renderLearning={props.renderLearning} onRead={()=>props.onRead(s.id)}/>) }
 </div>;
}
function SectionBlock({section,number,root,continuous,register,load,initial,pdf,language,renderText,renderLearning,onRead}:{section:ReadingSection,number:number,root:RefObject<HTMLDivElement|null>,continuous:boolean,register:(el:HTMLElement|null)=>void,load:(id:string)=>Promise<ReadingSection>,initial?:ReadingSection,pdf:boolean,language:Language,renderText:(s:ReadingSection)=>ReactNode,renderLearning?:(s:ReadingSection)=>ReactNode,onRead:()=>void}){
 const el=useRef<HTMLElement>(null),body=useRef<HTMLDivElement>(null),loadRef=useRef(load);loadRef.current=load;
 const [near,setNear]=useState(false),[value,setValue]=useState(initial),[error,setError]=useState(''),[retry,setRetry]=useState(0),[ratio,setRatio]=useState(Math.SQRT2);
 const [reserved,setReserved]=useState(0);
 const renderer=useRef(renderText);renderer.current=renderText;
 const rendered=useMemo(()=>value?renderer.current(value):null,[value,language]);
 useEffect(()=>{if(!el.current)return;const observer=new IntersectionObserver(entries=>setNear(entries[entries.length-1].isIntersecting),{root:root.current,rootMargin:'1400px 0px'});observer.observe(el.current);return()=>observer.disconnect();},[root,continuous]);
 useEffect(()=>{if(!near||pdf||value)return;let disposed=false;setError('');void loadRef.current(section.id).then(s=>{if(!disposed)setValue(s);}).catch(e=>{if(!disposed)setError(e.message);});return()=>{disposed=true;};},[near,pdf,value,section.id,retry]);
 // Keep measured space when distant content/canvases are released. Never collapse
 // preceding pages and move the paragraph that the reader is looking at.
 useLayoutEffect(()=>{if(!body.current||!near)return;const observer=new ResizeObserver(entries=>{const h=entries[0].borderBoxSize?.[0]?.blockSize||entries[0].contentRect.height;if(h>0){setReserved(h);}});observer.observe(body.current);return()=>observer.disconnect();},[near,pdf,value]);
 const estimate=Math.max(320,Math.ceil((section.chars||1500)/45)*30);
 return <section ref={node=>{el.current=node;register(node);}} className="reading-section" data-section-id={section.id} aria-label={section.page?`${language==='zh'?'第':'Page'} ${section.page}${language==='zh'?' 页':''}`:section.title}>
  <div className="reading-meta"><span className="eyebrow">{section.page?`PAGE ${section.page}`:`SECTION ${String(number).padStart(2,'0')}`}</span><span>{section.title}</span></div>
  <div ref={body} data-ready={near&&(pdf||!!value)?"true":"false"} className={'section-body '+(pdf?'original-page':'text-page')} style={!near?{height:pdf?undefined:(reserved||estimate),aspectRatio:pdf?`1 / ${ratio}`:undefined}:undefined}>
   {near?(pdf?<PdfPage page={section.page||1} language={language} initialRatio={ratio} onSize={setRatio}/>:value?<article className="paper">{rendered}</article>:<div className="section-placeholder" style={{minHeight:reserved||estimate}} role={error?'alert':'status'}>{error?<><p>{error}</p><button onClick={()=>setRetry(x=>x+1)}>{language==='zh'?'重新加载':'Retry'}</button></>:language==='zh'?'正在加载内容…':'Loading content…'}</div>):null}
  </div>
  {near&&renderLearning?.(value||section)}
  <div className="section-footer"><button className={'quiet '+(section.is_read?'is-read':'')} aria-label={section.is_read?(language==='zh'?'标为未读':'Mark as unread'):(language==='zh'?'标记已读':'Mark as read')} title={section.is_read?(language==='zh'?'改回未读，暂停本节自动记录':'Mark unread and pause automatic marking for this section'):(language==='zh'?'也可以手动标记已读':'You can also mark this section read manually')} onClick={onRead}>{section.is_read?(language==='zh'?'✓ 已读':'✓ Read'):section.auto_read_blocked?(language==='zh'?'保留未读':'Kept unread'):(language==='zh'?'未读':'Unread')}</button></div>
 </section>;
}
