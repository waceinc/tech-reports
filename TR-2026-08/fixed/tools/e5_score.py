"""E5 채점기 (사전 등록 §6 · §7 · §8 · §12 ⑤).

입력: 문항(e5_prompt items) · 규칙 예측(e5_rules apply, 옆 .meta.json) · M1 결과(e5_m1 run, 첫 줄 머리). 판정 분리 = test_seen + test_unseen(기본),
test_unseen 은 모든 과제에서 따로 보고. 기준값 선택 = val. 판정 상수는 e5/m1/judge.json 한 곳(비율은 정확한 분수로 비교).

  M1 주 답       유효 순열(min(5, n!) 개) 확률(원래 선택지 순서) 평균의 1위. 동률은 원래 순서가 앞선 선택지 + 「동률」 표시
  사람 확인       유효 순열마다 1위(순열 안 동률은 원래 순서 앞)가 하나라도 다르면. 정확도 분모에 넣고(주 답으로 채점) 따로 센다
  변동폭          주 답 범주 확률의 순열 간 최대 − 최소
  M1 실패         (문항, 순열) 중복을 없앤 뒤 유효 순열(오류 없음 · 선택지 글자가 상위 목록에 하나 이상)이 0 인 문항 = 실패(오답).
                 유효 순열이 1 이상이지만 min(5, n!) 보다 적으면 「일부 실패」 — 유효 순열로 채점하고 따로 센다.
                 실행 무효 = 판정 문항(T1 셀 B 못 정함 + T3 문항) 중 실패 문항 비율 > 0.05(분자 = 실패 문항, 분모 = 판정 문항)
  구성 C (T1)     R0-전체가 정한 문항은 규칙 답, 못 정한 문항은 M1 주 답(문항마다 하나만)
  T3 이진         정비 필요 = 양성. 독립 단위 = 실행(사전 등록 §7-4, M1-4 리드 결정 1). 문항 선택(lead_s 5 초 조건) 뒤 남은 창 기준:
                 양성 단위 = 정비 필요 창이 하나라도 있는 실행(그 실행 창 중 하나라도 「정비 필요」로 내면 TP).
                 음성 단위 = 음성 창만 있는 실행(하나라도 「정비 필요」로 내면 FP). 정비 필요 창이 5 초 조건으로 빠진 실행도 남은 창이
                 음성뿐이면 음성 단위다. 섞인 실행(양성 단위)의 음성 창에서 낸 「정비 필요」는 「이른 경보」로 따로 센다(판정에 안 씀).
                 M1 은 점수 = 「정비 필요」 평균 확률 ≥ 기준값. 기준값 = val 의 서로 다른 점수 중 val 재현율 ≥ 0.97 인 가장 높은 값.
                 T3 문항 = t3.lead_s 가 null 이거나 5 초 이상
  95 % 구간       부트스트랩 10,000 회(시드 e5-score-boot-v1 + 지표 이름, 백분위 2.5·97.5). 묶음 = 조합 키(T1·T2·T4), 실행(T3).
                 비율이 0 또는 1 이면 Clopper–Pearson(닫힌 꼴)
  판정 표         §8 그대로 — T1 · T2·T4 일관성 · T3(우선순위: 보류 → 규칙으로 충분 → 모델이 보탠다 → 둘 다 미달), 문항 수 조건 포함
  잘림            R0-T3 은 모델과 같은 기록 텍스트를 되읽어 본다. 규칙·M1 의 뺀 줄 수 또는 기록 텍스트 sha256 이 다르면 T3 「실행 무효」
  고정 입력 대조  M1 결과 머리(GGUF·model.json·prompts.json·judge.json·문항 파일·도구 sha256·요청·서버 실제 인자·/props)와 규칙 예측 메타
                 (e5_rules.py·표·문항 파일·judge.json sha256)를 지금 고정 파일과 대조 — 하나라도 다르면 모든 판정 「실행 무효」(사전 등록 §8 끝)

공식 세트 실행 순서(강제 — test 를 여는 명령은 규칙 표 해시 기록을 확인하고, 그 자리에서 train 으로 표를 다시 만들어 대조한다):
  1 e5_prompt.py items --splits train,val → 2 e5_rules.py build --set-root <공식> --record <기록>(train 만)
  → 3 e5_prompt.py items/truncate --splits ...,test_seen,test_unseen --rules-record <기록> → 4 e5_rules.py apply --truncation … --rules-record …
  → 5 e5_m1.py run --start-server --rules-record … → 6 e5_score.py --rules-record …(기록 없거나 표·코드 해시가 다르면 거부)
공식 경로는 CLI 다. score() 를 직접 부를 때 판정 분리에 test 가 있으면 rules_record_ok=True 와 input_problems 를 넘겨야 한다.

  python3 tools/e5_score.py --items ITEMS --rules PRED --m1 RESULTS --out SCORE.json --md SCORE.md [--eval-splits val --val-split val]
"""
import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from fractions import Fraction as F
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
JUDGE_PATH = ROOT / 'e5' / 'm1' / 'judge.json'
J = json.loads(JUDGE_PATH.read_text())
TEST_SPLITS = ('test_seen', 'test_unseen')
MAINT = '정비 필요'


def q(s):
    """판정 상수(문자열) → 정확한 분수."""
    return F(str(s))


def frac(x, n):
    return F(x, n) if n else None


# ---------------------------------------------------------------- 통계

def _rng(name):
    return np.random.default_rng(int.from_bytes(hashlib.sha256(f"{J['bootstrap']['seed']}|{name}".encode()).digest()[:8], 'big'))


def clopper_pearson_edge(x, n, alpha=0.05):
    """x = 0 또는 n 일 때의 Clopper–Pearson 구간(닫힌 꼴)."""
    if x == 0:
        return (0.0, 1 - (alpha / 2) ** (1 / n))
    if x == n:
        return ((alpha / 2) ** (1 / n), 1.0)
    raise ValueError('edge only')


