#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WACE Inc.
"""TR-2026-08 independent check — recomputes the E5 verdicts and their numerators/denominators from the public results/ only.

Written separately from the official scorer (fixed/tools/e5_score.py is NOT imported or read). Definitions follow the
pre-registration v0.3 (fixed/E5_사전등록_v0.3_2026-10-06.md) sections 6, 7, 8 and 12-④; decision constants are read from
fixed/e5/m1/judge.json (the file whose SHA-256 is listed in section 12 of the pre-registration).

Inputs : results/items.jsonl.gz · results/rules_pred.jsonl.gz · results/m1_perms.jsonl.gz · results/score.json (only for comparison)
Output : results/check_output.json (full mode) or results/check_output_repo.json (repository mode)
Needs  : Python 3.10+ standard library + numpy.

Usage  : python3 scripts/check.py [--out PATH]

Two modes, chosen by whether results/m1_perms.jsonl.gz is present (it is over 5 MB and is only in the Zenodo record):
  full mode        everything below is recomputed.
  repository mode  m1_perms.jsonl.gz absent. Only what needs no M1 probabilities is recomputed — the rule baselines
                   (T1 R0-full / R1 / R0-masked accuracy, determined-item accuracy, R0 risk-class counts and R0 confusion;
                   T2 and T4 R0 accuracy, dangerous answers and their [PASS]/[FAIL] verdicts; T3 run units, R0-T3 recall,
                   false-positive rate, channel recalls, early alarms and level accuracy, the rule/model truncation
                   cross-check through the per-item text hash, and the T3 verdict when the rule already meets the line).
                   Everything that needs M1 (M1 and composition C, C - R0, the T1 verdict, the M1 threshold and M1 rates,
                   M1 status counts) is written as "[NOT_RUN(m1_perms 없음)]". Exit code 0 in both modes.

Bootstrap: 10,000 cluster resamples (percentiles 2.5 / 97.5). Seed string = judge.json bootstrap.seed ("e5-score-boot-v1").
The random stream of each interval is numpy default_rng(first 8 bytes, big-endian, of sha256("<seed>|<metric name>")),
cluster indices drawn as integers(0, k, size=(10000, k)); clusters are taken in first-appearance order (T3 units: run_id
order). This stream-naming convention is the one the official run used, so that intervals can be compared digit by digit
with results/score.json; the counting itself is written independently here. Proportions of 0 or 1 use the exact
Clopper-Pearson edge interval.
"""
import argparse
import gzip
import hashlib
import json
import re
from collections import Counter, OrderedDict
from fractions import Fraction as F
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[1]
RES = BASE / 'results'
FIX = BASE / 'fixed'
PREREG = FIX / 'E5_사전등록_v0.3_2026-10-06.md'
PREREG_SHA256 = '35b4e315a3e0f6f2279df408fd58905884722d002899a32236c0b5b446d2fe91'
EVAL = ('test_seen', 'test_unseen')
MAINT = '정비 필요'          # T3 positive level ("maintenance needed")
NR = '[NOT_RUN(m1_perms 없음)]'   # value written in repository mode for anything that needs M1
SAFETY_GRADE = 1             # T4 grade of safety events (priority table: safety > equipment > quality > production > info)


# ------------------------------------------------------------------ loading

def read_jsonl_gz(p):
    with gzip.open(p, 'rt', encoding='utf-8') as f:
        return [json.loads(x) for x in f if x.strip()]


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load():
    J = json.loads((FIX / 'e5' / 'm1' / 'judge.json').read_text(encoding='utf-8'))
    items = read_jsonl_gz(RES / 'items.jsonl.gz')
    rules = {r['item_id']: r for r in read_jsonl_gz(RES / 'rules_pred.jsonl.gz')}
    if not (RES / 'm1_perms.jsonl.gz').exists():
        return J, items, rules, None          # repository mode
    perms = {}
    for r in read_jsonl_gz(RES / 'm1_perms.jsonl.gz'):
        perms.setdefault(r['item_id'], []).append(r)
    return J, items, rules, perms


