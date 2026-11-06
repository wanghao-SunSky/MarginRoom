import {useEffect,useRef} from 'react';
import {SlidersHorizontal,AlignJustify,FileText} from 'lucide-react';
import type {Language} from './i18n';

type Props={language:Language,continuous:boolean,onMode:(mode:string)=>void,autoRead:boolean,onAutoRead:()=>void,open:boolean,onOpen:(open:boolean)=>void};
export default function ReadingSettings({language,continuous,onMode,autoRead,onAutoRead,open,onOpen}:Props){
 const root=useRef<HTMLDivElement>(null),trigger=useRef<HTMLButtonElement>(null);
 const zh=language==='zh';
 useEffect(()=>{
  if(!open)return;
  const outside=(event:PointerEvent)=>{if(!root.current?.contains(event.target as Node))onOpen(false);};
  const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'){onOpen(false);trigger.current?.focus();}};
  document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);
  return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);};
 },[open,onOpen]);
 return <div className="reading-settings" ref={root} onBlur={event=>{if(event.relatedTarget&&!event.currentTarget.contains(event.relatedTarget as Node))onOpen(false);}}>
  <button ref={trigger} className={'icon-button '+(open?'is-open':'')} aria-label={zh?'阅读设置':'Reading settings'} title={zh?'阅读设置':'Reading settings'} aria-expanded={open} aria-controls="reading-settings-panel" onClick={()=>onOpen(!open)}><SlidersHorizontal size={17}/></button>
  {open&&<div className="reading-settings-panel" id="reading-settings-panel" role="dialog" aria-label={zh?'阅读设置':'Reading settings'}>
   <div className="settings-label">{zh?'阅读方式':'Reading layout'}</div>
   <div className="reading-layout-choice" role="group" aria-label={zh?'阅读方式':'Reading layout'}>
    <button aria-pressed={continuous} onClick={()=>onMode('continuous')}><AlignJustify size={15}/>{zh?'连续阅读':'Continuous'}</button>
    <button aria-pressed={!continuous} onClick={()=>onMode('paged')}><FileText size={15}/>{zh?'分页阅读':'Paginated'}</button>
   </div>
   <div className="reading-settings-rule"/>
   <div className="reading-setting-row"><span>{zh?'自动记录已读':'Mark read automatically'}</span><button className="reading-switch" role="switch" aria-checked={autoRead} aria-label={zh?'自动记录已读':'Mark read automatically'} onClick={onAutoRead}><span/></button></div>
   <p>{zh?'读过的内容自动记录，也可以手动撤销。':'Progress saves as you read. You can undo it anytime.'}</p>
  </div>}
 </div>;
}
