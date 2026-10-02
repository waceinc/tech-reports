// TR-2026-04 judgment 1 — static check.
// usage: node static_check.mjs --engine-host <engine host module> --program <program.ldprog.json> --io <task io.json> --patterns <patterns.json> --out <result.json>
// io.json = { "io": [ { "tag", "address", "type", "direction": "in"|"out", "use": "required"|"declared_only" } ] }  (the specification I/O table)
// Checks: S1 compile (engine loads the program) · S2 double coil · S3 every specification I/O tag declared
// with the same address and type, every required input read and every required output written · S4 forbidden patterns (patterns.json).
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const arg = (name) => { const i = process.argv.indexOf(name); if (i < 0) throw Error('missing ' + name); return process.argv[i + 1]; };
const { loadEngine } = await import(pathToFileURL(arg('--engine-host')).href);
const path = arg('--program');
const io = JSON.parse(readFileSync(arg('--io'), 'utf8')).io;
const patterns = JSON.parse(readFileSync(arg('--patterns'), 'utf8')).rules.map((r) => r.id);
const checks = [];
const add = (id, ok, detail) => checks.push({ id, status: ok ? '[PASS]' : '[FAIL]', ...(detail ? { detail } : {}) });

let prog = null;
try { prog = JSON.parse(readFileSync(path, 'utf8')); } catch (e) { add('S1', false, 'json: ' + String(e).slice(0, 200)); }
if (prog) {
  try { loadEngine(path); add('S1', true); } catch (e) { add('S1', false, String(e).slice(0, 400)); }
  const cells = [];
  (prog.rungs || []).forEach((r, i) => (r.grid || []).forEach((row) => row.forEach((c) => cells.push({ rung: i, ...c }))));
  const coilCount = {};
  for (const c of cells) if (c.k === 'coil' && c.mode === 'OUT') coilCount[c.tag] = (coilCount[c.tag] || 0) + 1;
  const doubled = Object.entries(coilCount).filter(([, n]) => n > 1).map(([t]) => t);
  add('S2', doubled.length === 0, doubled.length ? { doubled } : null);
  const declared = new Map((prog.tags || []).map((t) => [t.symbol, t]));
  const read = new Set(); const written = new Set();
  for (const c of cells) {
    if (c.k === 'contact') read.add(c.tag);
    if (c.k === 'coil') written.add(c.tag);
    if (c.k === 'box') { Object.values(c.inputs || {}).forEach((v) => read.add(v)); Object.values(c.outputs || {}).forEach((v) => written.add(v)); }
  }
  const s3 = [];
  for (const t of io) {
    const d = declared.get(t.tag);
    if (!d || d.address !== t.address || d.type !== t.type) s3.push({ tag: t.tag, problem: 'not declared as specified' });
    else if (t.use !== 'declared_only' && t.direction === 'in' && !read.has(t.tag)) s3.push({ tag: t.tag, problem: 'input never read' });
    else if (t.use !== 'declared_only' && t.direction === 'out' && !written.has(t.tag)) s3.push({ tag: t.tag, problem: 'output never written' });
  }
  add('S3', s3.length === 0, s3.length ? s3 : null);
  const specAddr = new Set(io.map((t) => t.address));
  const byAddr = new Map((prog.tags || []).map((t) => [t.symbol, t.address]));
  const hits = [];
  if (patterns.includes('F1')) for (const t of written) if ((byAddr.get(t) || '').startsWith('%I')) hits.push({ rule: 'F1', tag: t });
  if (patterns.includes('F2')) for (const t of prog.tags || []) if (/^%[IQ]/.test(t.address) && !specAddr.has(t.address)) hits.push({ rule: 'F2', tag: t.symbol, address: t.address });
  if (patterns.includes('F3')) (prog.rungs || []).forEach((r, i) => {
    const flat = (r.grid || []).flat();
    const header = flat.length > 0 && flat.every((c) => c.k === 'hwire' || c.k === 'empty');
    const acts = flat.some((c) => c.k === 'coil' || (c.k === 'box' && Object.keys(c.outputs || {}).length > 0));
    if (!header && !acts) hits.push({ rule: 'F3', rung: i });
  });
  if (patterns.includes('F4')) for (const c of cells) if (c.k === 'coil' && (c.mode === 'SET' || c.mode === 'RESET') && (byAddr.get(c.tag) || '').startsWith('%Q')) hits.push({ rule: 'F4', tag: c.tag, rung: c.rung });
  add('S4', hits.length === 0, hits.length ? hits.slice(0, 50) : null);
}
const status = checks.length && checks.every((c) => c.status === '[PASS]') ? '[PASS]' : '[FAIL]';
writeFileSync(arg('--out'), JSON.stringify({ program: path, status, checks }, null, 1) + '\n');
console.log(status, checks.map((c) => c.id + c.status).join(' '));
