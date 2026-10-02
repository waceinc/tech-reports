#!/usr/bin/env python3
"""TR-2026-04 분석 — 사전 등록 v0.4 §8 지표를 판정 기록(verdict.json)과 생성 기록(unit.json)에서 센다.

작성 2026-10-02 [작업자: 방동걸]. 결과(summary.json 의 116 줄 요약)를 본 뒤에 쓴 스크립트다 — 지표 정의는 §8 그대로이고,
결과를 보고 바꾼 정의는 없다. 사전 등록에 없는 보조 값(정확 이항 상한)은 [보조] 로 표시한다.

지표(§8)
 1. ③만 [FAIL] = ①② 통과 & ③ [FAIL] / ①② 통과. 전체·과제별. 분모 20 이상이면 과제 단위 재표본 95 % 구간(1만 회, 시드 0).
 2. 원인 분류(§6-3) — ③만 [FAIL] 래더가 있을 때만. 0 개면 분류하지 않는다.
 3. 생성기·과제 크기·수정 횟수별 기술 통계 · marker 사용 비율.
판정선(§9): ③만 [FAIL] 10 % 이상 & 원인 절반 이상이 타이밍·물리 전제 → [맞음], 아니면 [틀림].

사용: python3 TR-04_분석.py <판정 결과 폴더> <생성 작업 폴더>   → 표준 출력(결정적)
"""
import collections, json, random, sys
from pathlib import Path

res, work = Path(sys.argv[1]), Path(sys.argv[2])
V = {p.parent.name: json.loads(p.read_text()) for p in sorted(res.glob('T*-G*-r*/verdict.json'))}
U = {p.parent.name: json.loads(p.read_text()) for p in sorted(work.glob('T*-G*-r*/unit.json'))}
gen_dirs = sorted(p.name for p in work.glob('T*-G*-r*') if p.is_dir())

print('생성 폴더', len(gen_dirs), '· unit.json', len(U), '· verdict.json', len(V))
print('unit.json 없는 생성 폴더', [d for d in gen_dirs if d not in U])
print('판정 없는 unit', [u for u in U if u not in V])


def p12(v):
    return v['j1'] == '[PASS]' and v['j2'] == '[PASS]'


task = lambda u: u.split('-')[0]
gen = lambda u: u.split('-')[1]

# 1. ③만 [FAIL]
den = [u for u, v in V.items() if p12(v)]
num = [u for u in den if V[u]['j3'] == '[FAIL]']
not_run3 = [u for u in den if V[u]['j3'] not in ('[PASS]', '[FAIL]')]
print(f'\n[지표1] ③만 [FAIL] = {len(num)}/{len(den)} = {len(num)/len(den)*100:.1f} %' + (f' · ③ 미판정 {not_run3}' if not_run3 else ''))
by_task = collections.defaultdict(lambda: [0, 0])
for u in den:
    by_task[task(u)][1] += 1
    by_task[task(u)][0] += V[u]['j3'] == '[FAIL]'
print('과제별 (분자/분모):', ' '.join(f'{t} {a}/{b}' for t, (a, b) in sorted(by_task.items())))
if len(den) >= 20:
    tasks = sorted(by_task)
    rng = random.Random(0)
    stats = []
    for _ in range(10000):
        pick = [rng.choice(tasks) for _ in tasks]
        a = sum(by_task[t][0] for t in pick); b = sum(by_task[t][1] for t in pick)
        stats.append(a / b if b else 0.0)
    stats.sort()
    print(f'과제 단위 재표본 95 % 구간: {stats[249]*100:.1f} % ~ {stats[9749]*100:.1f} %')
# [보조] 사전 등록에 없는 값: 래더를 독립 표본으로 볼 때 0 건의 정확 이항 95 % 상한(단측 = 1 - 0.05^(1/n))
if not num:
    print(f'[보조] 0/{len(den)} 의 정확 이항 단측 95 % 상한 = {(1 - 0.05 ** (1/len(den)))*100:.1f} % (래더 독립 가정 — 같은 과제 반복은 독립이 아니다)')

# 2. 원인 분류
print('\n[지표2] 원인 분류:', '대상 없음(③만 [FAIL] 0 개) — 분류자를 띄우지 않는다' if not num else f'대상 {len(num)} 개 — 분류자 2 필요')

# 판정선
rate = len(num) / len(den)
print(f'\n[판정선] ③만 [FAIL] {rate*100:.1f} % (기준 10 % 이상) → ' + ('[맞음] 조건 1 충족' if rate >= 0.10 else '[틀림]'))

# 3. 기술 통계
print('\n[지표3] 생성기별 단계 결과')
for g in ('G1', 'G2', 'G3'):
    us = [u for u in V if gen(u) == g]
    c = collections.Counter((V[u]['j1'], V[u]['j2'], V[u]['j3']) for u in us)
    print(f' {g} 판정 {len(us)} · ①② 통과 {sum(p12(V[u]) for u in us)} · ' + ' · '.join(f'①{a[1:-1]} ②{b[1:-1]} ③{c3[1:-1]}={n}' for (a, b, c3), n in sorted(c.items())))
print(' 셀별 ①② 통과:', dict(sorted(collections.Counter((V[u]['cell'], p12(V[u])) for u in V).items())))

print('\n 수정 횟수(repairs_used) 분포 — 생성기별')
for g in ('G1', 'G2', 'G3'):
    print(f'  {g}', dict(sorted(collections.Counter(U[u].get('repairs_used') for u in U if gen(u) == g).items())),
          '· 컴파일 성공', sum(bool(U[u].get('compile_ok')) for u in U if gen(u) == g), '/', sum(gen(u) == g for u in U))
print('\n 수정 횟수별 ①② 통과율')
for k in sorted({U[u].get('repairs_used') for u in U}, key=str):
    us = [u for u in U if U[u].get('repairs_used') == k and u in V]
    print(f'  수정 {k}: {sum(p12(V[u]) for u in us)}/{len(us)}')

# marker 사용(§6-4): 조립 기록(assemble-*.json)의 generator_wrote_marker — 판정기가 넣은 marker 는 세지 않는다
mk = collections.Counter()
for d in gen_dirs:
    a = sorted((work / d).glob('assemble-*.json'))
    rec = json.loads(a[-1].read_text()) if a else None
    mk[(gen(d), '조립 기록 없음' if rec is None else rec.get('generator_wrote_marker', '조립 실패(산출 파일 없음)'))] += 1
print('\n 생성기가 marker 를 쓴 수(조립 기록 기준):', dict(sorted(mk.items(), key=str)))

# 과제 크기 = 정답 블록 사양서 길이 대신 TASK.md 바이트(과제 묶음과 같은 파일)
size = {}
for u in U:
    p = work / u / 'TASK.md'
    if p.exists():
        size.setdefault(task(u), p.stat().st_size)
print('\n 과제별 ①② 통과(G1·G2·G3 합) · TASK.md 바이트')
for t in sorted({task(u) for u in V}):
    us = [u for u in V if task(u) == t]
    print(f'  {t} {sum(p12(V[u]) for u in us)}/{len(us)} · {size.get(t)}')
