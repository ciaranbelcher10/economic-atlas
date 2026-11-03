// Test helper (v1.9.76): boots compare.html under jsdom with d3/topojson/Chart stubs, phone or desktop, then evals mobile.js.
const fs=require("fs"),path=require("path");const {JSDOM,VirtualConsole}=require("jsdom");
const ROOT=require("path").resolve(__dirname,".."),NM=process.env.NODE_PATH||"/tmp/node_modules";
module.exports=async function(opts){opts=opts||{};
 const html=require(ROOT+"/tools/inline_local_scripts")(fs.readFileSync(ROOT+"/compare.html","utf8"),ROOT);
 const store=Object.assign({},opts.store||{});const errs=[];const vc=new VirtualConsole();
 vc.on("jsdomError",e=>{const m=String(e&&e.message||e).split("\n")[0];if(!/supabase|EATLAS_PREFS|Not implemented/i.test(m))errs.push(m);});
 const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,virtualConsole:vc,url:"https://theeconomicatlas.com/compare",
 beforeParse(win){win.HTMLCanvasElement.prototype.getContext=()=>new Proxy({},{get(){return function(){return{addColorStop(){}};};}});
  function C(c,cfg){this.data=(cfg&&cfg.data)||{datasets:[]};this.options=(cfg&&cfg.options)||{};this.canvas=c;}C.prototype.update=function(){};C.prototype.destroy=function(){};C.prototype.resetZoom=function(){};C.register=function(){};win.Chart=C;
  win.eval(fs.readFileSync(NM+"/d3/dist/d3.min.js","utf8"));win.eval(fs.readFileSync(NM+"/topojson/dist/topojson.min.js","utf8"));
  Object.defineProperty(win,"localStorage",{configurable:true,value:{getItem:k=>(k in store?store[k]:null),setItem:(k,v)=>{store[k]=String(v);},removeItem:k=>{delete store[k];},clear(){},key:()=>null,get length(){return 0;}}});
  win.matchMedia=()=>({matches:opts.desktop?false:true,addListener(){},removeListener(){},addEventListener(){},removeEventListener(){}});
  win.fetch=u=>{const f=String(u).split("/").pop().split("?")[0];const p=/countries-110m/.test(String(u))?NM+"/world-atlas/countries-110m.json":path.join(ROOT,f);
   if(!fs.existsSync(p))return Promise.reject(new Error("no "+f));return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(JSON.parse(fs.readFileSync(p,"utf8"))),text:()=>Promise.resolve(fs.readFileSync(p,"utf8"))});};}});
 const win=dom.window;await new Promise(r=>win.addEventListener("load",r,{once:true}));
 for(let i=0;i<120&&win.document.getElementById("mainContent").style.display==="none";i++)await new Promise(r=>setTimeout(r,50));
 await new Promise(r=>setTimeout(r,600));
 if(!opts.noMobile){win.eval(fs.readFileSync(ROOT+"/mobile.js","utf8"));await new Promise(r=>setTimeout(r,200));}
 return {win,doc:win.document,errs,store};};
