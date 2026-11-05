import {BookOpen,ArrowUpRight,FileText,Layers} from 'lucide-react';
import {useEffect,useRef,useState} from 'react';
import {getLanguage,type Language} from './i18n';
import copy from './home-demo-copy.json';
import './home.css';

export default function Home({onStartReading,onOpenOnline}:{onStartReading:()=>void,onOpenOnline:()=>void}){
 const [language,setLanguage]=useState<Language>(getLanguage);
 const [step,setStep]=useState(0),[playing,setPlaying]=useState(false);
 const [source,setSource]=useState<number|null>(null),[tab,setTab]=useState<'note'|'cards'>('note');
 const [opened,setOpened]=useState<number[]>([]);
 const demo=useRef<HTMLElement>(null);
 const t=(zh:string,en:string)=>language==='zh'?zh:en;
 const words=(pair:string[])=>pair[language==='zh'?0:1];
 const away=source===1||(source===null&&step===2);
 useEffect(()=>{const update=()=>setLanguage(getLanguage());window.addEventListener('reading-language',update);return()=>window.removeEventListener('reading-language',update);},[]);
 useEffect(()=>{document.documentElement.lang=language==='zh'?'zh-CN':'en';document.title=t('阅间 · AI 阅读与学习伙伴','MarginRoom · Your AI reading & learning partner');},[language]);
 useEffect(()=>{
  if(!playing)return;
  const timer=window.setTimeout(()=>{setSource(null);setStep(s=>Math.min(s+1,4));if(step>=3)setPlaying(false);},5500);
  return()=>window.clearTimeout(timer);
 },[playing,step]);
 useEffect(()=>{const pause=()=>{if(document.hidden)setPlaying(false);};document.addEventListener('visibilitychange',pause);return()=>document.removeEventListener('visibilitychange',pause);},[]);
 function changeLanguage(next:Language){localStorage.setItem('reading-language',next);setLanguage(next);window.dispatchEvent(new Event('reading-language'));}
 function play(){if(playing){setPlaying(false);return;}setSource(null);if(step===0||step===4){setStep(1);setOpened([]);setTab('note');}setPlaying(true);}
 function selectStep(next:number){setPlaying(false);setSource(null);setStep(next);}
 function returnToReading(){setSource(3);if(step===2)selectStep(3);}
 function downloadCards(){
  const rows=['#separator:Tab','#html:false',...copy.cards.map(c=>[words(c.q),words(c.a)].join('\t'))].join('\n');
  const url=URL.createObjectURL(new Blob([rows],{type:'text/tab-separated-values;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download='marginroom-demo-anki.tsv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 const labels=[t('查前文','Find context'),t('跳过去','Visit source'),t('回原位','Return'),t('记下来','Keep it')];
 const statuses=[t('从你读到的地方开始','Starting where you are'),t('找到第一章的相关解释','Found the explanation in chapter 1'),t('现在读的是第一章','Now showing chapter 1'),t('已回到原阅读位置','Back where you left off'),t('一条笔记，两张复习卡','One note, two review cards')];
 return <div className={`home-page${language==='en'?' en':''}`}>
  <header><a className="home-brand" href="/"><BookOpen size={27}/><span>MarginRoom <small lang="zh-CN">阅间</small></span></a><div className="home-nav"><div className="home-language" role="group" aria-label="Language"><button aria-pressed={language==='zh'} onClick={()=>changeLanguage('zh')}>中文</button><button aria-pressed={language==='en'} onClick={()=>changeLanguage('en')}>EN</button></div><button onClick={onOpenOnline}>{t('在线体验','Try online')}</button></div></header>
  <main>
   <section className="home-hero">
    <div className="home-intro"><h1>{t('Agent 时代的\nAI 阅读与学习伙伴','Your AI Reading & Learning Partner\nfor the Agent Era')}</h1><p>{t('导入你想读的书、论文或文章。阅间知道你读到哪，帮你查全书、理解难点，把收获留成笔记和 Anki 复习卡。','Bring a book, paper, or article. MarginRoom follows your place, finds context across the text, and helps turn understanding into notes and Anki cards.')}</p><div className="home-cta-row"><button className="home-cta" onClick={onStartReading}>{t('打开本地阅读器','Open local reader')}</button><button className="home-demo-link" onClick={()=>{demo.current?.scrollIntoView({block:'nearest',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});if(!playing)play();}}>{t('看一次伴读','See it in action')}<ArrowUpRight size={15}/></button></div><span className="home-allowance">{t('本地运行 · AI 伴读需配置 DeepSeek API','Runs locally · Add a DeepSeek API key for AI')}</span></div>
    <section className="reading-demo" ref={demo} aria-label={t('阅读过程演示','Reading walkthrough')}>
     <div className="demo-heading"><h2>{t('一本书，一个问题，一起读懂。','A passage. A question. A clearer understanding.')}</h2><span>{t('交互演示','Interactive demo')}</span></div>
     <div className="demo-book">
      <div className="demo-book-header"><div><span className="demo-role">{t('你正在读的书','The book you’re reading')}</span><strong><BookOpen size={15}/>{words(copy.bookTitle)}</strong></div><span className="demo-read-count">{t('已读 2 / 3 章','2 of 3 chapters read')}</span></div>
      <div className="demo-book-body"><nav aria-label={t('示例书目录','Sample book contents')}>{copy.chapters.map((chapter,i)=><div key={i} className={`demo-chapter ${i===(away?0:2)?'current':''} ${step===1&&i===0?'found':''}`}><span>{i+1}</span>{words(chapter)}</div>)}</nav>
       <article><div className="demo-page-location">{away?t('第一章 · 第 12 页','Chapter 1 · Page 12'):t('第三章 · 第 38 页','Chapter 3 · Page 38')}</div><h3>{words(away?copy.earlierTitle:copy.currentTitle)}</h3>{(away?copy.earlierParagraphs:copy.currentParagraphs).map((p,i)=><p key={i}>{away&&i===0?<mark>{words(p)}</mark>:words(p)}</p>)}{away&&<button className="demo-return" onClick={returnToReading}>{t('回到第三章 · 第 38 页','Return to chapter 3 · Page 38')}<ArrowUpRight size={13}/></button>}</article>
      </div><div className="demo-page-footer"><span>{t('示例读物 · 原创节选','Sample book · Original excerpt')}</span><span>{away?t('原位置已保留：第 38 页','Place saved: page 38'):t('当前位置：第 38 页','Current place: page 38')}</span></div>
     </div>
     <div className="demo-question"><span>{t('你问','You ask')}</span><p>{words(copy.prompt)}</p></div>
     <div className="demo-companion"><div className="demo-companion-name"><BookOpen size={17}/><strong>{t('阅间','MarginRoom')}</strong><span>{t('AI 阅读伙伴','AI reading companion')}</span></div>
      <div className="demo-response" aria-live="polite" aria-atomic="true"><strong>{statuses[step]}</strong><p>{words(copy.answers[step])}</p></div>
      {step===4&&<div className="demo-results"><div className="demo-tabs" role="tablist" aria-label={t('阅读收获','Reading takeaways')}><button id="demo-tab-note" role="tab" aria-controls="demo-result" aria-selected={tab==='note'} onClick={()=>setTab('note')}><FileText size={14}/>{t('笔记','Note')}</button><button id="demo-tab-cards" role="tab" aria-controls="demo-result" aria-selected={tab==='cards'} onClick={()=>setTab('cards')}><Layers size={14}/>{t('复习卡 2','Review cards 2')}</button></div><div id="demo-result" role="tabpanel" aria-labelledby={tab==='note'?'demo-tab-note':'demo-tab-cards'}>{tab==='note'?<div className="demo-note"><h4>{words(copy.noteTitle)}</h4><p>{words(copy.note)}</p></div>:copy.cards.map((card,i)=><div key={i} className="demo-card"><button aria-expanded={opened.includes(i)} onClick={()=>setOpened(old=>old.includes(i)?old.filter(n=>n!==i):[...old,i])}>{words(card.q)}<span>{opened.includes(i)?t('收起','Hide'):t('看答案','Reveal')}</span></button>{opened.includes(i)&&<p>{words(card.a)}</p>}</div>)}<div className="demo-sources"><button onClick={()=>setSource(1)}>{t('来源：第一章','Source: chapter 1')}</button><button onClick={()=>setSource(3)}>{t('来源：第三章','Source: chapter 3')}</button>{tab==='cards'&&<button onClick={downloadCards}>{t('导出 Anki 卡片','Export Anki cards')}</button>}</div></div></div>}
      <div className="demo-controls"><button className="demo-play" onClick={play}>{playing?t('暂停','Pause'):step===0?t('看阅间怎么做','Start walkthrough'):step===4?t('再看一遍','Replay'):t('继续演示','Resume')}</button><div className="demo-steps" role="group" aria-label={t('查看演示步骤','View walkthrough steps')}>{labels.map((label,i)=><button key={i} aria-pressed={step===i+1} onClick={()=>selectStep(i+1)}><span>{i+1}</span>{label}</button>)}</div></div>
     </div><p className="demo-caption">{t('以上为预设演示；开始阅读后，AI 将围绕你自己的资料回答。','A scripted walkthrough. When you start reading, the AI works with your own documents.')}</p>
    </section>
   </section>
   <section className="home-start" aria-label={t('如何开始','Getting started')}><h2>{t('这样开始你的第一次伴读','Your first reading session')}</h2><div className="home-start-steps"><div><span>1</span><h3>{t('导入你的资料','Bring your reading')}</h3><p>{t('书籍、论文、长文章。支持 PDF、EPUB、MOBI、AZW3、Markdown 和 TXT。','Books, papers, and articles in PDF, EPUB, MOBI, AZW3, Markdown, or TXT.')}</p></div><div><span>2</span><h3>{t('边读，边问','Read and ask')}</h3><p>{t('不用反复复制背景。它知道你读到哪，也能带你查前文。','No need to keep pasting context. It follows your place and takes you to earlier passages.')}</p></div><div><span>3</span><h3>{t('把收获留下来','Keep what you learn')}</h3><p>{t('对话、笔记、复习卡留在一起。需要时，导出到 Anki。','Keep conversations, notes, and review cards together. Export cards to Anki when you want.')}</p></div></div></section>
  </main><footer><span>MarginRoom · 阅间</span><span>{t('让阅读走向理解，让理解留得下来。','Read for understanding. Keep what you learn.')}</span><a href="https://github.com/wanghao-SunSky/MarginRoom/blob/main/SECURITY.md">{t('隐私说明','Privacy')}</a></footer>
 </div>;
}