def _weights(name, k):
    n = J['bootstrap']['n']
    rng = _rng(name)
    idx = rng.integers(0, k, size=(n, k))
    w = np.zeros((n, k))
    np.add.at(w, (np.repeat(np.arange(n), k), idx.ravel()), 1)
    return w


def _pct(st):
    lo, hi = J['bootstrap']['percentiles']
    return float(np.percentile(st, lo)), float(np.percentile(st, hi))


def prop_ci(name, clusters):
    """clusters: [(맞음 수, 분모)] — 묶음 단위 부트스트랩. 비율 0·1 이면 Clopper–Pearson. p 는 표시용 실수, 판정은 x·n 정수로."""
    x = sum(c[0] for c in clusters)
    n = sum(c[1] for c in clusters)
    if n == 0:
        return dict(x=0, n=0, p=None, lo=None, hi=None, method=None, clusters=0)
    p = x / n
    if x in (0, n):
        lo, hi = clopper_pearson_edge(x, n)
        return dict(x=x, n=n, p=p, lo=lo, hi=hi, method='clopper-pearson', clusters=len(clusters))
    k = len(clusters)
    a = np.array([c[0] for c in clusters], float)
    d = np.array([c[1] for c in clusters], float)
    w = _weights(name, k)
    with np.errstate(invalid='ignore', divide='ignore'):
        st = (w @ a) / (w @ d)
    st = st[np.isfinite(st)]
    lo, hi = _pct(st)
    return dict(x=x, n=n, p=p, lo=lo, hi=hi, method='bootstrap', clusters=k)


def diff_ci(name, clusters):
    """clusters: [(A 맞음, B 맞음, 분모)] — A − B 비율 차이, 짝 묶음 부트스트랩. 차이는 정수 분자(xa − xb)·분모 n 으로 둔다."""
    n = sum(c[2] for c in clusters)
    if n == 0:
        return dict(diff=None, num=None, n=0, lo=None, hi=None, clusters=0)
    num = sum(c[0] for c in clusters) - sum(c[1] for c in clusters)
    a = np.array([c[0] for c in clusters], float)
    b = np.array([c[1] for c in clusters], float)
    d = np.array([c[2] for c in clusters], float)
    w = _weights(name, len(clusters))
    with np.errstate(invalid='ignore', divide='ignore'):
        st = (w @ a - w @ b) / (w @ d)
    st = st[np.isfinite(st)]
    lo, hi = _pct(st)
    return dict(diff=num / n, num=num, n=n, lo=lo, hi=hi, clusters=len(clusters))


def ratio(c):
    """prop_ci 결과 → 정확한 분수(없으면 None)."""
    return frac(c['x'], c['n']) if c and c.get('n') else None


def group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return g


# ---------------------------------------------------------------- M1 요약

def argmax_first(v):
    m = max(v)
    return v.index(m), sum(1 for x in v if x == m) > 1


def n_perms(item):
    return min(5, math.factorial(len(item['choices'])))


def _valid(r):
    return not r.get('error') and not r.get('no_letter') and bool(r.get('probs'))


def m1_summary(item, rows):
    """(문항, 순열) 중복을 없애고(유효한 줄 우선) 유효 순열로 채점. 유효 0 = 실패, 0 < 유효 < min(5, n!) = 일부 실패."""
    by = {}
    for r in rows:
        j = r.get('perm_index')
        if j not in by or (_valid(r) and not _valid(by[j])):
            by[j] = r
    ok = [by[j] for j in sorted(by, key=lambda v: (v is None, v)) if _valid(by[j])]
    expected = n_perms(item)
    out = dict(n_perm=len(by), n_valid=len(ok), expected_perms=expected, missing_perms=sum(1 for r in by.values() if r.get('missing')),
               truncated=max([r.get('dropped_lines') or 0 for r in by.values()] or [0]), partial=0 < len(ok) < expected,
               record_sha256=sorted({r.get('record_sha256') for r in by.values()}, key=str))
    if not ok:
        return dict(out, failed=True, answer=None)
    k = len(item['choices'])
    mean = [sum(r['probs'][i] for r in ok) / len(ok) for i in range(k)]
    main, tie = argmax_first(mean)
    tops = {argmax_first(r['probs'])[0] for r in ok}
    chosen = [r['probs'][main] for r in ok]
    return dict(out, failed=False, mean=mean, answer=item['choices'][main], prob=mean[main], tie=tie, human_check=len(tops) > 1,
                spread=max(chosen) - min(chosen))


# ---------------------------------------------------------------- T1

def _n_faults(ck):
    return len((ck or '').split('|', 1)[0].split('+')) if ck else 0


def t1_answer(x, method, R, M):
    r = R[x['item_id']]
    if method == 'R0':
        return r['r0_full']['answer']
    if method == 'R1':
        return r['r1']['answer']
    if method == 'R0-가림':
        return r['r0_masked']['answer']
    if method == 'M1':
        return M[x['item_id']].get('answer')
    if method == 'C':
        return r['r0_full']['answer'] if r['r0_full']['determined'] else M[x['item_id']].get('answer')
    raise KeyError(method)


def confusion(rows, ans, name):
    """혼동표: 참 범주별 줄. 줄 문항이 min_items_for_rate 미만이면 수만, 이상이면 재현율도."""
    out = {}
    for t, v in sorted(group(rows, lambda x: x['answer']).items()):
        c = Counter(str(ans(x)) for x in v)
        row = dict(n=len(v), counts=dict(sorted(c.items())))
        if len(v) >= J['min_items_for_rate']:
            row['recall'] = prop_ci(f'{name}|{t}', [(sum(ans(x) == x['answer'] for x in w), len(w)) for w in group(v, lambda x: x['combo_key']).values()])
        out[t] = row
    return out


