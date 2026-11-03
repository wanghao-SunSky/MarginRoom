import { useEffect, useRef, useState } from 'react';
import { getDocument, GlobalWorkerOptions, TextLayer } from 'pdfjs-dist';
import workerURL from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'pdfjs-dist/web/pdf_viewer.css';
import {translate,type Language} from './i18n';
GlobalWorkerOptions.workerSrc = workerURL;
export default function PdfPage({book, page,language}: {book:string,page:number,language:Language}) {
 const host=useRef<HTMLDivElement>(null),canvas=useRef<HTMLCanvasElement>(null),text=useRef<HTMLDivElement>(null);
 const [error,setError]=useState(''),[width,setWidth]=useState(0);
 useEffect(()=>{let timer:ReturnType<typeof setTimeout>;const observer=new ResizeObserver(entries=>{clearTimeout(timer);timer=setTimeout(()=>setWidth(Math.round(entries[0].contentRect.width)),100);});observer.observe(host.current!);return()=>{clearTimeout(timer);observer.disconnect();};},[]);
 useEffect(()=>{
  if(!width)return;
  let disposed=false; const task=getDocument({url:`/api/books/${book}/file`});
  setError('');
  (async()=>{const doc=await task.promise;const p=await doc.getPage(page); if(disposed)return;
   const base=p.getViewport({scale:1});const scale=Math.min(1.6,(width-4)/base.width);
   const viewport=p.getViewport({scale});const c=canvas.current!;const t=text.current!;
   c.width=viewport.width*devicePixelRatio;c.height=viewport.height*devicePixelRatio;
   c.style.width=`${viewport.width}px`;c.style.height=`${viewport.height}px`;
   t.replaceChildren();t.style.setProperty('--scale-factor',String(scale));
   await p.render({canvas:c,viewport,transform:[devicePixelRatio,0,0,devicePixelRatio,0,0]}).promise;
   if(disposed)return;
   const layer=new TextLayer({textContentSource:await p.getTextContent(),container:t,viewport});await layer.render();
  })().catch(e=>{if(!disposed)setError(String(e.message));});
  return ()=>{disposed=true;void task.destroy();};
 },[book,page,width]);
 return <div ref={host} className="pdf-host">{error&&<p role="alert">{translate(language,'原版页面暂时无法显示：')}{error}</p>}<div className="pdf-page" hidden={!!error}><canvas ref={canvas}/><div ref={text} className="textLayer"/></div></div>;
}
