#!/usr/bin/env python3
"""TR-2026-03 리드 독립 검산 — 분석 스크립트(TR-03_분석.py)와 그 해석 코드를 쓰지 않고, 사전 등록 §5 정의만으로
각 변종의 「드러남(4단계)」 여부와 P1 을 summary.json 에서 다시 센다.

정의(사전 등록 §5): 「원본과 같다」 = 사건 이름별 개수와 최종 상태가 같다. 4단계 = 공장 사건이 다르거나(a) 제어 판정만 다름(b).
- 원본 = 같은 셀·같은 시나리오 키의 원본 기준 실행 반복 1.
- 사건 = summary.events + summary.production_events 의 이름별 개수. 최종 상태 = classification · routes.
- 판정 = status · judgments.
- 종료 코드가 0 이 아닌 변종 실행은 드러남으로 세지 않고 오류로 따로 센다. 그 변종에 정상 실행에서 드러난 시나리오가 없으면 보류.
P1 과 P2 의 1단계 비율은 재스캔이 필요해 이 검산 범위 밖이다(P1 만 다시 센다).

사용: python3 TR-03_리드독립검산.py <결과 폴더>   → 표준 출력(결정적)
"""
import collections, json, sys
from pathlib import Path

root = Path(sys.argv[1])
rows = [json.loads(l) for l in (root / 'ledger.jsonl').read_text().splitlines() if l.strip()]


def summ(name):
    return json.loads((root / name / 'summary.json').read_text())


def names(evs):
    return sorted(collections.Counter(e['name'] if isinstance(e, dict) else str(e) for e in evs).items())


def sig(s):
    return dict(events=names(s.get('events', []) + s.get('production_events', [])),
                final=json.dumps([s.get('classification'), s.get('routes')], sort_keys=True),
                verdict=json.dumps([s.get('status'), s.get('judgments')], sort_keys=True))


base = {}
for r in rows:
    if r['kind'] == 'baseline' and r['rep'] == 1:
        base[(r['cell'], r['key'])] = sig(summ(r['name']))

var = collections.defaultdict(lambda: dict(cell=None, group=None, detected=[], errors=0, ok=0))
for r in rows:
    if r['kind'] != 'variant':
        continue
    v = var[r['variant_id']]
    v['cell'], v['group'] = r['cell'], r['group']
    if str(r['rc']) != '0':
        v['errors'] += 1
        continue
    b = base.get((r['cell'], r['key']))
    if b is None:
        v['errors'] += 1
        continue
    s = sig(summ(r['name']))
    v['ok'] += 1
    if s['events'] != b['events'] or s['final'] != b['final']:
        v['detected'].append(('4a', r['key']))
    elif s['verdict'] != b['verdict']:
        v['detected'].append(('4b', r['key']))

state = {}
for vid, v in var.items():
    if v['detected']:
        state[vid] = '4a' if any(k == '4a' for k, _ in v['detected']) else '4b'
    elif v['errors']:
        state[vid] = '보류'
    else:
        state[vid] = '미검출'

print('변종 수', len(var), '· 상태', dict(sorted(collections.Counter(state.values()).items())))
print('오류 실행 있는 변종', sorted(k for k, v in var.items() if v['errors']))
by = collections.defaultdict(collections.Counter)
for vid, v in var.items():
    by[(v['cell'], v['group'])][state[vid]] += 1
for k in sorted(by):
    print(k, dict(sorted(by[k].items())))


def rate(groups):
    c = collections.Counter()
    for vid, v in var.items():
        if v['group'] in groups and state[vid] != '보류':
            c['n'] += 1
            c['und'] += state[vid] == '미검출'
    return c['und'], c['n']


u1, n1 = rate({'복귀', '포장 핸드셰이크'})
u2, n2 = rate({'안전'})
d = (u1 / n1 - u2 / n2) * 100
print(f'P1: 복귀·포장 핸드셰이크 미검출 {u1}/{n1} = {u1/n1*100:.1f}% · 안전 미검출 {u2}/{n2} = {u2/n2*100:.1f}% · 차이 {d:.1f} %p → '
      + ('[맞음]' if d >= 20 else '[틀림]'))
