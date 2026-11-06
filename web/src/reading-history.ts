/** Browser-style reading history, scoped to one book and one tab session. */
export type ReadingPoint={section:string,offset:number};
export type ReadingHistory={version:1,book:string,entries:ReadingPoint[],index:number};
export const HISTORY_LIMIT=80;
export function point(section:string,offset=0):ReadingPoint{return {section,offset:Number.isFinite(offset)?Math.max(-10000,Math.min(1e7,Math.round(offset))):0};}
export function samePoint(a:ReadingPoint|undefined,b:ReadingPoint|undefined){return !!a&&!!b&&a.section===b.section&&Math.abs(a.offset-b.offset)<=1;}
export function currentPoint(h:ReadingHistory){return h.entries[h.index];}
export function replacePoint(h:ReadingHistory,p:ReadingPoint):ReadingHistory{
 const clean=point(p.section,p.offset);if(!h.entries.length)return {...h,entries:[clean],index:0};
 if(samePoint(currentPoint(h),clean))return h;
 return {...h,entries:h.entries.map((old,i)=>i===h.index?clean:old)};
}
export function visitPoint(h:ReadingHistory,p:ReadingPoint):ReadingHistory{
 if(samePoint(currentPoint(h),p))return h;
 const entries=[...h.entries.slice(0,h.index+1),point(p.section,p.offset)].slice(-HISTORY_LIMIT);
 return {...h,entries,index:entries.length-1};
}
export function stepHistory(h:ReadingHistory,direction:-1|1):ReadingHistory|null{
 const index=h.index+direction;return index>=0&&index<h.entries.length?{...h,index}:null;
}
export function restoreHistory(raw:string|null,book:string,valid:ReadonlySet<string>,fallback:ReadingPoint,legacy:string|null=null):ReadingHistory{
 let entries:ReadingPoint[]=[],index=-1;
 try{const data=JSON.parse(raw||'null');if(data?.version===1&&data.book===book&&Array.isArray(data.entries)&&Number.isInteger(data.index)){
  for(let i=0;i<data.entries.length;i++){const p=data.entries[i];if(p&&typeof p.section==='string'&&valid.has(p.section)&&typeof p.offset==='number'&&Number.isFinite(p.offset)){entries.push(point(p.section,p.offset));if(i<=data.index)index=entries.length-1;}}
 }}catch{/* Corrupt tab storage must not prevent opening a book. */}
 if(!entries.length&&legacy){try{const ids=JSON.parse(legacy);if(Array.isArray(ids)){entries=ids.filter((id):id is string=>typeof id==='string'&&valid.has(id)).map(id=>point(id));if(!samePoint(entries.at(-1),fallback))entries.push(fallback);index=entries.length-1;}}catch{/* Old section-only history is optional. */}}
 if(!entries.length){entries=[point(fallback.section,fallback.offset)];index=0;}
 index=Math.max(0,Math.min(index,entries.length-1));const start=Math.max(0,entries.length-HISTORY_LIMIT);
 return {version:1,book,entries:entries.slice(start),index:Math.max(0,index-start)};
}
export function positionFromRects(top:number,height:number,sections:{id:string,top:number}[]):ReadingPoint|null{
 if(!sections.length)return null;const line=top+Math.min(160,height*.25);let section=sections[0];
 for(const item of sections){if(item.top>line)break;section=item;}
 return point(section.id,top+24-section.top);
}
export function captureReadingPoint(root:HTMLElement|null):ReadingPoint|null{
 if(!root)return null;const viewport=root.getBoundingClientRect();return positionFromRects(viewport.top,root.clientHeight,Array.from(root.querySelectorAll<HTMLElement>('.reading-section[data-section-id]')).map(el=>({id:el.dataset.sectionId!,top:el.getBoundingClientRect().top})));
}