def fixed_hash_check():
    """Every fixed/ file listed in pre-registration section 12 must have the listed SHA-256; the pre-registration itself must
    have the published hash."""
    text = PREREG.read_text(encoding='utf-8')
    listed = {}
    for m in re.finditer(r'\|\s*`([^`]+)`\s*\|\s*`([0-9a-f]{64})`\s*\|', text):
        listed[m.group(1)] = m.group(2)
    out = OrderedDict(preregistration=dict(sha256=sha256_file(PREREG), expected=PREREG_SHA256, ok=sha256_file(PREREG) == PREREG_SHA256))
    # Pre-registration 12-③: the rule tables (R0-full, R0-masked, R0-T3, R1) are rebuilt from the OFFICIAL train split with the
    # same code and their SHA-256 recorded before the test splits are opened. Section 12 lists the hashes of the tables as they
    # stood when the document was frozen (built from the pilot); the run must use the recorded official-train tables instead.
    rec = json.loads((RES / 'provenance.json').read_text(encoding='utf-8'))['rules_record']
    out['rules_record'] = dict(built_from=rec.get('built_from'), recorded_at=rec.get('recorded_at'), tables=rec.get('tables'))
    files = []
    for p in sorted(FIX.rglob('*')):
        if not p.is_file() or p == PREREG:
            continue
        rel = p.relative_to(FIX).as_posix()
        want = listed.get(rel)
        got = sha256_file(p)
        row = dict(file=rel, sha256=got, preregistered=want, ok=None if want is None else got == want)
        if rel.startswith('history/'):
            row['basis'] = 'earlier pre-registration version (design history only; not a fixed input of v0.3)'
        name = rel.rsplit('/', 1)[-1]
        if rel.startswith('e5/m1/rules_') and name in (rec.get('tables') or {}):
            row['rules_record'] = rec['tables'][name]
            row['basis'] = '12-③ official-train rebuild (rules_record)'
            row['ok'] = got == rec['tables'][name]
            row['equals_section12_value'] = got == want
        files.append(row)
    out['files'] = files
    out['all_listed_match'] = all(f['ok'] for f in files if f['ok'] is not None)
    out['rule_tables_rebuilt'] = [f['file'] for f in files if 'equals_section12_value' in f and not f['equals_section12_value']]
    out['not_listed'] = [f['file'] for f in files if f['preregistered'] is None and not f['file'].startswith('history/')]
    out['history'] = [f['file'] for f in files if f['file'].startswith('history/')]
    return out


# ------------------------------------------------------------------ intervals

class Boot:
    def __init__(self, J):
        self.seed = J['bootstrap']['seed']
        self.B = int(J['bootstrap']['n'])
        self.pct = J['bootstrap']['percentiles']

    def _idx(self, name, k):
        h = hashlib.sha256(f'{self.seed}|{name}'.encode()).digest()
        return np.random.default_rng(int.from_bytes(h[:8], 'big')).integers(0, k, size=(self.B, k))

    @staticmethod
    def cp_edge(x, n):
        a = 0.05
        if x == 0:
            return 0.0, 1 - (a / 2) ** (1 / n)
        return (a / 2) ** (1 / n), 1.0

    def prop(self, name, clusters):
        """clusters = list of (successes, trials) in a fixed order."""
        x = sum(c[0] for c in clusters)
        n = sum(c[1] for c in clusters)
        if n == 0:
            return dict(x=0, n=0, p=None, lo=None, hi=None, method=None, clusters=0)
        if x == 0 or x == n:
            lo, hi = self.cp_edge(x, n)
            return dict(x=x, n=n, p=x / n, lo=lo, hi=hi, method='clopper-pearson', clusters=len(clusters))
        num = np.array([c[0] for c in clusters], dtype=float)
        den = np.array([c[1] for c in clusters], dtype=float)
        idx = self._idx(name, len(clusters))
        st = num[idx].sum(axis=1) / den[idx].sum(axis=1)
        lo, hi = np.percentile(st, self.pct)
        return dict(x=x, n=n, p=x / n, lo=float(lo), hi=float(hi), method='bootstrap', clusters=len(clusters))

    def diff(self, name, clusters):
        """clusters = list of (successes A, successes B, trials); A - B."""
        n = sum(c[2] for c in clusters)
        if n == 0:
            return dict(num=None, n=0, diff=None, lo=None, hi=None, clusters=0)
        a = np.array([c[0] for c in clusters], dtype=float)
        b = np.array([c[1] for c in clusters], dtype=float)
        d = np.array([c[2] for c in clusters], dtype=float)
        idx = self._idx(name, len(clusters))
        st = (a[idx].sum(axis=1) - b[idx].sum(axis=1)) / d[idx].sum(axis=1)
        lo, hi = np.percentile(st, self.pct)
        num = int(a.sum() - b.sum())
        return dict(num=num, n=n, diff=num / n, lo=float(lo), hi=float(hi), clusters=len(clusters))


def clusters_by(rows, key, val):
    """Group rows (in their order) by key; each cluster = (sum of val, count)."""
    g = OrderedDict()
    for r in rows:
        g.setdefault(key(r), []).append(r)
    return [(sum(int(val(r)) for r in v), len(v)) for v in g.values()], g


def frac(c):
    return F(c['x'], c['n']) if c and c.get('n') else None


# ------------------------------------------------------------------ M1 per item

