import { readFileSync, writeFileSync } from 'node:fs';
const [,, interval, debtFile, outputPrefix, seedText='1']=process.argv;
let rng=Number(seedText)>>>0;
Math.random=()=>{rng=(Math.imul(rng,1664525)+1013904223)>>>0;return rng/4294967296;};
const {BirdsEyeWorm}=await import('./build/src/BirdsEyeWorm.js');
const worm=new BirdsEyeWorm(false,`${outputPrefix}.cycles`);
const input=readFileSync(debtFile,'utf8').trim().split('\n');
let weight=0;
for(const line of input){const [u,v,a]=line.trim().split(/\s+/);worm.addTransfer(u,v,Number(a));weight+=Number(a);}
const calls={work1:0,work2:0};
for (const name of Object.keys(calls)) { const original=worm[name].bind(worm); worm[name]=async(...args)=>{calls[name]++;return original(...args);}; }
const started=performance.now();
process.on('exit',(code)=>{
 const summary={code,interval:Number(interval),seed:Number(seedText),inputWeight:weight,calls,wallSeconds:(performance.now()-started)/1000,loops:worm.numLoopsFound,linksPruned:worm.numLinksRemoved,stats:worm.stats};
 writeFileSync(`${outputPrefix}.summary.json`,JSON.stringify(summary,null,2));
});
await worm.runWorms();
