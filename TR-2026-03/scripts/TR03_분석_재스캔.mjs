// TR-2026-03 분석 보조 — 원본 래더를 원본 실행의 스캔별 입력으로 다시 스캔하고, 스캔 끝의 조건 태그 값을 돌려준다(사전 등록 §5 1단계).
// 브리지 엔진 호스트(bridge/engine.mjs)의 loadEngine 을 그대로 불러 쓴다(고치지 않는다). 파일을 쓰지 않는다.
// 사용: node TR03_분석_재스캔.mjs <engine.mjs 경로> <program.ldprog.json 경로> <조건 태그 JSON 배열>
// 표준입력 한 줄 = {"inputs":[I, ...]} (한 틱의 스캔 입력). 표준출력 한 줄 = {"scans":[{"scan","digest","Q","v","img_q_ok"}]}
//   v = 조건 태그 순서대로 스캔 끝 값 '0'/'1' 문자열, img_q_ok = 메모리 이미지에서 읽은 BOOL 출력이 엔진 q() 와 같은가(읽는 위치 자가검증).
import { pathToFileURL } from 'node:url';
import { createInterface } from 'node:readline';

const [enginePath, ladderPath, tagsJson] = process.argv.slice(2);
const { loadEngine } = await import(pathToFileURL(enginePath).href);
const engine = loadEngine(ladderPath);
const entries = new Map(engine.description().symbols);
const tags = JSON.parse(tagsJson);
for (const t of tags) {
  const e = entries.get(t);
  if (!e || e.type !== 'BOOL') throw Error('조건 태그가 BOOL 이 아님: ' + t);
}
const boolOutputs = [...entries].filter(([s, e]) => e.type === 'BOOL' && s in engine.q()).map(([s]) => s);
const bit = (img, t) => { const e = entries.get(t); return (img[e.byteOffset] >> (e.bit & 7)) & 1; };

process.stdout.write(JSON.stringify({ ok: true, tags: tags.length, bool_outputs: boolOutputs.length }) + '\n');
for await (const line of createInterface({ input: process.stdin })) {
  const request = JSON.parse(line);
  if (request.cmd === 'quit') break;
  const scans = request.inputs.map((I) => {
    const r = engine.scan(I, false);
    const img = engine.cycle.snapshot().data;
    const imgQok = boolOutputs.every((s) => (bit(img, s) === 1) === r.Q[s]);
    return { scan: r.scan, digest: r.digest, Q: r.Q, v: tags.map((t) => bit(img, t)).join(''), img_q_ok: imgQok };
  });
  process.stdout.write(JSON.stringify({ scans }) + '\n');
}
