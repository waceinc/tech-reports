// TR-2026-03 변종 적용 + 정적 컴파일 검사(사전 등록 v0.3 고정 입력). 스캔·시나리오 실행은 하지 않는다.
// 변환 = 변종 목록의 cells 칸(같은 렁·같은 태그·같은 모드 접점 전부)을 {k:"hwire"} 로 바꾼다.
// 실행: node TR-03_변종적용_컴파일검사.mjs TR-03_변종목록_v1.json <출력 폴더>  — 출력 폴더는 업무 폴더 밖에 둔다.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
const { loadEngine } = await import('<repos>/plc-twin-lab/bridge/engine.mjs');
const list = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const dir = process.argv[3]; mkdirSync(dir, { recursive: true });
const src = {};
const res = { pass: 0, fail: [], all: 0 };
for (const v of list.variants) {
  if (!v.sampled) continue;
  res.all++;
  src[v.cell] ??= execFileSync('git', ['-C', '<repos>/plc-twin-lab', 'show', `${list.source.commit}:ladders/${v.cell}/correct/program.ldprog.json`]).toString();
  const p = JSON.parse(src[v.cell]);
  for (const [r, c] of v.cells) { const cell = p.rungs[v.rung].grid[r][c]; if (cell.k !== 'contact' || cell.tag !== v.tag) throw Error('mismatch ' + v.id); p.rungs[v.rung].grid[r][c] = { k: 'hwire' }; }
  const f = `${dir}/${v.id}.ldprog.json`; writeFileSync(f, JSON.stringify(p));
  try { const e = loadEngine(f); res.pass++; } catch (err) { res.fail.push([v.id, String(err).slice(0, 200)]); }
}
console.log(JSON.stringify(res));
