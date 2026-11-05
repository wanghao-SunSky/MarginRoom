import { createRoot } from 'react-dom/client';
import {lazy,Suspense,useState} from 'react';
import Home from './Home';
const App=lazy(()=>import('./App'));
import './styles.css';
import 'katex/dist/katex.min.css';
function LocalReader(){
 const [home,setHome]=useState(new URLSearchParams(location.search).has('home'));
 return home?<Home onStartReading={()=>{history.replaceState(null,'','/');setHome(false);}} onOpenOnline={()=>{location.href='https://marginroom.app';}}/>:<Suspense fallback={<main>正在打开阅读空间 / Opening your library…</main>}><App/></Suspense>;
}
createRoot(document.getElementById('root')!).render(<LocalReader/>);