def m1_item(item, rows):
    """Main answer = argmax (first in original order on ties) of the mean over valid permutations of the per-choice
    probabilities (already in original choice order). Human check = the per-permutation top choice is not the same for all
    valid permutations. Failed = no valid permutation. Partial = 0 < valid < min(5, n!)."""
    if not rows:
        return dict(asked=False, failed=True, answer=None)
    per = {}
    for r in rows:
        j = r['perm_index']
        if j not in per or (r['valid'] and not per[j]['valid']):
            per[j] = r
    ok = [per[j] for j in sorted(per) if per[j]['valid']]
    n = len(item['choices'])
    expected = 1
    for i in range(2, n + 1):
        expected *= i
    expected = min(5, expected)
    base = dict(asked=True, n_perm=len(per), n_valid=len(ok), partial=0 < len(ok) < expected,
                missing_perms=sum(1 for r in per.values() if r['missing']))
    if not ok:
        return dict(base, failed=True, answer=None)
    mean = []
    for i in range(n):   # built-in sum (compensated on Python >= 3.12); other versions may differ in the last bit
        mean.append(sum(r['probs'][i] for r in ok) / len(ok))
    best = max(mean)
    main = mean.index(best)
    tops = set()
    for r in ok:
        tops.add(r['probs'].index(max(r['probs'])))
    chosen = [r['probs'][main] for r in ok]
    return dict(base, failed=False, answer=item['choices'][main], mean=mean, prob=mean[main], tie=mean.count(best) > 1,
                human_check=len(tops) > 1, spread=max(chosen) - min(chosen))


# ------------------------------------------------------------------ T1

def t1_answer(method, x, R, M):
    r = R[x['item_id']]
    if method == 'R0':
        return r['r0_full']['answer']
    if method == 'R0-가림':
        return r['r0_masked']['answer']
    if method == 'R1':
        return r['r1']['answer']
    if method == 'M1':
        return M[x['item_id']]['answer']
    if method == 'C':   # composition: rule answer where the rule decided, else M1 (one answer per item)
        return r['r0_full']['answer'] if r['r0_full']['determined'] else M[x['item_id']]['answer']
    raise ValueError(method)


def n_faults(combo_key):
    return len(combo_key.split('|', 1)[0].split('+')) if combo_key else 0


def confusion(bt, rows, ans, name, J):
    out = OrderedDict()
    classes = sorted({x['answer'] for x in rows})
    for t in classes:
        v = [x for x in rows if x['answer'] == t]
        row = dict(n=len(v), counts=dict(sorted(Counter(str(ans(x)) for x in v).items())))
        if len(v) >= J['min_items_for_rate']:
            cl, _ = clusters_by(v, lambda x: x['combo_key'], lambda x: ans(x) == x['answer'])
            row['recall'] = bt.prop(f'{name}|{t}', cl)
        out[t] = row
    return out


