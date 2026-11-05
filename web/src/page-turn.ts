// A new scroll gesture must start at the edge. Momentum that merely reaches
// the bottom cannot skip the final paragraph or flip several short chapters.
export class PageTurnGesture {
 private last = -Infinity;
 private amount = 0;
 private armed = false;
 private turned = -Infinity;
 wheel(atEnd:boolean, delta:number, now:number):boolean {
  if(now-this.last>600){this.armed=atEnd;this.amount=0;}
  this.last=now;
  if(!atEnd||delta<=0){this.armed=false;this.amount=0;return false;}
  if(!this.armed||now-this.turned<1400)return false;
  this.amount+=delta;
  if(this.amount<100)return false;
  this.armed=false;this.amount=0;this.turned=now;return true;
 }
 reset(){this.last=-Infinity;this.amount=0;this.armed=false;}
}
export function atReadingEnd(el:{scrollHeight:number,scrollTop:number,clientHeight:number}){
 return el.scrollHeight-el.scrollTop-el.clientHeight<=3;
}
export function showIncomplete(status:string){return ['failed','cancelled','interrupted'].includes(status);}
