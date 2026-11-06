import {createContext,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {getDocument,GlobalWorkerOptions,TextLayer,type PDFDocumentProxy,type RenderTask} from 'pdfjs-dist';
import workerURL from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'pdfjs-dist/web/pdf_viewer.css';
import {translate,type Language} from './i18n';
GlobalWorkerOptions.workerSrc=workerURL;
const DocumentContext=createContext<{doc:PDFDocumentProxy|null,error:string}>({doc:null,error:''});

// One loading task/worker per open book, shared by visible and prefetched pages.
export function PdfDocument({book,children}:{book:string,children:ReactNode}){
 const [value,setValue]=useState<{doc:PDFDocumentProxy|null,error:string}>({doc:null,error:''});
 useEffect(()=>{let disposed=false;setValue({doc:null,error:''});const task=getDocument({url:`/api/books/${book}/file`});
  void task.promise.then(doc=>{if(!disposed)setValue({doc,error:''});}).catch(e=>{if(!disposed)setValue({doc:null,error:String(e.message)});});
  return()=>{disposed=true;void task.destroy();};
 },[book]);
 return <DocumentContext.Provider value={value}>{children}</DocumentContext.Provider>;
}
export default function PdfPage({page,language,onSize,initialRatio=Math.SQRT2}:{page:number,language:Language,onSize?:(ratio:number)=>void,initialRatio?:number}){
 const {doc,error:documentError}=useContext(DocumentContext);
 const host=useRef<HTMLDivElement>(null),canvas=useRef<HTMLCanvasElement>(null),text=useRef<HTMLDivElement>(null);
 const sizeCallback=useRef(onSize);sizeCallback.current=onSize;
 const [error,setError]=useState(''),[width,setWidth]=useState(0),[ready,setReady]=useState(false),[retry,setRetry]=useState(0);
 const [ratio,setRatio]=useState(initialRatio);
 useEffect(()=>{const el=host.current;if(!el)return;const observer=new ResizeObserver(entries=>setWidth(Math.round(entries[0].contentRect.width)));observer.observe(el);return()=>observer.disconnect();},[]);
 useEffect(()=>{
  if(!doc||!width)return;
  let disposed=false,render:RenderTask|undefined,layer:TextLayer|undefined;
  setError('');setReady(false);
  void (async()=>{const p=await doc.getPage(page);if(disposed)return;
   const base=p.getViewport({scale:1});const aspect=base.height/base.width;setRatio(aspect);sizeCallback.current?.(aspect);
   const viewport=p.getViewport({scale:width/base.width});const c=canvas.current!;const t=text.current!;
   const density=Math.min(window.devicePixelRatio||1,2);
   c.width=Math.round(viewport.width*density);c.height=Math.round(viewport.height*density);
   c.style.width=`${viewport.width}px`;c.style.height=`${viewport.height}px`;
   t.replaceChildren();t.style.setProperty('--scale-factor',String(viewport.scale));
   render=p.render({canvas:c,viewport,transform:[density,0,0,density,0,0]});await render.promise;if(disposed)return;
   const content=await p.getTextContent();if(disposed)return;
   layer=new TextLayer({textContentSource:content,container:t,viewport});await layer.render();if(!disposed)setReady(true);
  })().catch(e=>{if(!disposed)setError(String(e.message));});
  return()=>{disposed=true;render?.cancel();layer?.cancel();};
 },[doc,page,width,retry]);
 const failure=documentError||error;
 return <div ref={host} className="pdf-host" style={{aspectRatio:`1 / ${ratio}`}} aria-busy={!ready&&!failure}>
  {failure?<div className="reader-load-error" role="alert"><p>{translate(language,'原版页面暂时无法显示：')}{failure}</p><button onClick={()=>documentError?location.reload():setRetry(x=>x+1)}>{language==='zh'?'重新加载':'Retry'}</button></div>:<>
   {!ready&&<div className="pdf-loading" role="status">{language==='zh'?`正在准备第 ${page} 页…`:`Preparing page ${page}…`}</div>}
   <div className="pdf-page" style={{visibility:ready?'visible':'hidden'}}><canvas ref={canvas}/><div ref={text} className="textLayer"/></div>
  </>}
 </div>;
}
