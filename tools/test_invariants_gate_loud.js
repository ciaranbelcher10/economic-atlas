#!/usr/bin/env node
/* v1.9.52: invariants_gate.js fails loudly. Runs the gate against broken copies of the tree and of
 * node_modules (all built with symlinks in a temp folder, so the real tree is never touched) and
 * checks each failure gives a non-zero exit and says what went wrong.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_invariants_gate_loud.js  (about a minute) */
const fs = require("fs"), path = require("path"), os = require("os"), { spawnSync } = require("child_process");
const ROOT = path.resolve(__dirname, ".."), NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0];
const GATE = path.join(ROOT, "tools", "invariants_gate.js"), PAGE = "uk.html";
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "gate-loud-"));
function tree(name, edit){            // a copy of the repo top level, symlinked except the files edited
  const d = path.join(tmp, name); fs.mkdirSync(d);
  for (const f of fs.readdirSync(ROOT)) if (f !== ".git") fs.symlinkSync(path.join(ROOT, f), path.join(d, f));
  edit && edit(d); return d;
}
function mods(name, edit){            // a copy of node_modules, symlinked except what is edited
  const d = path.join(tmp, name, "node_modules"); fs.mkdirSync(d, { recursive: true });
  for (const f of fs.readdirSync(NM)) fs.symlinkSync(path.join(NM, f), path.join(d, f));
  edit && edit(d); return d;
}
const replace = (d, f, text) => { fs.unlinkSync(path.join(d, f)); fs.writeFileSync(path.join(d, f), text); };
function gate(root, nm){
  const r = spawnSync("node", [GATE, "--page", PAGE], { env: { ...process.env, ATLAS_ROOT: root, NODE_PATH: nm }, encoding: "utf8", timeout: 120000 });
  return { code: r.status, out: (r.stdout || "") + (r.stderr || "") };
}
const page = fs.readFileSync(path.join(ROOT, PAGE), "utf8");
const inject = js => page.replace("</body>", "<script>" + js + "</script></body>");

let r = gate(ROOT, NM);
ok(r.code === 0, "the real tree passes: " + r.out.slice(-200));

r = gate(ROOT, mods("nod3", d => fs.unlinkSync(path.join(d, "d3"))));
ok(r.code === 2 && /library files missing .*d3\/dist\/d3\.min\.js/.test(r.out), "a missing library file stops the gate with exit 2 and names it: " + r.out.slice(-200));

r = gate(ROOT, mods("emptyd3", d => { fs.unlinkSync(path.join(d, "d3")); fs.mkdirSync(path.join(d, "d3", "dist"), { recursive: true }); fs.writeFileSync(path.join(d, "d3", "dist", "d3.min.js"), "/* broken */"); }));
ok(r.code === 1 && /d3\.min\.js is on the page but d3 never loaded/.test(r.out), "a library that never defines its global fails: " + r.out.slice(-200));

r = gate(tree("reject", d => replace(d, PAGE, inject("Promise.reject(new Error('boom from page'));"))), NM);
ok(r.code === 1 && /unhandled promise rejection: boom from page/.test(r.out), "a rejected promise in a page fails and is named: " + r.out.slice(-200));

r = gate(tree("unserved", d => replace(d, PAGE, page.replace("</head>", "<script src='https://cdn.example/plotly-2.35.2.min.js'></script></head>"))), NM);
ok(r.code === 1 && /asks for a library this gate does not serve .*plotly-2\.35\.2\.min\.js/.test(r.out), "a library the gate does not serve fails: " + r.out.slice(-200));

r = gate(tree("crash", d => fs.unlinkSync(path.join(d, "data-uk.json"))), NM);
ok(r.code === 2 && /invariants_gate: crashed/.test(r.out), "a crash inside the gate exits 2, not 0: " + r.out.slice(-200));

fs.rmSync(tmp, { recursive: true, force: true });
console.log(`test_invariants_gate_loud: ${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
