// Runs compare.html's own script against the repo's data files and prints the
// figure each card would show, so aggregation rules are checked by executing
// them rather than by reading them.
//
//   node tools/compare_values.js 2025                  every concept, every country
//   node tools/compare_values.js 2025 cpi trade_balance only these concepts
//   node tools/compare_values.js --json 2025 > out.json
//
// Each row carries the value, the unit it is expressed in, and the coverage
// note Compare attaches (when the page defines yearCoverageNote).
const fs = require('fs'), path = require('path'), vm = require('vm');
const REPO = process.env.ATLAS_REPO || path.resolve(__dirname, '..');

function makeEl(id){
  const el = {
    id, hidden:false, disabled:false, textContent:'', innerHTML:'', className:'', value:'', style:{}, dataset:{},
    children:[], options:[], checked:false,
    classList:{add(){},remove(){},toggle(){},contains(){return false;}},
    addEventListener(){}, removeEventListener(){}, appendChild(c){return c;}, removeChild(){}, insertBefore(c){return c;},
    setAttribute(){}, getAttribute(){return null;}, removeAttribute(){}, focus(){}, blur(){}, click(){},
    querySelector(){return makeEl('q');}, querySelectorAll(){return [];}, closest(){return null;},
    getBoundingClientRect(){return {left:0,top:0,width:800,height:400,right:800,bottom:400};},
    getContext(){ return new Proxy({}, {get(){ return function(){ return {}; }; }}); },
    cloneNode(){ return makeEl(id); }, scrollIntoView(){}, contains(){ return false; },
  };
  return new Proxy(el, {get(t,k){ if(k in t) return t[k]; return function(){ return makeEl('anon'); }; }, set(t,k,v){ t[k]=v; return true; }});
}

function extractMain(html){
  const re = /<script>([\s\S]*?)<\/script>/g; let m;
  while((m = re.exec(html))) if(m[1].includes('function getSnapshotValue')) return m[1];
  throw new Error('compare script block not found');
}