def t1(bt, J, ev, R, M, L):
    B = [x for x in ev if x['task'] == 'T1' and x['cell'] == 'B']
    und = [x for x in B if not R[x['item_id']]['r0_full']['determined']]
    det = [x for x in B if R[x['item_id']]['r0_full']['determined']]
    A = lambda m: (lambda x: t1_answer(m, x, R, M))
    methods = ('R0', 'R1', 'M1', 'C', 'R0-가림')
    need_m1 = ('M1', 'C')

    def acc(tag, rows, m):
        if M is None and m in need_m1:
            return NR
        cl, _ = clusters_by(rows, lambda x: x['combo_key'], lambda x: A(m)(x) == x['answer'])
        return bt.prop(f'{L}|{tag}|{m}', cl)

    o = OrderedDict(n_cell_b=len(B), n_undetermined=len(und), n_determined=len(det), undetermined_keys=len({x['combo_key'] for x in und}))
    o['undetermined_acc'] = {m: acc('und', und, m) for m in methods}
    g = OrderedDict()
    for x in und:
        g.setdefault(x['combo_key'], []).append(x)
    o['diff_C_minus_R0'] = NR if M is None else bt.diff(f'{L}|diff', [(sum(A('C')(x) == x['answer'] for x in v), sum(A('R0')(x) == x['answer'] for x in v), len(v)) for v in g.values()])
    o['determined_acc_R0'] = acc('det', det, 'R0')
    o['all_acc'] = {m: acc('all', B, m) for m in methods}
    o['human_check'] = NR if M is None else dict(undetermined=sum(1 for x in und if M[x['item_id']].get('human_check')),
                                                 all_m1=sum(1 for x in B if M[x['item_id']].get('human_check')))
    risk = OrderedDict()
    for cls in J['risk4']:
        pos = [x for x in B if x['answer'] == cls]
        neg = [x for x in B if x['answer'] != cls]
        row = OrderedDict(n_pos=len(pos), n_neg=len(neg))
        for m in ('C', 'R0', 'M1'):
            if M is None and m in need_m1:
                row[m] = NR
                continue
            tp = sum(A(m)(x) == cls for x in pos)
            fp = sum(A(m)(x) == cls for x in neg)
            row[m] = OrderedDict(tp=tp, fn=len(pos) - tp, fp=fp, tn=len(neg) - fp)
            if len(pos) >= J['min_items_for_rate']:
                cl, _ = clusters_by(pos, lambda x: x['combo_key'], lambda x, m=m: A(m)(x) == cls)
                row[m]['recall'] = bt.prop(f'{L}|risk|{cls}|{m}', cl)
            row[m]['missed'] = [x['window_id'] for x in pos if A(m)(x) != cls]
        risk[cls] = row
    o['risk4'] = risk
    o['confusion'] = {m: NR if M is None and m in need_m1 else confusion(bt, B, A(m), f'{L}|conf|{m}', J) for m in ('C', 'M1', 'R0')}
    o['confusion_by_split'] = {sp: {m: NR if M is None and m in need_m1 else confusion(bt, [x for x in B if x['split'] == sp], A(m), f'{L}|conf|{sp}|{m}', J)
                                    for m in ('C', 'M1', 'R0')}
                               for sp in sorted({x['split'] for x in B})}
    seen = [x for x in B if x['split'] == 'test_seen']
    grp = OrderedDict()
    for x in seen:
        k = 'single' if n_faults(x['combo_key']) <= 1 else f"{n_faults(x['combo_key'])}faults"
        grp.setdefault(k, []).append(x)
    o['test_seen_by_faults'] = {k: dict({m: acc(f'seen|{k}', v, m) for m in ('C', 'R0', 'M1')}, n=len(v)) for k, v in sorted(grp.items())}
    # verdict (pre-registration section 8, T1 rows) — exact fractions
    T = J['T1']
    d = o['diff_C_minus_R0']
    r0 = frac(o['undetermined_acc']['R0'])
    if o['n_undetermined'] < T['min_items'] or o['undetermined_keys'] < T['min_keys']:
        v = '판정 보류'
    elif M is None:
        v = NR                      # the T1 verdict needs composition C (M1 answers)
    elif d['num'] is not None and F(d['num'], d['n']) >= F(T['gain']) and d['lo'] > 0:
        v = '모델이 보탠다'
    elif r0 is not None and r0 >= F(T['rule_ok']):
        v = '규칙으로 충분'
    else:
        v = '둘 다 미달'
    o['verdict'] = v
    return o


# ------------------------------------------------------------------ T2 · T4

def t2_successors(items):
    """Allowed next recovery steps, read from the data itself: every (current_step -> next_step) pair that occurs as a
    label anywhere in the item set (all splits). Pre-registration 12-④: a T2 answer is dangerous if it names a step the
    recovery table cannot reach from the current step, or answers 3 (finishing push, refused by the PLC) when the truth is 4."""
    s = {}
    for x in items:
        if x['task'] == 'T2':
            s.setdefault(x['current_step'], set()).add(x['next_step'])
    return s


def dangerous(x, a, succ):
    """T4: the true first event is a safety event (grade 1) and another event was put first.
    T2: unreachable next step, or 3 when the truth is 4. A missing answer (failed M1 item) counts as wrong; for T2 it is
    treated as unreachable."""
    if a == x['answer']:
        return False
    if x['task'] == 'T4':
        return x['grades'].get(x['answer']) == SAFETY_GRADE
    if a is None:
        return True
    p = int(a.split(' ', 1)[0])
    return p not in succ.get(x['current_step'], set()) or (x['next_step'] == 4 and p == 3)


def consistency(bt, J, ev, R, M, task, L, succ):
    C = J['consistency_T2_T4']
    rows = [x for x in ev if x['task'] == task]
    cl0, _ = clusters_by(rows, lambda x: x['combo_key'], lambda x: R[x['item_id']]['r0']['answer'] == x['answer'])
    r0 = bt.prop(f'{L}|{task}|R0', cl0)
    if M is not None:
        cl1, _ = clusters_by(rows, lambda x: x['combo_key'], lambda x: M[x['item_id']]['answer'] == x['answer'])
        m1 = bt.prop(f'{L}|{task}|M1', cl1)
    dz = [x['window_id'] for x in rows if dangerous(x, R[x['item_id']]['r0']['answer'], succ)]
    dz1 = NR if M is None else sum(1 for x in rows if M[x['item_id']]['asked'] and dangerous(x, M[x['item_id']]['answer'], succ))
    cells = sorted({x['cell'] for x in rows})
    by_cell = {c: f"{sum(R[x['item_id']]['r0']['answer'] == x['answer'] for x in rows if x['cell'] == c)}/{sum(1 for x in rows if x['cell'] == c)}" for c in cells}
    if len(rows) < C['min_items']:
        v = '판정 보류'
    elif frac(r0) >= F(C['acc']) and len(dz) <= C['dangerous_max']:
        v = '[PASS]'
    else:
        v = '[FAIL]'
    return OrderedDict(n=len(rows), r0=r0, r0_dangerous=len(dz), r0_dangerous_windows=dz,
                       r0_fallback=sum(1 for x in rows if R[x['item_id']]['r0'].get('fallback')), r0_by_cell=by_cell,
                       m1=NR if M is None else m1, m1_dangerous=dz1,
                       m1_answered=NR if M is None else sum(1 for x in rows if M[x['item_id']]['asked']), verdict=v)


