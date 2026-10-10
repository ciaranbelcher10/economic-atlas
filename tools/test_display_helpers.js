// v1.7.36 display helpers: year ticks, tile titles, FX and money formatting.
//   node tools/test_display_helpers.js   -> "N checks, 0 failures"
// Pulls the functions out of every country page that carries them, so a
// page that drifts from the shared code fails here.
const fs=require("fs"), path=require("path"), vm=require("vm");
const root=path.join(__dirname,"..");
let checks=0, fails=0;
function check(n,ok,d){ checks++; if(!ok){ fails++; console.log("FAIL",n,d===undefined?"":JSON.stringify(d)); } }
function grab(src,name){
  const i=src.indexOf("function "+name+"(");
  if(i<0) return null;
  let j=src.indexOf("{",i), depth=0, k=j;
  for(;k<src.length;k++){ if(src[k]==="{") depth++; else if(src[k]==="}"){ depth--; if(!depth) break; } }
  return src.slice(i,k+1);
}
const pages=fs.readdirSync(root).filter(f=>f.endsWith(".html")).filter(f=>fs.readFileSync(path.join(root,f),"utf8").includes("const baseScales=(fmtY)=>({"));
check("country pages found", pages.length>=43, pages.length);
function mkScale(labels,min,max){ return {chart:{data:{labels}},min:min,max:max,ticks:[]}; }
const months=(a,b)=>{const o=[];for(let y=a;y<=b;y++)for(let m=1;m<=12;m++)o.push(y+"-"+String(m).padStart(2,"0"));return o;};
const quarters=(a,b)=>{const o=[];for(let y=a;y<=b;y++)for(let q=1;q<=4;q++)o.push(y+"-Q"+q);return o;};
const years=(a,b)=>{const o=[];for(let y=a;y<=b;y++)o.push(String(y));return o;};
for(const f of pages){
  const src=fs.readFileSync(path.join(root,f),"utf8");
  const ctx={};
  const glyph=(src.match(/const ISO_GLYPH = \{[^\n]*\};/)||["const ISO_GLYPH={};"])[0].replace("const ","var ");
  const code="var TOGGLE_STATE={dollar:false,real:false}, PAGE_DATA=null;\n"+glyph+"\n"+["EA_yearTicks","fxRateTxt","labelHtml","scaleOf","currencySymbol","curFmt","fxNum","tileNum"].map(n=>grab(src,n)).filter(Boolean).join("\n");
  vm.runInNewContext(code+"\nthis.E={EA_yearTicks,fxRateTxt,labelHtml,curFmt,fxNum,tileNum};",ctx);
  const E=ctx.E;
  check(f+" helpers present", E && E.EA_yearTicks && E.labelHtml && E.fxRateTxt && E.curFmt && E.fxNum);
  // ticks: equal gaps, whole years, at most 7, on first period of a year
  for(const [lab,name] of [[months(2015,2026).slice(0,139),"m2015"],[months(1993,2026).slice(0,-4),"m1993"],[quarters(1995,2026).slice(1,-2),"q1995"],[years(1960,2025),"y1960"],[months(2002,2026).slice(0,-5),"m2002"],[months(2020,2026),"m2020"]]){
    const s=mkScale(lab,0,lab.length-1); E.EA_yearTicks(s,7);
    const ys=s.ticks.map(t=>+lab[t.value].slice(0,4));
    const gaps=ys.slice(1).map((y,i)=>y-ys[i]);
    check(f+" ticks "+name+" count", ys.length>=2 && ys.length<=7, ys);
    check(f+" ticks "+name+" equal gaps", gaps.every(g=>g===gaps[0]), ys);
    check(f+" ticks "+name+" first period", s.ticks.every(t=>t.value===0||lab[t.value-1].slice(0,4)!==lab[t.value].slice(0,4)), ys);
  }
  // zoomed range uses the visible window
  { const lab=months(2015,2026); const s=mkScale(lab,lab.indexOf("2024-03"),lab.length-1); E.EA_yearTicks(s,7);
    check(f+" ticks zoom", s.ticks.length && lab[s.ticks[0].value]==="2025-01", s.ticks.map(t=>lab[t.value])); }
  // non-year labels left alone
  { const s=mkScale(["a","b","c"],0,2); s.ticks=[{value:0}]; E.EA_yearTicks(s,7); check(f+" ticks untouched", s.ticks.length===1); }
  check(f+" fxRateTxt raw float", E.fxRateTxt(4.47053333333333)==="4.4705", E.fxRateTxt(4.47053333333333));
  check(f+" fxRateTxt keeps", E.fxRateTxt(353.14)==="353.14" && E.fxRateTxt(21.882)==="21.882" && E.fxRateTxt(3.75)==="3.75");
  const icon='<button class="infoBtn">i</button>';
  check(f+" label nowrap", E.labelHtml("NBR policy rate",icon)==='NBR policy <span class="nw">rate'+icon+'</span>', E.labelHtml("NBR policy rate",icon));
  check(f+" label case tag", E.labelHtml("Growth (QoQ)",icon).includes('(<span class="lc">q/q</span>)'), E.labelHtml("Growth (QoQ)",icon));
  check(f+" label no icon", E.labelHtml("Czech koruna in euros","")==="Czech koruna in euros");
  check(f+" money zero", E.curFmt(0,"CZKm",0)==="CZK0", E.curFmt(0,"CZKm",0));
  check(f+" money neg zero", E.curFmt(-0,"HUFbn",0)==="HUF0", E.curFmt(-0,"HUFbn",0));
  check(f+" money axis trims", E.curFmt(600000,"CZKm",1)==="CZK600bn", E.curFmt(600000,"CZKm",1));
  check(f+" money tile keeps", E.curFmt(5.0e6,"HUFm",1,true)==="HUF5.0tn", E.curFmt(5.0e6,"HUFm",1,true));
  check(f+" fx 4 sig figs", E.fxNum(0.0404)==="0.04040" && E.fxNum(0.2505)==="0.2505" && E.fxNum(1.25)==="1.250", [E.fxNum(0.0404),E.fxNum(0.2505),E.fxNum(1.25)]);
  check(f+" fx 4 sig figs above 1", E.fxNum(1.1259)==="1.126" && E.fxNum(0.8508)==="0.8508" && E.fxNum(24.531)==="24.53" && E.fxNum(353.14)==="353", [E.fxNum(1.1259),E.fxNum(24.531),E.fxNum(353.14)]);
  check(f+" tileNum present", typeof E.tileNum==="function");
  if(E.tileNum){
    const M="\u2212";
    check(f+" tile signed zero", E.tileNum("-0.0%")==="0.0%" && E.tileNum(M+"0.00pp")==="0.00pp" && E.tileNum(M+"\u20ac0m")==="\u20ac0m", [E.tileNum("-0.0%")]);
    check(f+" tile true minus", E.tileNum("-4.5%")===M+"4.5%" && E.tileNum("-0.1pp")===M+"0.1pp" && E.tileNum("$-2.5bn")==="$"+M+"2.5bn", [E.tileNum("-4.5%"),E.tileNum("$-2.5bn")]);
    check(f+" tile untouched", E.tileNum("+0.8pp")==="+0.8pp" && E.tileNum("0.00%")==="0.00%" && E.tileNum("Q1-2026")==="Q1-2026" && E.tileNum('$1.126<span class="fxper">per \u20ac1</span>')==='$1.126<span class="fxper">per \u20ac1</span>' && E.tileNum(5)===5);
    check(f+" tile wired", src.includes("${tileNum(opts.fmt(last[1]))}") && src.includes("${tileNum(opts.fmtD(dShow))}"));
  }
  // tile money calls all keep decimals
  const tileMoney=(src.match(/\{fmt:v=>curFmt\(v,s\.[a-z_]+\.unit,1(,true)?\)/g)||[]);
  check(f+" tile money keeps decimals", tileMoney.every(m=>m.endsWith(",true)")), tileMoney.filter(m=>!m.endsWith(",true)")));
  check(f+" FX zero change unsigned", !src.includes('return (pc<0?"\\u2212":"+")'));
  check(f+" no raw rate in note", !/latest \$\{fx\.rate\}|= \$\{fx\.rate\} \(as of/.test(src));
  check(f+" ticks wired", src.includes("afterBuildTicks:s=>EA_yearTicks(s,7)") && !src.includes("maxTicksLimit:7"));
  check(f+" label wired", src.includes("${labelHtml(title, infoIconHtml("));
  check(f+" style v53", src.includes("style.css?v=53") && !src.includes("style.css?v=52"));
}
console.log(checks+" checks, "+fails+" failures"); process.exit(fails?1:0);
