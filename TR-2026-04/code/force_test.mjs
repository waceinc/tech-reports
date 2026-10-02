// TR-2026-04 judgment 2 — input-forcing test runner (engine only, no plant model).
// usage: node force_test.mjs --engine-host <engine host module> --program <program.ldprog.json> --tests <tests.json> --out <result.json>
// The engine host module must export loadEngine(path) -> { scan(I) -> { Q } } (10 ms scan).
// Test file format (written from the specification only):
// { "cell": "...", "defaults": {tag: value}, "tests": [ { "id", "purpose", "requirements": [..], "scans": N,
//   "initial": {tag: value}, "steps": [ { "at": s, "set": {tag: value}, "ramp": {tag: perScan} } ],
//   "expect": [ { "tag", "value", "from", "to" } ] } ] }
// Inputs hold their value until changed. "ramp" adds perScan to an integer input on every scan from "at"
// (32-bit unsigned wrap; perScan 0 stops it). Expectation: output tag equals value on every scan from..to (1-based, inclusive).
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const arg = (name) => { const i = process.argv.indexOf(name); if (i < 0) throw Error('missing ' + name); return process.argv[i + 1]; };
const { loadEngine } = await import(pathToFileURL(arg('--engine-host')).href);
const program = arg('--program');
const spec = JSON.parse(readFileSync(arg('--tests'), 'utf8'));
const inputs = JSON.parse(readFileSync(program, 'utf8')).tags.filter((t) => t.address.startsWith('%I'));

const runOne = (test) => {
  const engine = loadEngine(program);
  const image = {};
  for (const t of inputs) image[t.symbol] = t.type === 'BOOL' ? false : 0;
  for (const src of [spec.defaults || {}, test.initial || {}]) for (const [k, v] of Object.entries(src)) if (k in image) image[k] = v;
  const ramps = {};
  const steps = new Map();
  for (const s of test.steps || []) steps.set(s.at, [...(steps.get(s.at) || []), s]);
  const history = [];
  for (let scan = 1; scan <= test.scans; scan += 1) {
    for (const s of steps.get(scan) || []) {
      for (const [k, v] of Object.entries(s.set || {})) if (k in image) image[k] = v;
      for (const [k, v] of Object.entries(s.ramp || {})) if (k in image) ramps[k] = v;
    }
    for (const [k, v] of Object.entries(ramps)) if (v) image[k] = (image[k] + v) >>> 0;
    history.push(engine.scan({ ...image }).Q);
  }
  const failures = [];
  for (const e of test.expect) {
    for (let s = e.from; s <= e.to; s += 1) {
      const q = history[s - 1];
      if (!q || !(e.tag in q)) { failures.push({ ...e, scan: s, actual: 'missing' }); break; }
      if (q[e.tag] !== e.value) { failures.push({ ...e, scan: s, actual: q[e.tag] }); break; }
    }
  }
  return { id: test.id, status: failures.length ? '[FAIL]' : '[PASS]', failures };
};

const results = [];
for (const test of spec.tests) {
  try { results.push(runOne(test)); } catch (error) { results.push({ id: test.id, status: '[FAIL]', error: String(error).slice(0, 300) }); }
}
const passed = results.filter((r) => r.status === '[PASS]').length;
const out = { program, tests: results.length, passed, status: passed === results.length ? '[PASS]' : '[FAIL]', results };
writeFileSync(arg('--out'), JSON.stringify(out, null, 1) + '\n');
console.log(out.status, 'passed', passed, '/', results.length);
