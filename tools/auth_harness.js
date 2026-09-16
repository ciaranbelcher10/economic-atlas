// Executes a page's real auth <script> under a stubbed DOM and a scripted
// Supabase client, then drives every auth action through every failure shape
// and reports the button state and the message a visitor would see.
//   node tools/auth_harness.js uk.html            (one page, full table)
//   node tools/auth_harness.js --all              (every page with auth, summary)
const fs = require('fs'), path = require('path'), vm = require('vm');
const REPO = process.env.ATLAS_REPO || path.resolve(__dirname, '..');

function extractAuthScript(html){
  const re = /<script>([\s\S]*?)<\/script>/g; let m;
  while((m = re.exec(html))) if(m[1].includes('sb.auth.signInWithPassword')) return m[1];
  return null;
}
function makeEl(id){
  const handlers = {};
  const el = {
    id, hidden:false, disabled:false, textContent:'', className:'', value:'x@y.co', innerHTML:'',
    style:{}, dataset:{}, children:[],
    classList:{add(){},remove(){},toggle(){},contains(){return false;}},
    addEventListener(t,f){ (handlers[t]=handlers[t]||[]).push(f); },
    removeEventListener(){}, reset(){}, focus(){}, setAttribute(){}, getAttribute(){return null;},
    appendChild(c){return c;}, querySelector(){return makeEl('q');}, querySelectorAll(){return [];},
    closest(){return null;}, getBoundingClientRect(){return {left:0,top:0,width:0,height:0,bottom:0};},
    fire(t){ (handlers[t]||[]).forEach(f=>f({preventDefault(){}, target:el})); },
  };
  return new Proxy(el,{get(t,k){ if(k in t) return t[k]; return function(){ return makeEl('anon'); }; }});
}
const LATE = {resolve: null};
const ERR = {
  api:  {name:'AuthApiError', status:400, message:'Invalid login credentials'},
  net:  {name:'AuthRetryableFetchError', status:0, message:'Failed to fetch'},
  down: {name:'AuthRetryableFetchError', status:503, message:'HTTP 503'},
};
function behave(shape){
  switch(shape){
    case 'ok':      return () => Promise.resolve({data:{user:{id:'u'},session:{user:{email:'x@y.co'}}}, error:null});
    case 'api':     return () => Promise.resolve({data:{}, error:ERR.api});
    case 'offline': return () => Promise.resolve({data:{}, error:ERR.net});
    case 'down':    return () => Promise.resolve({data:{}, error:ERR.down});
    case 'reject':  return () => Promise.reject(new TypeError('Failed to fetch'));
    case 'hang':    return () => new Promise(()=>{});
    case 'late':    return () => new Promise(r => { LATE.resolve = () => r({data:{user:{id:'u'},session:null}, error:null}); });
  }
}
async function run(html, action, shape){
  const src = extractAuthScript(html);
  if(!src) return null;
  const els = {};
  const created = [];
  const timers = [];
  const doc = {
    getElementById(id){ return els[id] = els[id] || makeEl(id); },
    addEventListener(){}, querySelector(){return makeEl('q');}, querySelectorAll(){return [];},
    createElement(t){ const e = makeEl(t); created.push(e); return e; }, body: makeEl('body'), documentElement: makeEl('html'),
  };
  const auth = {
    getSession: () => Promise.resolve({data:{session:null}}),
    onAuthStateChange(){ return {data:{subscription:{unsubscribe(){}}}}; },
    signUp: behave(shape), signInWithPassword: behave(shape), resetPasswordForEmail: behave(shape),
    updateUser: behave(shape), signOut: behave(shape),
  };
  const sbClient = new Proxy({auth}, {get(t,k){ return k in t ? t[k] : function(){ return new Proxy({}, {get(){ return function(){ return Promise.resolve({data:null,error:null}); }; }}); }; }});
  const WIN_FNS = new Set(['addEventListener','removeEventListener','matchMedia','scrollTo','requestAnimationFrame','open','getComputedStyle']);
  const winStore = {};
  const win = new Proxy(winStore, {get(t,k){ if(k in t) return t[k]; if(WIN_FNS.has(k)) return function(){ return {matches:false, addEventListener(){}, addListener(){}}; }; return undefined; }});
  const ctx = {
    window: win, document: doc, console: {log(){},warn(){},error(){}},
    supabase: {createClient: () => sbClient},
    setTimeout: (f,ms) => { timers.push({f,ms,done:false}); return timers.length; },
    clearTimeout: (i) => { if(timers[i-1]) timers[i-1].done = true; },
    setInterval(){ return 0; }, clearInterval(){},
    localStorage: {getItem(){return null;},setItem(){},removeItem(){}},
    location: {href:'',search:'',hash:'',pathname:'/'}, navigator: {userAgent:''},
    fetch: () => new Promise(()=>{}), URL, URLSearchParams,
    requestAnimationFrame(){ return 0; }, matchMedia(){ return {matches:false, addEventListener(){}, addListener(){}}; },
    history: {replaceState(){}, pushState(){}}, sessionStorage: {getItem(){return null;},setItem(){},removeItem(){}},
  };
  winStore.document = doc; winStore.location = ctx.location; winStore.localStorage = ctx.localStorage;
  vm.createContext(ctx);
  try { vm.runInContext(src, ctx, {timeout: 2000}); } catch(e) { return {error: 'script threw: ' + e.message}; }
  const spec = {
    signUp:                ['authForm', 'submit', 'authSubmitBtn', 'authMsg', 'signup'],
    signInWithPassword:    ['authForm', 'submit', 'authSubmitBtn', 'authMsg', 'login'],
    resetPasswordForEmail: ['authForgotForm', 'submit', 'authForgotSubmitBtn', 'authForgotMsg'],
    updateUser:            ['authResetForm', 'submit', 'authResetSubmitBtn', 'authResetMsg'],
    signOut:               ['authSignOutBtn', 'click', 'authSignOutBtn', 'authSignOutMsg'],
  }[action];
  const [formId, evt, btnId, msgId, mode] = spec;
  const unhandled = [];
  const crossScript = [];
  const onUnhandled = (e) => {
    const m = e && e.name === 'ReferenceError' && /^(\w+) is not defined/.exec(e.message);
    if(m && new RegExp('function\\s+' + m[1] + '\\s*\\(').test(html)) { crossScript.push(m[1]); return; }
    unhandled.push(e); if(process.env.AUTH_HARNESS_DEBUG) console.error("UNHANDLED:", e && e.stack ? e.stack.split("\n").slice(0,3).join(" | ") : e); };
  process.on('unhandledRejection', onUnhandled);
  if(mode === 'signup') {
    doc.getElementById('authBtn').fire('click');
    await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
    const t = created.filter(e => e.textContent === 'Sign up').pop();
    if(!t) return {error: 'no Sign up toggle created'};
    t.fire('click');
    if(doc.getElementById('authSubmitBtn').textContent !== 'Sign up') return {error: 'did not enter sign-up mode'};
  }
  doc.getElementById(formId).fire(evt);
  await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
  let pending = timers.filter(t => !t.done && t.ms >= 1000);
  const hung = shape === 'hang' || shape === 'late';
  if(hung) pending.forEach(t => { t.done = true; t.f(); });
  if(shape === 'late' && LATE.resolve) { LATE.resolve(); LATE.resolve = null; await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r)); }
  const btn = doc.getElementById(btnId);
  const msg = els[msgId] ? els[msgId].textContent : '(no message element)';
  const msgShown = els[msgId] && /show/.test(els[msgId].className);
  await new Promise(r => setImmediate(r));
  process.off('unhandledRejection', onUnhandled);
  return {disabled: btn.disabled, msg: msgShown ? msg : '', unhandled: unhandled.length, crossScript};
}
async function page(file){
  const html = fs.readFileSync(path.join(REPO, file), 'utf8');
  const rows = [];
  for(const a of ['signUp','signInWithPassword','resetPasswordForEmail','updateUser','signOut'])
    for(const s of ['ok','api','offline','down','reject','hang','late']) {
      const r = await run(html, a, s);
      rows.push({action:a, shape:s, ...r});
    }
  return rows;
}
(async () => {
  const arg = process.argv[2];
  if(arg === '--all'){
    const files = [];
    for(const dir of ['', 'indicators', 'embed'])
      if(fs.existsSync(path.join(REPO, dir)))
        for(const f of fs.readdirSync(path.join(REPO, dir)))
          if(f.endsWith('.html') && extractAuthScript(fs.readFileSync(path.join(REPO, dir, f), 'utf8'))) files.push(path.join(dir, f));
    let stuck = 0, raw = 0, calls = 0, errs = 0, unh = 0; const cross = new Set();
    for(const f of files){
      for(const r of await page(f)){
        calls++;
        if(r.error) errs++;
        if(r.unhandled) unh++;
        (r.crossScript || []).forEach(n => cross.add(f + ':' + n));
        if(r.disabled) stuck++;
        if(/Failed to fetch|HTTP \d|AuthRetryable/.test(r.msg||'')) raw++;
      }
    }
    console.log(`pages ${files.length}, scenarios ${calls}, harness errors ${errs}, button left disabled ${stuck}, unhandled rejections ${unh}, raw library text shown ${raw}`);
    if(cross.size) console.log('  not counted, defined in another script block the harness does not load: ' + [...cross].join(', '));
    process.exit(stuck || raw || errs || unh ? 1 : 0);
  }
  const rows = await page(arg || 'uk.html');
  for(const r of rows) console.log([r.action.padEnd(22), r.shape.padEnd(8), (r.error ? 'ERROR '+r.error : (r.disabled ? 'DISABLED' : 'enabled ')), (r.unhandled ? 'UNHANDLED' : '         '), JSON.stringify(r.msg||'')].join(' | '));
})();