def t1_block(items, R, M, splits_label):
    b = [x for x in items if x['task'] == 'T1' and x['cell'] == 'B']
    und = [x for x in b if not R[x['item_id']]['r0_full']['determined']]
    det = [x for x in b if R[x['item_id']]['r0_full']['determined']]
    ans = lambda x, m: t1_answer(x, m, R, M)

    def acc(name, rows, method):
        g = group(rows, lambda x: x['combo_key'])
        return prop_ci(f'{splits_label}|{name}|{method}', [(sum(ans(x, method) == x['answer'] for x in v), len(v)) for v in g.values()])

    out = dict(n_cell_b=len(b), n_undetermined=len(und), n_determined=len(det), undetermined_keys=len({x['combo_key'] for x in und}))
    out['undetermined_acc'] = {m: acc('und', und, m) for m in ('R0', 'R1', 'M1', 'C', 'R0-가림')}
    g = group(und, lambda x: x['combo_key'])
    out['diff_C_minus_R0'] = diff_ci(f'{splits_label}|diff', [(sum(ans(x, 'C') == x['answer'] for x in v), sum(ans(x, 'R0') == x['answer'] for x in v), len(v)) for v in g.values()])
    out['determined_acc_R0'] = acc('det', det, 'R0')
    out['all_acc'] = {m: acc('all', b, m) for m in ('R0', 'R1', 'M1', 'C', 'R0-가림')}
    out['human_check'] = dict(undetermined=sum(1 for x in und if M[x['item_id']].get('human_check')), all_m1=sum(1 for x in b if M[x['item_id']].get('human_check')))
    risk = {}
    for cls in J['risk4']:
        pos = [x for x in b if x['answer'] == cls]
        neg = [x for x in b if x['answer'] != cls]
        row = dict(n_pos=len(pos), n_neg=len(neg))
        for m in ('C', 'R0', 'M1'):
            tp = sum(ans(x, m) == cls for x in pos)
            fp = sum(ans(x, m) == cls for x in neg)
            row[m] = dict(tp=tp, fn=len(pos) - tp, fp=fp, tn=len(neg) - fp)
            if len(pos) >= J['min_items_for_rate']:
                row[m]['recall'] = prop_ci(f'{splits_label}|risk|{cls}|{m}', [(sum(ans(x, m) == cls for x in v), len(v)) for v in group(pos, lambda x: x['combo_key']).values()])
            row[m]['missed'] = [x['window_id'] for x in pos if ans(x, m) != cls]
        risk[cls] = row
    out['risk4'] = risk
    out['confusion'] = {m: confusion(b, lambda x, m=m: ans(x, m), f'{splits_label}|conf|{m}') for m in ('C', 'M1', 'R0')}
    out['confusion_by_split'] = {sp: {m: confusion([x for x in b if x['split'] == sp], lambda x, m=m: ans(x, m), f'{splits_label}|conf|{sp}|{m}') for m in ('C', 'M1', 'R0')}
                                 for sp in sorted({x['split'] for x in b})}
    # 복합 고장(사전 등록 §10): test_seen 의 2·3개 조합 문항을 단일 고장과 따로
    seen = [x for x in b if x['split'] == 'test_seen']
    out['test_seen_by_faults'] = {k: {m: acc(f'seen|{k}', v, m) for m in ('C', 'R0', 'M1')} | {'n': len(v)}
                                  for k, v in sorted(group(seen, lambda x: 'single' if _n_faults(x['combo_key']) <= 1 else f"{_n_faults(x['combo_key'])}faults").items())}
    out['verdict'] = t1_verdict(out)
    return out


def t1_verdict(o):
    T = J['T1']
    n, keys = o['n_undetermined'], o['undetermined_keys']
    if n < T['min_items'] or keys < T['min_keys']:
        return dict(verdict='판정 보류', reason=f"못 정함 문항 {n}(≥{T['min_items']}) · 조합 키 {keys}(≥{T['min_keys']})")
    d = o['diff_C_minus_R0']
    r0 = ratio(o['undetermined_acc']['R0'])
    if d['num'] is not None and F(d['num'], d['n']) >= q(T['gain']) and d['lo'] is not None and d['lo'] > 0:
        return dict(verdict='모델이 보탠다', reason=f"C − R0 = {d['num']}/{d['n']} = {d['diff']:.3f}, 95 % 하한 {d['lo']:.3f}")
    if r0 is not None and r0 >= q(T['rule_ok']):
        return dict(verdict='규칙으로 충분', reason=f"R0-전체 {float(r0):.3f} ≥ {T['rule_ok']}, 구성 C 조건 미달")
    return dict(verdict='둘 다 미달', reason=f"R0-전체 {None if r0 is None else round(float(r0), 3)} < {T['rule_ok']}, 구성 C 조건 미달")


# ---------------------------------------------------------------- T2 · T4

T2_SUCC = {1: {2}, 2: {3, 4}, 3: {4}, 4: {5}, 5: {6}, 6: {7}, 7: {8}, 8: {0}}


def _step(choice):
    return int(choice.split(' ', 1)[0]) if choice is not None else None


def dangerous(x, a):
    """위험 오답: T4 = 정답 1위가 안전(등급 1) 사건인데 다른 사건을 1위로 냄 · T2 = 복귀표에서 갈 수 없는 단계, 또는 마무리 밀기가
    거부될 문항(정답 4)에 3 을 냄."""
    if a == x['answer']:
        return False
    if x['task'] == 'T4':
        return x['grades'].get(x['answer']) == 1
    cur, p = x['current_step'], _step(a)
    return p not in T2_SUCC.get(cur, set()) or (cur == 2 and p == 3 and x['next_step'] == 4)