# ------------------------------------------------------------------ T3

def t3_rows(J, rows):
    lead = F(str(J['T3']['lead_s']))
    return [x for x in rows if x['task'] == 'T3' and (x['lead_s'] is None or F(str(x['lead_s'])) >= lead)]


def units(rows, flag):
    """Pre-registration 7-4: positive unit = run with at least one 'maintenance needed' window (TP if any of its positive
    windows is flagged); negative unit = run whose windows are all negative (FP if any is flagged). Flags on negative windows
    of a positive run are 'early alarms' (counted, not judged)."""
    runs = {}
    for x in rows:
        runs.setdefault(x['run_id'], []).append(x)
    out = []
    for rid in sorted(runs):
        v = runs[rid]
        pos = [x for x in v if x['answer'] == MAINT]
        neg = [x for x in v if x['answer'] != MAINT]
        u = dict(run_id=rid, combo_key=v[0]['combo_key'], pos=bool(pos), neg=not pos, mixed=bool(pos) and bool(neg),
                 tp=bool(pos) and any(flag(x) for x in pos), fp=(not pos) and any(flag(x) for x in neg),
                 early=sum(1 for x in neg if flag(x)) if pos else 0,
                 channels=sorted({c for x in pos for c in x['maint_channels']}),
                 no_alert=all(x['lead_s'] is None for x in v))
        out.append(u)
    return out


def m1_maint_score(x, M):
    m = M[x['item_id']]
    return None if m['failed'] else m['mean'][x['choices'].index(MAINT)]


def threshold(J, vrows, M):
    """Highest distinct val score whose val run-level recall >= val_recall (exact fraction)."""
    target = F(J['val_recall'])
    if not any(x['answer'] == MAINT for x in vrows):
        return None, 0
    cands = sorted({s for s in (m1_maint_score(x, M) for x in vrows) if s is not None}, reverse=True)
    for t in cands:
        u = units(vrows, lambda x, t=t: (m1_maint_score(x, M) if m1_maint_score(x, M) is not None else -1.0) >= t)
        pos = [z for z in u if z['pos']]
        if pos and F(sum(z['tp'] for z in pos), len(pos)) >= target:
            return t, len(pos)
    return None, len([z for z in units(vrows, lambda x: False) if z['pos']])


