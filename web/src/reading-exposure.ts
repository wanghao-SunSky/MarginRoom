/** Reading progress is an estimate of attentive exposure, never a mastery score. */
export class ReadingExposure {
 private bins=new Array<number>(20).fill(0);
 private previous:{now:number,from:number,to:number}|undefined;
 private dwell=0;
 readonly requiredMs:number;
 constructor(characters:number){this.requiredMs=Math.min(30000,Math.max(3000,characters/60*1000));}
 observe(now:number,from:number,to:number,active:boolean):boolean {
  if(!active||!Number.isFinite(from)||!Number.isFinite(to)||to<=from){this.previous=undefined;return false;}
  from=Math.max(0,from);to=Math.min(1,to);
  const prior=this.previous;this.previous={now,from,to};
  if(!prior)return false;
  const elapsed=now-prior.now;
  // Background timer suspension and jumps cannot count as time spent reading.
  if(elapsed<=0||elapsed>1500)return false;
  const start=Math.max(from,prior.from),end=Math.min(to,prior.to);
  if(end-start<Math.min(to-from,prior.to-prior.from)*.75)return false;
  this.dwell+=elapsed;
  for(let i=0;i<20;i++)if((i+.5)/20>=start&&(i+.5)/20<=end)this.bins[i]+=elapsed/Math.max(.05,to-from);
  return this.dwell>=this.requiredMs&&this.bins[0]>=this.requiredMs&&this.bins[19]>=this.requiredMs&&this.bins.filter(ms=>ms>=this.requiredMs).length>=18;
 }
}