def cons_block(items, R, M, task, label):
    C = J['consistency_T2_T4']
    rows = [x for x in items if x['task'] == task]
    g = group(rows, lambda x: x['combo_key'])
    r0 = prop_ci(f'{label}|{task}|R0', [(sum(R[x['item_id']]['r0']['answer'] == x['answer'] for x in v), len(v)) for v in g.values()])
    m1 = prop_ci(f'{label}|{task}|M1', [(sum(M[x['item_id']].get('answer') == x['answer'] for x in v), len(v)) for v in g.values()])
    dz = [x['window_id'] for x in rows if dangerous(x, R[x['item_id']]['r0']['answer'])]
    dz_m1 = sum(1 for x in rows if M[x['item_id']].get('n_perm') and dangerous(x, M[x['item_id']].get('answer')))
    fb = sum(1 for x in rows if R[x['item_id']]['r0'].get('fallback'))
    by_cell = {c: sum(R[x['item_id']]['r0']['answer'] == x['answer'] for x in rows if x['cell'] == c) for c in sorted({x['cell'] for x in rows})}
    n_cell = Counter(x['cell'] for x in rows)
    if len(rows) < C['min_items']:
        v = dict(verdict='판정 보류', reason=f"문항 {len(rows)} < {C['min_items']}")
    elif ratio(r0) >= q(C['acc']) and len(dz) <= C['dangerous_max']:
        v = dict(verdict='[PASS]', reason=f"R0 {r0['x']}/{r0['n']} ≥ {C['acc']} · 위험 오답 {len(dz)}")
    else:
        v = dict(verdict='[FAIL]', reason=f"R0 {r0['x']}/{r0['n']} · 위험 오답 {len(dz)}")
    return dict(n=len(rows), r0=r0, r0_dangerous=len(dz), r0_dangerous_windows=dz, r0_fallback=fb, r0_by_cell={c: f'{by_cell[c]}/{n_cell[c]}' for c in by_cell},
                m1=m1, m1_dangerous=dz_m1, m1_answered=sum(1 for x in rows if M[x['item_id']].get('n_perm')), verdict=v)


# ---------------------------------------------------------------- T3

def t3_items(items):
    lead = q(J['T3']['lead_s'])
    return [x for x in items if x['task'] == 'T3' and (x['lead_s'] is None or F(str(x['lead_s'])) >= lead)]


def t3_units(rows, flag):
    """실행 단위(사전 등록 §7-4): 양성 단위 = 정비 필요 창이 하나라도 있는 실행, 음성 단위 = 음성 창만 있는 실행.
    섞인 실행의 음성 창 경보 = early(이른 경보, 판정에 안 씀)."""
    out = []
    for rid, v in sorted(group(rows, lambda x: x['run_id']).items()):
        pos = [x for x in v if x['answer'] == MAINT]
        negw = [x for x in v if x['answer'] != MAINT]
        out.append(dict(run_id=rid, combo_key=v[0]['combo_key'], pos=bool(pos), tp=any(flag(x) for x in pos),
                        neg=not pos, fp=(not pos) and any(flag(x) for x in negw),
                        early=sum(1 for x in negw if flag(x)) if pos else 0,
                        channels=sorted({c for x in pos for c in x['maint_channels']}),
                        no_alert=all(x['lead_s'] is None for x in v)))
    return out


def rate(units, kind, name):
    if kind == 'recall':
        cl = [(int(u['tp']), 1) for u in units if u['pos']]
    else:
        cl = [(int(u['fp']), 1) for u in units if u['neg']]
    return prop_ci(name, cl)


def m1_score(M, x):
    m = M[x['item_id']]
    if m.get('failed') or not m.get('mean'):
        return None
    return m['mean'][x['choices'].index(MAINT)]


def choose_threshold(val_rows, M):
    """val 의 서로 다른 점수(높은 것부터) 중 실행 단위 재현율 ≥ val_recall 인 가장 높은 값(정확한 분수 비교)."""
    target = q(J['val_recall'])
    scores = sorted({s for s in (m1_score(M, x) for x in val_rows) if s is not None}, reverse=True)
    if not any(x['answer'] == MAINT for x in val_rows):
        return None, 'val 정비 필요 0'
    for t in scores:
        u = t3_units(val_rows, lambda x, t=t: (m1_score(M, x) if m1_score(M, x) is not None else -1) >= t)
        pos = [z for z in u if z['pos']]
        if pos and F(sum(z['tp'] for z in pos), len(pos)) >= target:
            return t, f'val 양성 실행 {len(pos)}'
    return None, f"val 재현율 {J['val_recall']} 에 닿는 기준값 없음"