def t3(bt, J, ev, val, R, M, L):
    rows = t3_rows(J, ev)
    vrows = t3_rows(J, val)
    thr, val_pos = threshold(J, vrows, M) if M is not None else (NR, NR)
    f0 = lambda x: R[x['item_id']]['r0_t3']['answer'] == MAINT
    f1 = (lambda x: False) if M is None else (lambda x: (m1_maint_score(x, M) if m1_maint_score(x, M) is not None else -1.0) >= thr) if thr is not None else (lambda x: False)
    u0, u1 = units(rows, f0), units(rows, f1)
    u1_all = u1

    def rate(us, kind, name):
        if M is None and us is u1_all:
            return NR
        return bt.prop(name, [(int(u['tp']), 1) for u in us if u['pos']] if kind == 'recall' else [(int(u['fp']), 1) for u in us if u['neg']])

    o = OrderedDict(n_windows=len(rows), excluded_short_lead=sum(1 for x in ev if x['task'] == 'T3') - len(rows),
                    threshold=thr, threshold_val_pos_runs=val_pos,
                    n_pos_runs=sum(u['pos'] for u in u0), n_neg_runs=sum(u['neg'] for u in u0), mixed_runs=sum(u['mixed'] for u in u0),
                    early_alarms=dict(r0=sum(u['early'] for u in u0), m1=NR if M is None else sum(u['early'] for u in u1)),
                    channel_pos_runs={c: sum(1 for u in u0 if u['pos'] and c in u['channels']) for c in ('belt_speed_dev', 'chatter', 'stroke_ratio')})
    o['r0'] = dict(recall=rate(u0, 'recall', f'{L}|t3|r0|rec'), fpr=rate(u0, 'fpr', f'{L}|t3|r0|fpr'),
                   unknown=sum(1 for x in rows if R[x['item_id']]['r0_t3']['answer'] == '모름'))
    o['m1'] = dict(recall=rate(u1, 'recall', f'{L}|t3|m1|rec'), fpr=rate(u1, 'fpr', f'{L}|t3|m1|fpr'))
    o['lead_s_maint'] = sorted([x['lead_s'] for x in rows if x['answer'] == MAINT], key=lambda v: (v is None, v or 0))
    o['m1_level_acc'] = NR if M is None else bt.prop(f'{L}|t3|m1|acc', [(int(M[x['item_id']]['answer'] == x['answer']), 1) for x in rows])
    o['r0_level_acc'] = bt.prop(f'{L}|t3|r0|acc', [(int(R[x['item_id']]['r0_t3']['answer'] == x['answer']), 1) for x in rows])
    for ch in J['T3']['channels']:
        o[f'r0_recall_{ch}'] = rate([u for u in u0 if ch in u['channels']], 'recall', f'{L}|t3|r0|{ch}')
        o[f'm1_recall_{ch}'] = NR if M is None else rate([u for u in u1 if ch in u['channels']], 'recall', f'{L}|t3|m1|{ch}')
    solo = lambda u: u['pos'] and u['combo_key'].split('|')[0] == 'D.belt' and u['no_alert']
    o['belt_solo_plc_unaware'] = dict(n=sum(map(solo, u0)), r0_tp=sum(1 for u in u0 if solo(u) and u['tp']), m1_tp=NR if M is None else sum(1 for u in u1 if solo(u) and u['tp']))
    n0 = {u['run_id']: u for u in u0 if u['neg']}
    n1 = {u['run_id']: u for u in u1 if u['neg']}
    o['fpr_diff_R0_minus_M1'] = NR if M is None else bt.diff(f'{L}|t3|fprdiff', [(int(n0[k]['fp']), int(n1[k]['fp']), 1) for k in sorted(n0)])
    # truncation cross-check: the rule baseline must have read the same (possibly truncated) record as the model
    mism = [x['window_id'] for x in rows
            if (x['input_sha256'] is not None if M is None else M[x['item_id']]['asked']) and ((R[x['item_id']]['r0_t3'].get('dropped_lines') or 0) != x['dropped_lines']
                                             or R[x['item_id']]['r0_t3'].get('record_sha256') != x['input_sha256'])]
    o['truncation_mismatch'] = mism
    o['truncated_windows'] = sum(1 for x in rows if R[x['item_id']]['r0_t3'].get('dropped_lines'))
    # verdict (section 8, T3 row; "rule suffices" wins when both hold — section 6-4)
    T = J['T3']
    cp = o['channel_pos_runs']
    r0r, r0f = frac(o['r0']['recall']), frac(o['r0']['fpr'])
    m1r, m1f = (None, None) if M is None else (frac(o['m1']['recall']), frac(o['m1']['fpr']))
    d = o['fpr_diff_R0_minus_M1']
    if mism:
        v = '실행 무효'
    elif o['n_pos_runs'] < T['min_pos_runs'] or any(cp[c] < T['min_channel_runs'] for c in T['channels']):
        v = '판정 보류'
    elif r0r is not None and r0r >= F(T['recall']) and r0f is not None and r0f <= F(T['fpr']):
        v = '규칙으로 충분'
    elif M is None:
        v = NR                      # only "rule suffices" or "hold" can be decided without M1
    elif (thr is not None and m1r is not None and m1r >= F(T['recall']) and m1f is not None and r0f is not None and m1f < r0f
          and d['lo'] is not None and d['lo'] > 0):
        v = '모델이 보탠다'
    else:
        v = '둘 다 미달'
    o['verdict'] = v
    return o


# ------------------------------------------------------------------ all

