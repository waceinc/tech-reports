"""TR-03_분석.py 의 집계 부품 — 변종 4단계 분류(§5) · 지표 1~3(§6) · 예측 P1·P2(§7).

입력은 실행별 비교 결과(TR03_분석_읽기.compare)와 원본 재스캔 결과뿐이다. 해석 번호(I-n)는 TR-03_분석_고정기록.md.
"""
from collections import Counter

from TR03_분석_읽기 import blocked

GROUPS = ['안전', '밀기 순서', '출력', '알람', '복귀', '포장 핸드셰이크']
CELLS = ['cell-a', 'cell-b', 'cell-b-pack']
STAGES = ['1', '2', '3', '4a', '4b', '보류']
REVEALED = ('4a', '4b')
# §4: 0.45 포함 묶음(사전 등록 그대로 = 주 결과)과 제외 묶음을 나란히
SETS = {'full': lambda key: True, 'no045': lambda key: key != 'flow045'}


def classify(v, scen_keys, rescans, runs, keep):
    """변종 1 개의 단계. scen_keys = 그 셀의 유효 시나리오(§4 순서), rescans[key] = 재스캔 결과, runs[key] = 실행 결과 또는 누락 사유.
    I-1: 1단계는 원본 재스캔만으로 정한다. I-4: 누락 실행이 있으면 드러남이 확정된 경우 말고는 보류."""
    keys = [k for k in scen_keys if keep(k)]
    active, unknown = {}, []
    for k in keys:
        rs = rescans.get(k)
        if rs is None or not rs['ok']:
            unknown.append(k)
        else:
            active[k] = blocked(rs['values'][v['tag']], v['mode'])
    levels = {k: runs[k]['level'] for k in keys if isinstance(runs.get(k), dict) and 'level' in runs[k]}
    missing = {k: (runs.get(k) if isinstance(runs.get(k), str) else '기록 없음') for k in keys if k not in levels}
    revealed = [k for k in keys if levels.get(k) in REVEALED]
    is_active = any(n > 0 for n in active.values())

    def by_outcome():
        if revealed:
            return '4a' if any(levels[k] == '4a' for k in revealed) else '4b'
        if missing or unknown:
            return '보류'
        return '3' if any(lv == '3' for lv in levels.values()) else '2'
    anomaly = []
    if not keys:
        stage = alt = '보류'
    elif not is_active and not unknown:
        stage = '1'
        anomaly = [k for k, lv in levels.items() if lv != '2']  # I-1: 미활성인데 출력이 달라진 실행(스캔 중간 값 한계)
        alt = by_outcome() if anomaly else '1'
    else:
        stage = alt = by_outcome()
    shown = revealed if stage in REVEALED else []
    return dict(stage=stage, stage_outcome_first=alt, active_scans={k: active[k] for k in sorted(active)}, rescan_unknown=unknown,
                levels=levels, missing=missing, revealed_by=shown, first_revealed=shown[0] if shown else None,
                hazard_event_diff=stage == '4a' and any(runs[k].get('hazard_diff') for k in shown),
                inactive_but_q_changed=anomaly)


def rate(n, d):
    """분모 20 미만은 비율을 내지 않는다(TR-2026-02 §6)."""
    return dict(n=n, d=d, pct=None if d < 20 or d == 0 else round(100 * n / d, 2))