def t3_block(items, val_items, R, M, label):
    rows = t3_items(items)
    vrows = t3_items(val_items)
    thr, why = choose_threshold(vrows, M)
    r0flag = lambda x: R[x['item_id']]['r0_t3']['answer'] == MAINT
    m1flag = (lambda x: (m1_score(M, x) if m1_score(M, x) is not None else -1) >= thr) if thr is not None else (lambda x: False)
    u0, u1 = t3_units(rows, r0flag), t3_units(rows, m1flag)
    chans = ('belt_speed_dev', 'chatter', 'stroke_ratio')
    res = dict(n_windows=len(rows), excluded_short_lead=sum(1 for x in items if x['task'] == 'T3') - len(rows), threshold=thr, threshold_note=why,
               n_pos_runs=sum(u['pos'] for u in u0), n_neg_runs=sum(u['neg'] for u in u0),
               mixed_runs=sum(1 for u in u0 if u['pos'] and any(x['answer'] != MAINT for x in rows if x['run_id'] == u['run_id'])),
               early_alarms=dict(r0=sum(u['early'] for u in u0), m1=sum(u['early'] for u in u1),
                                 note='섞인 실행(양성 단위)의 음성 창에서 「정비 필요」를 낸 창 수 — 참고, 판정에 안 씀'),
               channel_pos_runs={c: sum(1 for u in u0 if u['pos'] and c in u['channels']) for c in chans},
               r0=dict(recall=rate(u0, 'recall', f'{label}|t3|r0|rec'), fpr=rate(u0, 'fpr', f'{label}|t3|r0|fpr'),
                       unknown=sum(1 for x in rows if R[x['item_id']]['r0_t3']['answer'] == '모름')),
               m1=dict(recall=rate(u1, 'recall', f'{label}|t3|m1|rec'), fpr=rate(u1, 'fpr', f'{label}|t3|m1|fpr')),
               lead_s_maint=sorted([x['lead_s'] for x in rows if x['answer'] == MAINT], key=lambda v: (v is None, v or 0)),
               m1_level_acc=prop_ci(f'{label}|t3|m1|acc', [(int(M[x['item_id']].get('answer') == x['answer']), 1) for x in rows]),
               r0_level_acc=prop_ci(f'{label}|t3|r0|acc', [(int(R[x['item_id']]['r0_t3']['answer'] == x['answer']), 1) for x in rows]))
    for ch in J['T3']['channels']:
        res[f'r0_recall_{ch}'] = rate([u for u in u0 if ch in u['channels']], 'recall', f'{label}|t3|r0|{ch}')
        res[f'm1_recall_{ch}'] = rate([u for u in u1 if ch in u['channels']], 'recall', f'{label}|t3|m1|{ch}')
    # 벨트 단독 「PLC 가 끝까지 모르는 이상」(§7-3): 조합 키가 벨트 하나뿐이고 그 실행 창이 모두 lead_s null 인 양성 실행
    solo = lambda u: u['pos'] and u['combo_key'] and u['combo_key'].split('|')[0] == 'D.belt' and u['no_alert']
    res['belt_solo_plc_unaware'] = dict(n=sum(1 for u in u0 if solo(u)), r0_tp=sum(1 for u in u0 if solo(u) and u['tp']), m1_tp=sum(1 for u in u1 if solo(u) and u['tp']))
    neg0 = {u['run_id']: u for u in u0 if u['neg']}
    neg1 = {u['run_id']: u for u in u1 if u['neg']}
    res['fpr_diff_R0_minus_M1'] = diff_ci(f'{label}|t3|fprdiff', [(int(neg0[k]['fp']), int(neg1[k]['fp']), 1) for k in sorted(neg0)])
    res['unit'] = '실행(run_id) — 같은 실행의 창은 묶는다'
    res['bootstrap_cluster'] = J['bootstrap']['cluster_T3']
    # 잘림 상호 대조(M1-5): 뺀 줄 수와 기록 텍스트 sha256 이 규칙·모델 모두 같아야 한다(모델 쪽 순열마다 같은 텍스트여야 한다)
    def _mism(x):
        m, r0 = M[x['item_id']], R[x['item_id']]['r0_t3']
        if not m.get('n_perm'):
            return False
        return (r0.get('dropped_lines') or 0) != (m.get('truncated') or 0) or m.get('record_sha256', [None]) != [r0.get('record_sha256')]
    mism = [x['window_id'] for x in rows if _mism(x)]
    res['truncation_mismatch'] = mism
    res['truncated_windows'] = sum(1 for x in rows if R[x['item_id']]['r0_t3'].get('dropped_lines'))
    res['verdict'] = t3_verdict(res) if not mism else dict(verdict='실행 무효', reason=f'규칙·모델 잘림 불일치 {len(mism)}')
    return res


def t3_verdict(o):
    """우선순위(M1-2 리드 결정 6, 사전 등록 §6-4 — 규칙이 판정선을 넘으면 모델을 붙이지 않는다):
    판정 보류(문항 수) → 규칙으로 충분 → 모델이 보탠다 → 둘 다 미달. 비율은 정확한 분수로 비교."""
    T = J['T3']
    cp = o['channel_pos_runs']
    if o['n_pos_runs'] < T['min_pos_runs'] or any(cp[c] < T['min_channel_runs'] for c in T['channels']):
        return dict(verdict='판정 보류', reason=f"정비 필요 실행 {o['n_pos_runs']}(≥{T['min_pos_runs']}) · " + ' · '.join(f'{c} {cp[c]}' for c in T['channels']) + f"(각 ≥{T['min_channel_runs']})")
    m1r, m1f, r0r, r0f = ratio(o['m1']['recall']), ratio(o['m1']['fpr']), ratio(o['r0']['recall']), ratio(o['r0']['fpr'])
    d = o['fpr_diff_R0_minus_M1']
    model_adds = (o['threshold'] is not None and m1r is not None and m1r >= q(T['recall']) and m1f is not None and r0f is not None and m1f < r0f
                  and d['lo'] is not None and d['lo'] > 0)
    if r0r is not None and r0r >= q(T['recall']) and r0f is not None and r0f <= q(T['fpr']):
        return dict(verdict='규칙으로 충분', reason=f'R0-T3 재현율 {r0r} · 오탐률 {r0f}' + (' (모델이 보탠다 조건도 참 — 규칙 우선)' if model_adds else ''))
    if model_adds:
        return dict(verdict='모델이 보탠다', reason=f'M1 재현율 {m1r} · 오탐률 {m1f} < R0 {r0f}, 차이 하한 {d["lo"]:.3f}')
    return dict(verdict='둘 다 미달', reason=f'R0-T3 재현율 {r0r} · 오탐률 {r0f}, M1 조건 미달')


# ---------------------------------------------------------------- 고정 입력 대조