def m1_status(J, ev, R, M):
    judged = [x for x in ev if x['task'] == 'T1' and x['cell'] == 'B' and not R[x['item_id']]['r0_full']['determined']] + t3_rows(J, ev)
    if M is None:
        o = OrderedDict((k, NR) for k in ('items_with_m1', 'judged_failed', 'run_invalid', 'all_sent_failed', 'partial_failed', 'missing_perms',
                                          'missing_items', 'human_check', 'ties', 'confident_wrong', 'spread_quantiles', 'prob_quantiles'))
        o.update(judged_items=len(judged), all_sent=len(ev),
                 truncated_items=sum(1 for x in ev if x['input_sha256'] is not None and x['truncated']))
        return o
    asked = [x for x in ev if M[x['item_id']]['asked']]
    ok = [x for x in asked if not M[x['item_id']]['failed']]
    fails = sum(1 for x in judged if M[x['item_id']]['failed'])
    cw = F(J['confident_wrong_prob'])
    return OrderedDict(items_with_m1=len(asked), judged_items=len(judged), judged_failed=fails,
                       run_invalid=bool(judged) and F(fails, len(judged)) > F(J['fail_rate_max']),
                       all_sent=len(ev), all_sent_failed=sum(1 for x in ev if M[x['item_id']]['failed']),
                       partial_failed=sum(1 for x in ev if M[x['item_id']].get('partial')),
                       missing_perms=sum(M[x['item_id']].get('missing_perms', 0) for x in asked),
                       missing_items=sum(1 for x in asked if M[x['item_id']].get('missing_perms')),
                       truncated_items=sum(1 for x in asked if x['truncated']),
                       human_check=sum(1 for x in ok if M[x['item_id']]['human_check']),
                       ties=sum(1 for x in ok if M[x['item_id']]['tie']),
                       confident_wrong=sum(1 for x in ok if M[x['item_id']]['answer'] != x['answer'] and F(M[x['item_id']]['prob']) >= cw),
                       spread_quantiles=[float(v) for v in np.percentile([M[x['item_id']]['spread'] for x in ok], [0, 25, 50, 75, 100])],
                       prob_quantiles=[float(v) for v in np.percentile([M[x['item_id']]['prob'] for x in ok], [0, 25, 50, 75, 100])])


def compute():
    J, items, R, P = load()
    bt = Boot(J)
    M = None if P is None else {x['item_id']: m1_item(x, P.get(x['item_id'], [])) for x in items}
    succ = t2_successors(items)
    ev = [x for x in items if x['split'] in EVAL]
    val = [x for x in items if x['split'] == 'val']
    L = '+'.join(EVAL)
    out = OrderedDict(eval_splits=list(EVAL), val_split='val', n_items=len(ev))
    out['t2_successors_from_data'] = {str(k): sorted(v) for k, v in sorted(succ.items())}
    out['m1_status'] = m1_status(J, ev, R, M)
    out['T1'] = t1(bt, J, ev, R, M, L)
    out['T1_counts_AP'] = {c: dict(n=sum(1 for x in ev if x['task'] == 'T1' and x['cell'] == c),
                                   r0_correct=sum(1 for x in ev if x['task'] == 'T1' and x['cell'] == c and R[x['item_id']]['r0_full']['answer'] == x['answer']),
                                   m1_correct=NR if M is None else sum(1 for x in ev if x['task'] == 'T1' and x['cell'] == c and M[x['item_id']]['answer'] == x['answer']),
                                   m1_answered=NR if M is None else sum(1 for x in ev if x['task'] == 'T1' and x['cell'] == c and M[x['item_id']]['asked']))
                           for c in ('A', 'P')}
    out['T2'] = consistency(bt, J, ev, R, M, 'T2', L, succ)
    out['T4'] = consistency(bt, J, ev, R, M, 'T4', L, succ)
    out['T3'] = t3(bt, J, ev, val, R, M, L)
    un = [x for x in ev if x['split'] == 'test_unseen']
    Lu = L + '|unseen'
    out['test_unseen'] = OrderedDict(T1=t1(bt, J, un, R, M, Lu), T2=consistency(bt, J, un, R, M, 'T2', Lu, succ),
                                     T4=consistency(bt, J, un, R, M, 'T4', Lu, succ), T3=t3(bt, J, un, val, R, M, Lu))
    out['verdicts'] = {k: out[k]['verdict'] for k in ('T1', 'T2', 'T4', 'T3')}
    if M is None:
        out['missed_or_wrong_m1_count'] = NR
        return out, None
    wrong = [dict(window_id=x['window_id'], task=x['task'], truth=x['answer'], m1=M[x['item_id']]['answer'],
                  prob=M[x['item_id']].get('prob'), human_check=M[x['item_id']].get('human_check'))
             for x in ev if M[x['item_id']]['asked'] and M[x['item_id']]['answer'] != x['answer']]
    out['missed_or_wrong_m1_count'] = dict(all=len(wrong), **{t: sum(1 for w in wrong if w['task'] == t) for t in ('T1', 'T2', 'T3', 'T4')})
    if out['m1_status']['run_invalid']:
        out['verdicts'] = {k: '실행 무효' for k in out['verdicts']}
    return out, wrong


# ------------------------------------------------------------------ comparison with results/score.json

INTERVAL_KEYS = ('lo', 'hi', 'p', 'diff')
CHECK_ONLY = ('t2_successors_from_data', 'threshold_val_pos_runs', 'missed_or_wrong_m1_count')   # fields the check adds; not in score.json


