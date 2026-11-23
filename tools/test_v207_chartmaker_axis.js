#!/usr/bin/env node
/* v2.0.7: Chartmaker (1) date labels on long monthly charts sit on year starts, not drifting months;
 * (2) an axis title the person cleared stays cleared after save and reopen; older saves still auto-title.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v207_chartmaker_axis.js */
let checks=0, failures=0; const ok=(c,m)=>{checks++; if(!c){failures++; console.log("  FAIL  "+m);}};
const path=require('path'); const ROOT=path.resolve(__dirname,'..'); process.chdir(ROOT);
const src=require('fs').readFileSync('tools/test_v203_bar_colours.js','utf8');
const bootSrc=src.slice(src.indexOf('async function boot'),src.indexOf('(async () => {'));
const fs=require('fs');const NM=(process.env.NODE_PATH||'/tmp/node_modules').split(path.delimiter)[0]+'/'; const {JSDOM,VirtualConsole}=require(NM+'jsdom');
eval(bootSrc.replace('require("./inline_local_scripts")','require(path.join(ROOT,"tools/inline_local_scripts"))'));
(async()=>{
 const win=await boot(); const run=js=>win.__cmEval(js);
 run(`series.length=0; addSeries("US","cpi",false,true); addSeries("UK","cpi",false,true); chartType="line"; renderChart();`);
 const svg=run(`czmBuildSVG(cmPreviewTheme(), false)`);
 const labs=[...String(svg).matchAll(/>((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Q\d)[^<]{0,10}\d{4})</g)].map(m=>m[1]);
 ok(labs.length>=3 && labs.every(l=>/^(Jan|Q1) \d{4}$/.test(l)), 'long monthly chart labels sit on year starts: '+labs.join(' | '));
 ok(run('style.yAxisTitle')==='%' && run('yAxisTitleTouched')===false, 'a fresh CPI chart is auto-titled %');
 // user clears title
 run(`var el=document.getElementById("cmYAxisTitle"); el.value=""; el.dispatchEvent(new Event("input"));`);
 const snap=JSON.parse(run(`JSON.stringify((function(){var o={}; return {yAxisTitle:style.yAxisTitle, yAxisTitleTouched:yAxisTitleTouched};})())`));
 ok(snap.yAxisTitle==='' && snap.yAxisTitleTouched===true, 'clearing the title marks it touched');
 const payload=run('JSON.stringify(buildSavePayload("t"))');
 const row=JSON.parse(payload); ok(row.style.snapshot.yAxisTitleTouched===true, 'the save carries the touched flag');
 run('series.length=0; yAxisTitleTouched=false; style.yAxisTitle="";');
 run('loadSavedChart(normalizeSavedRow('+payload+'))');
 ok(run('style.yAxisTitle')==='' && run('yAxisTitleTouched')===true, 'a cleared title stays cleared after reopening');
 // legacy row with no flag and empty title -> auto
 const legacy=JSON.parse(payload); delete legacy.style.snapshot.yAxisTitleTouched;
 run('loadSavedChart(normalizeSavedRow('+JSON.stringify(legacy)+'))');
 ok(run('style.yAxisTitle')==='%', 'an older save with no flag and no title is still auto-titled');
 console.log('test_v207_chartmaker_axis: '+checks+' checks, '+failures+' failures'); process.exit(failures?1:0);
})().catch(e=>{console.log(e);process.exit(1)});
