// TR-2026-03: rebuild the run versions of the 500 sampled variant ladders from released files only and check their SHA-256.
// Inputs: ladders/<cell>__correct.program.ldprog.json (public versions), variants/TR-03_변종목록_v1.json, variants/ladders-sha256.json.
// Steps, as in the fixed generator (TR-03_변종적용_컴파일검사.mjs), without the private repository:
//   1. run version of each correct ladder = public version with the `marker` line re-inserted as line 4; its SHA-256 must
//      equal the pre-registered hash;
//   2. for each sampled variant: JSON.parse, replace every listed contact cell with {"k":"hwire"}, JSON.stringify;
//   3. SHA-256 of that text must equal ladders-sha256.json[<id>].program (the table the official run recorded).
// Nothing is written. Usage: node rebuild_variants.mjs <bundle dir> [--selftest]
// --selftest moves one listed cell by one column for one variant and expects exactly that variant to fail (negative control).
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const dir = process.argv[2];
const selftest = process.argv.includes('--selftest');
const MARKER = '  "marker": "CONFIDENTIAL — WACE trade secret",\n';
const PREREG = {
  'cell-a': '5058bd0b97644e66c0310a540a0403931bf6bd8195445576430d6dd1cabf8ef1',
  'cell-b': '05999e23b90b265f9907e0cd05f5469eccec6195e43326310bb9b491bd4ed0b1',
  'cell-b-pack': '5a4cc91db8f6e53197e613ff87426bc94438a0b7c3226946417b2aa407b53fb1',
};
const sha = (s) => createHash('sha256').update(s).digest('hex');
const list = JSON.parse(readFileSync(`${dir}/variants/TR-03_변종목록_v1.json`, 'utf8'));
const table = JSON.parse(readFileSync(`${dir}/variants/ladders-sha256.json`, 'utf8'));
const run = {};
for (const cell of Object.keys(PREREG)) {
  const lines = readFileSync(`${dir}/ladders/${cell}__correct.program.ldprog.json`, 'utf8').split(/(?<=\n)/);
  const text = lines.slice(0, 3).join('') + MARKER + lines.slice(3).join('');
  if (sha(text) !== PREREG[cell]) throw Error(`run version of ${cell} does not match the pre-registered hash`);
  run[cell] = text;
}
let ok = 0;
const bad = [];
const sampled = list.variants.filter((v) => v.sampled);
sampled.forEach((v, i) => {
  const p = JSON.parse(run[v.cell]);
  const cells = selftest && i === 0 ? v.cells.map(([r, c]) => [r, c + 1]) : v.cells;
  for (const [r, c] of cells) p.rungs[v.rung].grid[r][c] = { k: 'hwire' };
  if (sha(JSON.stringify(p)) === table[v.id]?.program) ok++;
  else bad.push(v.id);
});
console.log(JSON.stringify({ correct_ladders_match_prereg: 3, sampled: sampled.length, match: ok, mismatch: bad }));
if (selftest) {
  const pass = bad.length === 1 && bad[0] === sampled[0].id;
  console.log(pass ? '[PASS] selftest: the altered variant was caught' : '[FAIL] selftest');
  process.exit(pass ? 0 : 1);
}
process.exit(bad.length || ok !== 500 ? 1 : 0);