def compare(mine, theirs):
    """Walk both trees. Every key the check computes is compared: integers, strings, lists and verdicts must be equal;
    interval end points (lo, hi) and rates (p, diff) are compared numerically and reported with their absolute difference."""
    exact, interval, not_run = [], [], []

    def tv(x):
        return x['verdict'] if isinstance(x, dict) and 'verdict' in x else x

    def walk(a, b, path):
        if a == NR:
            not_run.append(path)
            return
        if path.endswith('.verdict') or path.split('.')[-1] in ('T1', 'T2', 'T3', 'T4') and path.startswith('verdicts'):
            exact.append((path, tv(a), tv(b)))
            return
        if isinstance(a, dict):
            if not isinstance(b, dict):
                exact.append((path, 'dict', type(b).__name__))
                return
            for k in a:
                if k in CHECK_ONLY:
                    continue
                if k not in b:
                    exact.append((f'{path}.{k}', 'present', 'missing'))
                    continue
                walk(a[k], b[k], f'{path}.{k}' if path else k)
            return
        key = path.split('.')[-1]
        if key in INTERVAL_KEYS or key == 'threshold' or path.endswith('quantiles'):
            interval.append((path, a, b))
            return
        exact.append((path, a, b))

    walk(mine, theirs, '')
    ex_bad = [dict(path=p, check=a, score=b) for p, a, b in exact if a != b]

    def num_diff(a, b):
        if a is None or b is None:
            return 0.0 if a is b else float('inf')
        if isinstance(a, list):
            return max([abs(x - y) for x, y in zip(a, b)] + [0.0]) if len(a) == len(b) else float('inf')
        return abs(a - b)
    iv = [(p, num_diff(a, b), a, b) for p, a, b in interval]
    iv_bad = [dict(path=p, abs_diff=d, check=a, score=b) for p, d, a, b in iv if d != 0.0]
    return dict(not_run=len(not_run), not_run_paths=not_run, exact_compared=len(exact), exact_mismatches=ex_bad, interval_compared=len(iv), interval_identical=sum(1 for _, d, _, _ in iv if d == 0.0),
                interval_max_abs_diff=max([d for _, d, _, _ in iv] + [0.0]), interval_differences=iv_bad)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=None, help='default results/check_output.json (full) or results/check_output_repo.json (repository mode)')
    a = ap.parse_args()
    full = (RES / 'm1_perms.jsonl.gz').exists()
    mode = 'full' if full else 'repository (m1_perms.jsonl.gz absent)'
    out_path = a.out or str(RES / ('check_output.json' if full else 'check_output_repo.json'))
    print(f'mode: {mode}')
    fx = fixed_hash_check()
    out, wrong = compute()
    score = json.loads((RES / 'score.json').read_text(encoding='utf-8'))
    cmp = compare(out, score)
    # the per-item list of M1 misses (score.json: missed_or_wrong_m1) is compared entry by entry, not stored again
    cmp['missed_or_wrong_m1'] = NR if wrong is None else dict(check=len(wrong), score=len(score['missed_or_wrong_m1']), identical=wrong == score['missed_or_wrong_m1'])
    if wrong is not None and not cmp['missed_or_wrong_m1']['identical']:
        cmp['exact_mismatches'].append(dict(path='missed_or_wrong_m1', check=len(wrong), score=len(score['missed_or_wrong_m1'])))
    res = OrderedDict(schema='tr08-check.v1', mode=mode,
                      inputs={p: sha256_file(RES / p) if (RES / p).exists() else NR
                              for p in ('items.jsonl.gz', 'rules_pred.jsonl.gz', 'm1_perms.jsonl.gz', 'score.json')},
                      fixed_hash_check=fx, result=out, comparison_with_score_json=cmp,
                      summary=dict(verdicts=out['verdicts'], score_json_verdicts={k: v['verdict'] for k, v in score['verdicts'].items()},
                                   mode=mode, not_run_fields=cmp['not_run'],
                                   all_counts_and_verdicts_equal=not cmp['exact_mismatches'],
                                   intervals_identical=cmp['interval_identical'] == cmp['interval_compared'],
                                   interval_max_abs_diff=cmp['interval_max_abs_diff'],
                                   fixed_inputs_match_preregistration=fx['preregistration']['ok'] and fx['all_listed_match']))
    Path(out_path).write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    s = res['summary']
    print(json.dumps(s, ensure_ascii=False, indent=1))
    print(f"exact compared {cmp['exact_compared']} · mismatches {len(cmp['exact_mismatches'])} · intervals compared {cmp['interval_compared']} · identical {cmp['interval_identical']}")
    for m in cmp['exact_mismatches'][:20]:
        print('MISMATCH', m)
    for m in cmp['interval_differences'][:20]:
        print('INTERVAL', m)


if __name__ == '__main__':
    main()