async function load(){
  const html = fs.readFileSync(path.join(REPO, 'compare.html'), 'utf8');
  let src = extractMain(html);
  // Stop the page booting its UI; the harness drives loadAll itself.
  src = src.replace(/\nloadAll\(\)\.then\(function\(\)\{/, '\nfalse && loadAll().then(function(){');
  const tail = src.lastIndexOf('})();');
  if(tail < 0) throw new Error('compare script does not end with an IIFE');
  const REQUIRED = ['loadAll','getSnapshotValue','getChangeValue','yearAggregate','resolveKey','hasConcept','displayString',
    'metricSourceNote','historyPoints','getMapValueForYear'];
  const OPTIONAL = ['getSourceNote','noDataReason','annualValue','yearWindow','lastEndedYear','computeCurrentYear',
    'unitCompatible','yearCoverageNote','measureTag'];
  const exportsSrc = '\n;globalThis.__atlas = {'
    + REQUIRED.map(n => n + ': ' + n).join(', ') + ', '
    + OPTIONAL.map(n => n + ': (typeof ' + n + ' === "function" ? ' + n + ' : null)').join(', ') + ', '
    + 'CONCEPT_UNIT: CONCEPT_UNIT, CONCEPT_LABEL: CONCEPT_LABEL, CONCEPT_KEYS: CONCEPT_KEYS, ALL_COUNTRIES: ALL_COUNTRIES, REGISTRY: REGISTRY, '
    + 'get CURRENT_YEAR(){ return CURRENT_YEAR; }};\n';
  src = src.slice(0, tail) + exportsSrc + src.slice(tail);
  const doc = new Proxy({
    getElementById: (id) => makeEl(id), querySelector: () => makeEl('q'), querySelectorAll: () => [],
    createElement: (t) => makeEl(t), createElementNS: (n,t) => makeEl(t), createTextNode: () => makeEl('t'),
    addEventListener(){}, removeEventListener(){}, body: makeEl('body'), documentElement: makeEl('html'), head: makeEl('head'),
    readyState: 'complete', cookie: '',
  }, {get(t,k){ return k in t ? t[k] : function(){ return makeEl('d'); }; }});
  const store = {};
  const win = {};
  const ctx = {
    document: doc, window: win, console: {log(){}, warn(){}, error(){}, info(){}},
    fetch: (url) => {
      const p = path.join(REPO, String(url).split('?')[0].replace(/^\//, ''));
      if(!fs.existsSync(p)) return Promise.resolve({ok:false, status:404, json: () => Promise.reject(new Error('404'))});
      const body = fs.readFileSync(p, 'utf8');
      return Promise.resolve({ok:true, status:200, json: () => Promise.resolve(JSON.parse(body)), text: () => Promise.resolve(body)});
    },
    setTimeout: (f, ms) => 0, clearTimeout(){}, setInterval(){ return 0; }, clearInterval(){},
    requestAnimationFrame(){ return 0; }, cancelAnimationFrame(){},
    localStorage: {getItem: k => (k in store ? store[k] : null), setItem: (k,v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; }},
    sessionStorage: {getItem(){ return null; }, setItem(){}, removeItem(){}},
    location: {href:'https://theeconomicatlas.com/compare', search:'', hash:'', pathname:'/compare'},
    history: {replaceState(){}, pushState(){}}, navigator: {userAgent:'node', clipboard:{}},
    matchMedia: () => ({matches:false, addEventListener(){}, addListener(){}}),
    getComputedStyle: () => ({getPropertyValue(){ return ''; }}),
    URL, URLSearchParams, Blob: function(){}, Image: function(){ return makeEl('img'); },
    ResizeObserver: function(){ return {observe(){}, disconnect(){}}; },
    IntersectionObserver: function(){ return {observe(){}, disconnect(){}}; },
    MutationObserver: function(){ return {observe(){}, disconnect(){}}; },
    supabase: {createClient: () => new Proxy({}, {get(){ return new Proxy(function(){}, {get(){ return function(){ return Promise.resolve({data:{session:null}, error:null}); }; }, apply(){ return Promise.resolve({data:null, error:null}); }}); }})},
    Chart: function(){ return {destroy(){}, update(){}}; },
  };
  Object.assign(win, ctx, {addEventListener(){}, removeEventListener(){}, scrollTo(){}, innerWidth: 1200, innerHeight: 800, devicePixelRatio: 1});
  const winProxy = new Proxy(win, {get(t,k){ return k in t ? t[k] : undefined; }, set(t,k,v){ t[k]=v; return true; }});
  ctx.window = winProxy; ctx.self = winProxy; ctx.globalThis = undefined;
  vm.createContext(ctx);
  ctx.globalThis = ctx;
  vm.runInContext(src, ctx, {filename: 'compare.html#main'});
  const A = ctx.__atlas;
  await A.loadAll();
  return A;
}

function rows(A, year, concepts){
  const out = [];
  for(const concept of concepts){
    for(const country of A.ALL_COUNTRIES){
      if(!A.hasConcept(country, concept)) continue;
      const v = A.getSnapshotValue(country, concept, year);
      const note = A.yearCoverageNote ? A.yearCoverageNote(country, concept, year) : null;
      const tag = A.measureTag ? A.measureTag(country, concept) : null;
      out.push({concept, country, year, value: v ? v.value : null, unit: v ? (v.rawUnit || v.unit) : null, note, tag});
    }
  }
  return out;
}

module.exports = {load, rows};

if(require.main === module){
  (async () => {
    const args = process.argv.slice(2);
    const asJson = args[0] === '--json'; if(asJson) args.shift();
    const A = await load();
    const year = +(args.shift() || A.CURRENT_YEAR);
    const concepts = args.length ? args : Object.keys(A.CONCEPT_UNIT);
    const r = rows(A, year, concepts);
    if(asJson){ process.stdout.write(JSON.stringify({current_year: A.CURRENT_YEAR, year, rows: r})); return; }
    console.log(`slider maximum (CURRENT_YEAR): ${A.CURRENT_YEAR}   year shown: ${year}`);
    for(const x of r){
      const val = x.value == null ? 'n/a' : x.value;
      console.log(`${x.concept.padEnd(20)} ${x.country.padEnd(13)} ${String(val).padStart(14)} ${String(x.unit||'').padEnd(9)} ${x.tag ? '['+x.tag+'] ' : ''}${x.note || ''}`);
    }
  })().catch(e => { console.error(e); process.exit(1); });
}