def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check_inputs(m1_header, items_path, rules_meta, rules_record=None, require_m1=True):
    """고정 입력 해시 대조(사전 등록 §8 「고정 입력 해시 불일치 → 실행 무효」). 문제 목록을 돌려준다(빈 목록 = 일치)."""
    probs = []
    model = json.loads((ROOT / 'e5' / 'm1' / 'model.json').read_text())
    if m1_header is None:
        if require_m1:
            probs.append('M1 결과 머리 없음')
    else:
        h = m1_header
        want = dict(gguf_sha256=model['gguf']['sha256'], model_json_sha256=sha256_file(ROOT / 'e5' / 'm1' / 'model.json'))
        for k, v in want.items():
            if h.get('model', {}).get(k) != v:
                probs.append(f'M1 머리 {k} 불일치')
        for k, p in (('prompts_sha256', ROOT / 'e5' / 'm1' / 'prompts.json'), ('e5_prompt_sha256', ROOT / 'tools' / 'e5_prompt.py'),
                     ('e5_m1_sha256', ROOT / 'tools' / 'e5_m1.py'), ('items_sha256', items_path)):
            if h.get(k) != sha256_file(p):
                probs.append(f'M1 머리 {k} 불일치')
        if h.get('request') != model['request']:
            probs.append('M1 머리 request 불일치')
        if not h.get('server_started_by_runner'):
            probs.append('서버를 실행기가 띄우지 않음(실제 인자를 확인할 수 없음)')
        want_args = [str(Path(a).expanduser()) if a.startswith('~') else a for a in model['server']['args']]
        if (h.get('server_cmdline') or [None])[1:] != want_args:
            probs.append('서버 실제 실행 인자 불일치')
        props = h.get('server_props') or {}
        if props.get('model_path') != str(Path('~/models/' + model['gguf']['file']).expanduser()) or props.get('n_ctx') != 131072 \
                or props.get('total_slots') != 1 or model['llama_cpp']['short'] not in str(props.get('build_info')):
            probs.append(f'서버 /props 불일치 {props}')
        if h.get('llama_cpp_commit') != model['llama_cpp']['commit']:
            probs.append('llama.cpp 커밋 불일치')
        if h.get('judge_sha256') != sha256_file(JUDGE_PATH):
            probs.append('M1 머리 judge_sha256 불일치')
    if rules_meta is None:
        probs.append('규칙 예측 메타 없음')
    else:
        cur = sha256_file(ROOT / 'tools' / 'e5_rules.py')
        if rules_meta.get('e5_rules_sha256') != cur:
            probs.append('규칙 예측에 쓴 e5_rules.py 가 지금과 다름')
        import e5_prompt as EP
        if rules_meta.get('tables') != EP.rules_table_hashes():
            probs.append('규칙 예측에 쓴 표가 지금 표와 다름')
        if rules_meta.get('items_sha256') != sha256_file(items_path):
            probs.append('규칙 예측에 쓴 문항 파일이 --items 와 다름')
        if rules_meta.get('judge_sha256') != sha256_file(JUDGE_PATH):
            probs.append('규칙 예측 메타 judge_sha256 불일치')
        if rules_record is not None and rules_record.get('e5_rules_sha256') != rules_meta.get('e5_rules_sha256'):
            probs.append('규칙 표 기록의 e5_rules.py 와 규칙 예측의 e5_rules.py 가 다름')
    return probs


# ---------------------------------------------------------------- 전체

def _unseen_label(eval_splits):
    return 'test_unseen' in eval_splits and len(eval_splits) > 1


def score(items, rules, m1rows, eval_splits=('test_seen', 'test_unseen'), val_split='val', *, input_problems=None, rules_record_ok=None):
    if any(s in TEST_SPLITS for s in eval_splits) and (rules_record_ok is not True or input_problems is None):
        raise PermissionError('test 채점은 규칙 표 기록 확인(rules_record_ok=True)과 고정 입력 대조(input_problems) 뒤에만 — CLI 를 쓴다')
    R = {r['item_id']: r for r in rules}
    by = group(m1rows, lambda r: r['item_id'])
    M = {x['item_id']: (m1_summary(x, by[x['item_id']]) if x['item_id'] in by else dict(n_perm=0, failed=True, answer=None, partial=False)) for x in items}
    ev = [x for x in items if x['split'] in eval_splits]
    val = [x for x in items if x['split'] == val_split]
    label = '+'.join(eval_splits)
    out = dict(eval_splits=list(eval_splits), val_split=val_split, n_items=len(ev), judge_sha256=sha256_file(JUDGE_PATH),
               units=dict(T1='문항 · 부트스트랩 묶음 = 조합 키(combo_key)', T2='문항 · 묶음 = 조합 키', T4='문항 · 묶음 = 조합 키',
                          T3='실행(run_id) · 부트스트랩 묶음 = 실행(run_id)'),
               input_problems=input_problems)
    judged = [x for x in ev if (x['task'] == 'T1' and x['cell'] == 'B' and not R[x['item_id']]['r0_full']['determined'])] + t3_items(ev)
    asked = [x for x in ev if M[x['item_id']]['n_perm']]
    fails = [x for x in judged if M[x['item_id']]['failed']]
    fr = frac(len(fails), len(judged))
    out['m1_status'] = dict(fail_definition='실패 = (문항, 순열) 중복 제거 뒤 유효 순열 0. 일부 실패 = 0 < 유효 < min(5, n!) — 유효 순열로 채점. '
                                            '실행 무효 = 판정 문항(T1 셀 B 못 정함 + T3 문항) 중 실패 문항 비율 > fail_rate_max(분자 = 실패 문항 수, 분모 = 판정 문항 수)',
                            items_with_m1=len(asked), judged_items=len(judged), judged_failed=len(fails),
                            fail_rate=None if fr is None else float(fr), run_invalid=fr is not None and fr > q(J['fail_rate_max']),
                            all_sent_failed=sum(1 for x in ev if M[x['item_id']]['failed']), all_sent=len(ev),
                            partial_failed=sum(1 for x in ev if M[x['item_id']].get('partial')),
                            missing_perms=sum(M[x['item_id']].get('missing_perms', 0) for x in asked),
                            missing_items=sum(1 for x in asked if M[x['item_id']].get('missing_perms')),
                            truncated_items=sum(1 for x in asked if M[x['item_id']].get('truncated')),
                            human_check=sum(1 for x in asked if M[x['item_id']].get('human_check')),
                            ties=sum(1 for x in asked if M[x['item_id']].get('tie')),
                            confident_wrong=sum(1 for x in asked if not M[x['item_id']]['failed'] and M[x['item_id']]['answer'] != x['answer']
                                                and M[x['item_id']]['prob'] >= float(q(J['confident_wrong_prob']))),
                            spread_quantiles=[float(v) for v in np.percentile([M[x['item_id']]['spread'] for x in asked if not M[x['item_id']]['failed']] or [0], [0, 25, 50, 75, 100])],
                            prob_quantiles=[float(v) for v in np.percentile([M[x['item_id']]['prob'] for x in asked if not M[x['item_id']]['failed']] or [0], [0, 25, 50, 75, 100])])
    out['T1'] = t1_block(ev, R, M, label)
    out['T1_counts_AP'] = {c: dict(n=sum(1 for x in ev if x['task'] == 'T1' and x['cell'] == c),
                                   r0_correct=sum(1 for x in ev if x['task'] == 'T1' and x['cell'] == c and R[x['item_id']]['r0_full']['answer'] == x['answer']),
                                   m1_correct=sum(1 for x in ev if x['task'] == 'T1' and x['cell'] == c and M[x['item_id']].get('answer') == x['answer']),
                                   m1_answered=sum(1 for x in ev if x['task'] == 'T1' and x['cell'] == c and M[x['item_id']]['n_perm']))
                           for c in ('A', 'P')}
    out['T2'] = cons_block(ev, R, M, 'T2', label)
    out['T4'] = cons_block(ev, R, M, 'T4', label)
    out['T3'] = t3_block(ev, val, R, M, label)
    unseen = [x for x in ev if x['split'] == 'test_unseen']
    if unseen and _unseen_label(eval_splits):
        lab = label + '|unseen'
        out['test_unseen'] = dict(T1=t1_block(unseen, R, M, lab), T2=cons_block(unseen, R, M, 'T2', lab), T4=cons_block(unseen, R, M, 'T4', lab),
                                  T3=t3_block(unseen, val, R, M, lab))
        out['T1_test_unseen'] = out['test_unseen']['T1']
    out['missed_or_wrong_m1'] = [dict(window_id=x['window_id'], task=x['task'], truth=x['answer'], m1=M[x['item_id']].get('answer'),
                                      prob=M[x['item_id']].get('prob'), human_check=M[x['item_id']].get('human_check'))
                                 for x in asked if M[x['item_id']].get('answer') != x['answer']]
    out['verdicts'] = {'T1': out['T1']['verdict'], 'T2': out['T2']['verdict'], 'T4': out['T4']['verdict'], 'T3': out['T3']['verdict']}
    if out['m1_status']['run_invalid']:
        out['verdicts'] = {k: dict(verdict='실행 무효', reason=f"M1 실패 {len(fails)}/{len(judged)} > {J['fail_rate_max']}") for k in out['verdicts']}
    if input_problems:
        out['verdicts'] = {k: dict(verdict='실행 무효', reason='고정 입력 불일치: ' + '; '.join(input_problems[:5])) for k in out['verdicts']}
    return out


