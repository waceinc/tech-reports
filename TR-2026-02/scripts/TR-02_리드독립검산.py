#!/usr/bin/env python3
"""TR-2026-02 리드 독립 검산 — 분석 스크립트(TR-02_분석.py)를 쓰지 않고 trace·summary 를 직접 읽어 P1~P4 와
펄스·기준 실행 요약 판정 [FAIL] 의 내역을 다시 센다. 반복 1 만 본다(반복 2 는 해시 동일 확인됨).

사용: python3 TR-02_리드독립검산.py <결과 폴더>  → 표준 출력(결정적)
"""
import collections, json, sys
from pathlib import Path

root = Path(sys.argv[1])
led = {r['name']: r for r in map(json.loads, (root / 'ledger.jsonl').read_text().splitlines())}


def ticks(name):
    return [x for x in map(json.loads, (root / name / 'trace.jsonl').read_text().splitlines()) if x['type'] == 'tick']


def summary(name):
    return json.loads((root / name / 'summary.json').read_text())


def qchanges(t):
    out, prev = [], None
    for x in t:
        for k, v in sorted(x['Q'].items()):
            if prev is not None and prev.get(k) != v:
                out.append((x['tick'], k, v))
        prev = x['Q']
    return out


def one(pred):
    ns = sorted(n for n in led if pred(n, led[n]))
    assert len(ns) == 1, ns
    return ns[0]


print('# P1·P2 — 공장 연결 반복 1')
for v in ['correct', 'late-reverse', 'swapped-sensors']:
    h = one(lambda n, r: r['kind'] == 'plant' and r['variant'] == v and r['mode'] == 'history' and r['rep'] == 1)
    b = one(lambda n, r: r['kind'] == 'plant' and r['variant'] == v and r['mode'] == 'boundary' and r['rep'] == 1)
    sh, sb = summary(h), summary(b)
    ev = lambda s: sorted(collections.Counter(e['name'] if isinstance(e, dict) else e for e in s['events']).items())
    ch, cb = qchanges(ticks(h)), qchanges(ticks(b))
    diffs = sorted({tb - th for (th, _, _), (tb, _, _) in zip(ch, cb)})
    print(f"{v}: 판정 {sh['status']}/{sb['status']} · 사건 같음 {ev(sh) == ev(sb)} · Q 변화 {len(ch)}/{len(cb)} · "
          f"순서 같음 {[c[1:] for c in ch] == [c[1:] for c in cb]} · 틱 차이 {diffs}")

print('\n# P3·P4 — 짧은 펄스 검출 수(위상 10 점 중), 폭 5·15·25·35·45 ms')
base = {m: ticks(one(lambda n, r, m=m: r['kind'] == 'baseline' and r['mode'] == m and r['rep'] == 1)) for m in ['history', 'boundary']}
det = collections.Counter()
detected_runs = set()
for n, r in led.items():
    if r['kind'] != 'pulse' or r['rep'] != 1:
        continue
    tag, _, _, w = r['pulse'].split(':')
    t, bq = ticks(n), base[r['mode']]
    hit = any(t[i]['Q'] != bq[i]['Q'] for i in range(100, 141))
    det[(tag, r['mode'], int(w))] += hit
    if hit:
        detected_runs.add((r['pulse'], r['mode']))
for tag in ['A.PB.stop_nc', 'A.PB.estop_nc', 'A.Sen.left', 'A.Sen.right']:
    for m in ['boundary', 'history']:
        print(f"{tag} {m}: {[det[(tag, m, w)] for w in [5, 15, 25, 35, 45]]}")

print('\n# 기록만 — 펄스·기준 실행 요약 판정 내역(반복 1·2 전부)')
rows = collections.Counter()
for n, r in led.items():
    if r['kind'] == 'plant':
        continue
    s = summary(n)
    rounds = s['probes'].get('Rounds')
    hit = (r['pulse'], r['mode']) in detected_runs
    rows[(r['kind'], s['status'], rounds, '검출' if hit else '미검출', len(s['events']))] += 1
for k, c in sorted(rows.items(), key=lambda x: (x[0][0], str(x[0]))):
    print(f"{k[0]} · 판정 {k[1]} · 왕복 {k[2]} · 펄스 {k[3]} · 공장 사건 {k[4]} → {c} 실행")
print(f"합계 {sum(rows.values())}")