def metrics(variants, results, population):
    """variants: 추출 변종 목록(번호 순), results[id] = classify 결과, population[cell][group] = §3-1 대상 조건 수."""
    m1, m2, m3 = {}, {}, {}
    for cell in CELLS:
        vs = [v for v in variants if v['cell'] == cell]
        if not vs:
            continue
        m1[cell], m2[cell] = {}, {}
        weighted_num, weighted_den = 0.0, 0
        for g in GROUPS + ['전체']:
            gv = [v for v in vs if g == '전체' or v['group'] == g]
            if not gv:
                continue
            st = Counter(results[v['id']]['stage'] for v in gv)
            rev = st['4a'] + st['4b']
            act = st['2'] + st['3'] + rev
            m1[cell][g] = dict(all=rate(rev, len(gv)), active=rate(rev, act), held=st['보류'])
            m2[cell][g] = {s: st[s] for s in STAGES}
            m2[cell][g]['4a_위험사건'] = sum(1 for v in gv if results[v['id']]['hazard_event_diff'])
            if g != '전체' and population[cell].get(g):
                weighted_num += population[cell][g] * rev / len(gv)
                weighted_den += population[cell][g]
        m1[cell]['가중 전체'] = dict(pct=round(100 * weighted_num / weighted_den, 2) if weighted_den else None,
                                  population=weighted_den, rule='묶음별 드러난 비율(분모 추출 변종 전체)을 §3-1 대상 조건 수로 가중')
        first = Counter(results[v['id']]['first_revealed'] for v in vs if results[v['id']]['first_revealed'])
        single = Counter(results[v['id']]['revealed_by'][0] for v in vs if len(results[v['id']]['revealed_by']) == 1)
        m3[cell] = dict(first_revealed=dict(first), only_one_scenario=sum(single.values()), only_one_by_scenario=dict(single),
                        revealed_scenario_count_hist={str(k): c for k, c in sorted(Counter(
                            len(results[v['id']]['revealed_by']) for v in vs if results[v['id']]['stage'] in REVEALED).items())})
    return m1, m2, m3


def predictions(variants, results, key='stage'):
    """§7. I-5: 세 셀 합산, 보류는 분모에서 뺀다. P1 의 「복귀·포장 핸드셰이크」는 두 묶음을 합친 비율이 주 판정, 묶음별은 참고.
    key='stage_outcome_first' 는 I-1 민감도(미활성인데 출력이 달라진 변종을 결과대로 다시 분류)용 참고 판정."""
    def undetected(groups):
        vs = [v for v in variants if v['group'] in groups and results[v['id']][key] != '보류']
        n = sum(1 for v in vs if results[v['id']][key] in ('1', '2', '3'))
        return dict(n=n, d=len(vs), pct=round(100 * n / len(vs), 2) if vs else None)
    safety, target = undetected({'안전'}), undetected({'복귀', '포장 핸드셰이크'})
    ref = {g: undetected({g}) for g in ('복귀', '포장 핸드셰이크')}
    if safety['d'] == 0 or target['d'] == 0:
        p1 = dict(verdict='[판정 불가 — 분모 0]', diff_pp=None)
    else:
        diff = round(target['pct'] - safety['pct'], 2)
        p1 = dict(verdict='[맞음]' if diff >= 20 else '[틀림]', diff_pp=diff)
    p1.update(safety=safety, return_and_handshake=target, reference_by_group=ref,
              reference_diff_pp={g: (round(r['pct'] - safety['pct'], 2) if r['d'] and safety['d'] else None) for g, r in ref.items()})
    und = [v for v in variants if results[v['id']][key] in ('1', '2', '3')]
    s1 = sum(1 for v in und if results[v['id']][key] == '1')
    if not und:
        p2 = dict(verdict='[판정 불가 — 미검출 0]', stage1=0, undetected=0, pct=None)
    else:
        pct = round(100 * s1 / len(und), 2)
        p2 = dict(verdict='[맞음]' if pct >= 50 else '[틀림]', stage1=s1, undetected=len(und), pct=pct)
    return dict(P1=p1, P2=p2)


def representatives(variants, results):
    """§10: 범주마다 변종 번호가 가장 작은 것(목록 번호 = 셀 이름 + 순번, 셀 A → B → 포장 순)."""
    order = {c: i for i, c in enumerate(CELLS)}
    out = {}
    for s in STAGES:
        ids = sorted((order[v['cell']], v['id']) for v in variants if results[v['id']]['stage'] == s)
        out[s] = ids[0][1] if ids else None
    rev = sorted((order[v['cell']], v['id']) for v in variants if results[v['id']]['stage'] in REVEALED)
    out['드러남'] = rev[0][1] if rev else None
    return out