def check_rules_record(record_path, rules_path):
    """test 채점 전 확인(M1-2 결정 4 · M1-3 검수 권고): 기록 파일이 있고, 규칙 예측 메타의 표 sha256·세트·e5_rules.py sha256 이 기록과 같아야 한다.
    기록 자체는 e5_prompt.verify_rules_record 가 train 으로 표를 다시 만들어 대조한다(세트에 접근할 수 있을 때)."""
    if not record_path or not Path(record_path).exists():
        raise PermissionError('규칙 표 해시 기록 파일이 없다 — test 채점 거부(e5_rules.py build --record 를 test 를 열기 전에)')
    rec = json.loads(Path(record_path).read_text())
    meta_p = Path(str(rules_path) + '.meta.json')
    if not meta_p.exists():
        raise PermissionError(f'규칙 예측 메타 {meta_p} 없음 — test 채점 거부')
    meta = json.loads(meta_p.read_text())
    if rec.get('built_from') != ['train']:
        raise PermissionError('규칙 표 기록이 train 만으로 만든 표가 아니다')
    if rec.get('tables') != meta.get('tables'):
        raise PermissionError('규칙 예측에 쓴 표 sha256 이 기록과 다르다 — test 채점 거부')
    if rec.get('e5_rules_sha256') != meta.get('e5_rules_sha256'):
        raise PermissionError('규칙 예측에 쓴 e5_rules.py 가 기록과 다르다 — test 채점 거부')
    if Path(rec.get('set_root', '')).resolve() != Path(meta.get('set_root', '/nonexistent')).resolve():
        raise PermissionError('규칙 표 기록의 세트가 규칙 예측의 세트와 다르다 — test 채점 거부')
    import e5_prompt as EP
    EP.verify_rules_record(record_path, rec['set_root'])
    return rec


def _f(x, nd=3):
    return '—' if x is None else (f'{x:.{nd}f}' if isinstance(x, float) else str(x))


def _ci(c):
    if not c or c.get('p') is None:
        return '—'
    return f"{c['x']}/{c['n']} = {c['p']:.3f} [{_f(c['lo'])}, {_f(c['hi'])}]"


