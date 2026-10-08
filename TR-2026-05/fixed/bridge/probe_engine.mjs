// TR-2026-05 교정 측정기(I11)용 탐침 호스트 — 새로 씀. engine.mjs 의 loadEngine 을 그대로 쓰고(래더 · 엔진 동작 같음),
// 스캔마다 스냅숏 메모리에서 이름 준 내부 태그(Arrive · Chute · Out 등)를 읽기만 한다. 래더의 Q 는 돌려주지만 측정기는 버린다.
// 입력(표준 입력, JSON 한 줄씩): 첫 줄 {"read":[태그…]}, 그 뒤 스캔마다 완전한 I 이미지 한 줄. 출력: 스캔마다 [scan, 값…] 한 줄.
// 확인: 스캔마다 탐침(probes) 가운데 읽기 목록에도 있는 태그는 두 경로의 값이 같아야 한다(다르면 멈춤).
import { createInterface } from 'node:readline';
import { loadEngine } from './engine.mjs';
import { readBool, readNumAt, numTypeOf } from '../vendor/plc-simulator/packages/runtime/dist/index.js';
const engine = loadEngine(process.argv[2]);
const d = engine.description(); const entries = new Map(d.symbols); const tags = new Map(d.program.tags.map(t => [t.symbol, t]));
let names = null;
for await (const line of createInterface({ input: process.stdin })) {
  const msg = JSON.parse(line);
  if (!names) {
    names = msg.read; for (const n of names) if (!tags.has(n)) throw Error('unknown tag ' + n);
    process.stdout.write(JSON.stringify({ ok: true, read: names }) + '\n'); continue;
  }
  const r = engine.scan(msg);
  const snap = engine.cycle.snapshot(); const dv = new DataView(snap.data.buffer, snap.data.byteOffset, snap.data.byteLength);
  const value = n => { const t = tags.get(n), e = entries.get(n); return t.type === 'BOOL' ? readBool(dv, e.byteOffset, e.bit) : readNumAt(dv, e.byteOffset, numTypeOf(t.type)); };
  const values = names.map(value);
  names.forEach((n, i) => { if (n in r.probes && r.probes[n] !== values[i]) throw Error(`probe mismatch ${n} ${r.probes[n]} ${values[i]}`); });
  process.stdout.write(JSON.stringify([r.scan, ...values]) + '\n');
}