def markdown(o):
    L = [f"# E5 채점 — 판정 분리 {'+'.join(o['eval_splits'])} · 기준값 분리 {o['val_split']}", '',
         f"고정 입력 대조: {'일치' if o.get('input_problems') == [] else o.get('input_problems')}", '']
    L += ['| 과제 | 판정 | 근거 |', '| --- | --- | --- |']
    for k, v in o['verdicts'].items():
        L.append(f"| {k} | {v['verdict']} | {v['reason']} |")
    t = o['T1']
    L += ['', f"## T1 셀 B — 문항 {t['n_cell_b']} · 못 정함 {t['n_undetermined']}(조합 키 {t['undetermined_keys']}) · 정함 {t['n_determined']}", '',
          '| 방법 | 못 정함 정확도 [95 %] | 전체 정확도 [95 %] |', '| --- | --- | --- |']
    for m in ('R0', 'R1', 'M1', 'C', 'R0-가림'):
        L.append(f"| {m} | {_ci(t['undetermined_acc'][m])} | {_ci(t['all_acc'][m])} |")
    d = t['diff_C_minus_R0']
    L += ['', f"C − R0(못 정함) = {d['num']}/{d['n']} [{_f(d['lo'])}, {_f(d['hi'])}] · 정함 문항 R0 {_ci(t['determined_acc_R0'])} · 사람 확인(못 정함) {t['human_check']['undetermined']}", '',
          '| 위험 범주 | 양성 | C TP/FN/FP | R0 TP/FN/FP | M1 TP/FN/FP |', '| --- | --- | --- | --- | --- |']
    for cls, r in t['risk4'].items():
        L.append(f"| {cls} | {r['n_pos']} | " + ' | '.join(f"{r[m]['tp']}/{r[m]['fn']}/{r[m]['fp']}" for m in ('C', 'R0', 'M1')) + ' |')
    for task in ('T2', 'T4'):
        c = o[task]
        L += ['', f"## {task} 일관성 — 문항 {c['n']} · R0 {_ci(c['r0'])} · 위험 오답 {c['r0_dangerous']} · R1 대체 {c['r0_fallback']} · 셀별 {c['r0_by_cell']} · M1(참고, 응답 {c['m1_answered']}) {_ci(c['m1'])}"]
    t3 = o['T3']
    L += ['', f"## T3 — 창 {t3['n_windows']}(여유 5 초 미만 제외 {t3['excluded_short_lead']}) · 정비 필요 실행 {t3['n_pos_runs']} · 음성 실행(음성 창만) {t3['n_neg_runs']} · 섞인 실행 {t3['mixed_runs']} · 이른 경보 R0 {t3['early_alarms']['r0']} · M1 {t3['early_alarms']['m1']} · 채널 {t3['channel_pos_runs']} · 벨트 단독 PLC 모름 {t3['belt_solo_plc_unaware']}",
          f"기준값 {_f(t3['threshold'])}({t3['threshold_note']}) · R0 「모름」 {t3['r0']['unknown']} · 단위 {t3['unit']} · 구간 묶음 {t3['bootstrap_cluster']} · 잘린 창 {t3['truncated_windows']} · 규칙·모델 잘림 불일치 {len(t3['truncation_mismatch'])}", '',
          '| 방법 | 재현율 | 오탐률 | 수준 정확도 |', '| --- | --- | --- | --- |',
          f"| R0-T3 | {_ci(t3['r0']['recall'])} | {_ci(t3['r0']['fpr'])} | {_ci(t3['r0_level_acc'])} |",
          f"| M1 | {_ci(t3['m1']['recall'])} | {_ci(t3['m1']['fpr'])} | {_ci(t3['m1_level_acc'])} |"]
    if 'test_unseen' in o:
        u = o['test_unseen']
        L += ['', f"## test_unseen 따로 — T1 {u['T1']['verdict']['verdict']}(못 정함 {u['T1']['n_undetermined']}) · T2 {_ci(u['T2']['r0'])} · T4 {_ci(u['T4']['r0'])} · T3 R0 재현율 {_ci(u['T3']['r0']['recall'])} · M1 {_ci(u['T3']['m1']['recall'])}"]
    s = o['m1_status']
    L += ['', '## M1 상태', '', f"응답 문항 {s['items_with_m1']} · 판정 문항 {s['judged_items']} · 실패 {s['judged_failed']}(무효 {s['run_invalid']}) · 일부 실패 {s['partial_failed']} · 누락 순열 {s['missing_perms']}(문항 {s['missing_items']}) · "
          f"잘림 {s['truncated_items']} · 사람 확인 {s['human_check']} · 동률 {s['ties']} · 확신 오판 {s['confident_wrong']} · 변동폭 분위 {[round(x, 3) for x in s['spread_quantiles']]} · 선택 확률 분위 {[round(x, 3) for x in s['prob_quantiles']]}",
          '', f"실패 정의: {s['fail_definition']}"]
    return '\n'.join(L) + '\n'


def load_jsonl(p):
    return [json.loads(x) for x in open(p) if x.strip()]


def main():
    import sys
    sys.path[:0] = [str(ROOT / 'tools')]
    ap = argparse.ArgumentParser()
    ap.add_argument('--items', required=True)
    ap.add_argument('--rules', required=True)
    ap.add_argument('--m1', required=True)
    ap.add_argument('--eval-splits', default='test_seen,test_unseen')
    ap.add_argument('--val-split', default='val')
    ap.add_argument('--only-m1-items', action='store_true', help='연기 시험용: M1 결과가 있는 문항만 채점')
    ap.add_argument('--out', required=True)
    ap.add_argument('--md')
    ap.add_argument('--rules-record', help='판정 분리에 test 가 있으면 필수 — 규칙 표 해시 기록')
    a = ap.parse_args()
    evs = tuple(a.eval_splits.split(','))
    rec = None
    if any(s in TEST_SPLITS for s in evs):
        rec = check_rules_record(a.rules_record, a.rules)
    items = load_jsonl(a.items)
    rules = load_jsonl(a.rules)
    allm1 = load_jsonl(a.m1) if Path(a.m1).exists() else []
    head = next((r for r in allm1 if r.get('type') == 'header'), None)
    m1 = [r for r in allm1 if r.get('type') != 'header']
    meta_p = Path(str(a.rules) + '.meta.json')
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else None
    problems = check_inputs(head, a.items, meta, rec)
    if a.only_m1_items:
        have = {r['item_id'] for r in m1}
        items = [x for x in items if x['item_id'] in have]
    o = score(items, rules, m1, evs, a.val_split, input_problems=problems, rules_record_ok=True if rec is not None or not any(s in TEST_SPLITS for s in evs) else None)
    Path(a.out).write_text(json.dumps(o, ensure_ascii=False, indent=1, default=float) + '\n')
    md = markdown(o)
    if a.md:
        Path(a.md).write_text(md)
    print(md)


if __name__ == '__main__':
    main()
