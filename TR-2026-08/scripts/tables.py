#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WACE Inc.
"""TR-2026-08 report tables — the numbers of the report's verdict table, T1 detail, T3 detail, M1-alone reference and the
separate test_unseen report, recomputed from the public results/ with the independent check (scripts/check.py).

Usage : python3 scripts/tables.py [--out results/tables.json]
Needs : Python 3.10+ standard library + numpy (through check.py), and results/m1_perms.jsonl.gz (Zenodo record only);
        without it the script prints a note and exits 0 without writing.
Every proportion is given as x, n, p and its 95 % interval (lo, hi) plus a ready-made text "x/n = p [lo, hi]".
"""
import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True   # keep the bundle free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check as C  # noqa: E402


def txt(c, nd=3):
    if not c or c.get('n') in (0, None):
        return '—'
    return f"{c['x']}/{c['n']} = {c['p']:.{nd}f} [{c['lo']:.{nd}f}, {c['hi']:.{nd}f}]"


def prop(c):
    return OrderedDict(x=c['x'], n=c['n'], p=c['p'], lo=c['lo'], hi=c['hi'], method=c['method'], clusters=c['clusters'], text=txt(c))


def diff(d, nd=3):
    return OrderedDict(num=d['num'], n=d['n'], diff=d['diff'], lo=d['lo'], hi=d['hi'], clusters=d['clusters'],
                       text=f"{d['num']}/{d['n']} = {d['diff']:.{nd}f} [{d['lo']:.{nd}f}, {d['hi']:.{nd}f}]")


def quantiles(v):
    v = [x for x in v if x is not None]
    if not v:
        return None
    q = np.percentile(v, [0, 25, 50, 75, 100])
    return OrderedDict(n=len(v), min=float(q[0]), q1=float(q[1]), median=float(q[2]), q3=float(q[3]), max=float(q[4]))


def verdict_table(o, J):
    t1, t2, t4, t3 = o['T1'], o['T2'], o['T4'], o['T3']
    return [
        OrderedDict(task='T1', verdict=t1['verdict'],
                    basis=OrderedDict(undetermined_items=t1['n_undetermined'], undetermined_keys=t1['undetermined_keys'],
                                      min_items=J['T1']['min_items'], min_keys=J['T1']['min_keys'],
                                      r0_undetermined=prop(t1['undetermined_acc']['R0']), rule_ok=J['T1']['rule_ok'],
                                      c_undetermined=prop(t1['undetermined_acc']['C']),
                                      c_minus_r0=diff(t1['diff_C_minus_R0']), gain=J['T1']['gain'])),
        OrderedDict(task='T2', verdict=t2['verdict'],
                    basis=OrderedDict(items=t2['n'], r0=prop(t2['r0']), dangerous=t2['r0_dangerous'], acc=J['consistency_T2_T4']['acc'],
                                      min_items=J['consistency_T2_T4']['min_items'])),
        OrderedDict(task='T4', verdict=t4['verdict'],
                    basis=OrderedDict(items=t4['n'], r0=prop(t4['r0']), dangerous=t4['r0_dangerous'], r1_fallback=t4['r0_fallback'],
                                      acc=J['consistency_T2_T4']['acc'], min_items=J['consistency_T2_T4']['min_items'])),
        OrderedDict(task='T3', verdict=t3['verdict'],
                    basis=OrderedDict(pos_runs=t3['n_pos_runs'], neg_runs=t3['n_neg_runs'], channel_pos_runs=t3['channel_pos_runs'],
                                      min_pos_runs=J['T3']['min_pos_runs'], min_channel_runs=J['T3']['min_channel_runs'],
                                      r0_recall=prop(t3['r0']['recall']), r0_fpr=prop(t3['r0']['fpr']),
                                      m1_recall=prop(t3['m1']['recall']), m1_fpr=prop(t3['m1']['fpr']),
                                      recall_line=J['T3']['recall'], fpr_line=J['T3']['fpr'])),
    ]


def t1_detail(t):
    methods = ('R0', 'R1', 'M1', 'C', 'R0-가림')
    risk = OrderedDict()
    for cls, r in t['risk4'].items():
        risk[cls] = OrderedDict(n_pos=r['n_pos'])
        for m in ('C', 'R0', 'M1'):
            risk[cls][m] = OrderedDict(tp=r[m]['tp'], fn=r[m]['fn'], fp=r[m]['fp'], recall=prop(r[m]['recall']) if 'recall' in r[m] else None,
                                       missed=r[m]['missed'])
    conf = OrderedDict()
    for m, rows in t['confusion'].items():
        conf[m] = OrderedDict((cls, OrderedDict(n=v['n'], counts=v['counts'], recall=prop(v['recall']) if 'recall' in v else None)) for cls, v in rows.items())
    conf_split = OrderedDict()
    for sp, mm in t['confusion_by_split'].items():
        conf_split[sp] = OrderedDict((m, OrderedDict((cls, OrderedDict(n=v['n'], counts=v['counts'], recall=prop(v['recall']) if 'recall' in v else None))
                                                     for cls, v in rows.items())) for m, rows in mm.items())
    return OrderedDict(
        cell_b_items=t['n_cell_b'], undetermined=t['n_undetermined'], undetermined_keys=t['undetermined_keys'], determined=t['n_determined'],
        accuracy=[OrderedDict(method=m, undetermined=prop(t['undetermined_acc'][m]), all_cell_b=prop(t['all_acc'][m])) for m in methods],
        c_minus_r0_undetermined=diff(t['diff_C_minus_R0']),
        determined_r0=prop(t['determined_acc_R0']),
        m1_human_check=t['human_check'],
        risk4=risk,
        test_seen_by_number_of_faults=OrderedDict((k, OrderedDict(n=v['n'], **{m: prop(v[m]) for m in ('C', 'R0', 'M1')}))
                                                  for k, v in t['test_seen_by_faults'].items()),
        confusion=conf, confusion_by_split=conf_split)


def t3_detail(t, J):
    out = OrderedDict(
        windows=t['n_windows'], excluded_short_lead=t['excluded_short_lead'], lead_s_min=J['T3']['lead_s'],
        pos_runs=t['n_pos_runs'], neg_runs=t['n_neg_runs'], mixed_runs=t['mixed_runs'],
        channel_pos_runs=t['channel_pos_runs'],
        m1_threshold=t['threshold'], m1_threshold_val_pos_runs=t['threshold_val_pos_runs'], val_recall_target=J['val_recall'],
        methods=[OrderedDict(method='R0-T3', recall=prop(t['r0']['recall']), fpr=prop(t['r0']['fpr']), level_acc=prop(t['r0_level_acc']),
                             **{f'recall_{ch}': prop(t[f'r0_recall_{ch}']) for ch in J['T3']['channels']}),
                 OrderedDict(method='M1', recall=prop(t['m1']['recall']), fpr=prop(t['m1']['fpr']), level_acc=prop(t['m1_level_acc']),
                             **{f'recall_{ch}': prop(t[f'm1_recall_{ch}']) for ch in J['T3']['channels']})],
        fpr_diff_r0_minus_m1=diff(t['fpr_diff_R0_minus_M1']),
        early_alarms=t['early_alarms'], r0_unknown=t['r0']['unknown'],
        belt_solo_plc_unaware=t['belt_solo_plc_unaware'],
        lead_s_maint=OrderedDict(windows=len(t['lead_s_maint']), no_alert_until_end=sum(1 for v in t['lead_s_maint'] if v is None),
                                 with_lead=quantiles(t['lead_s_maint'])),
        truncated_windows=t['truncated_windows'], truncation_mismatch=len(t['truncation_mismatch']))
    return out


def m1_alone(o, M, items, R):
    ev = [x for x in items if x['split'] in C.EVAL]
    per_task = OrderedDict()
    for task in ('T1', 'T2', 'T3', 'T4'):
        rows = [x for x in ev if x['task'] == task and M[x['item_id']]['asked']]
        ok = [x for x in rows if not M[x['item_id']]['failed']]
        per_task[task] = OrderedDict(items=len(rows), correct=sum(1 for x in ok if M[x['item_id']]['answer'] == x['answer']),
                                     human_check=sum(1 for x in ok if M[x['item_id']]['human_check']),
                                     confident_wrong=sum(1 for x in ok if M[x['item_id']]['answer'] != x['answer'] and M[x['item_id']]['prob'] >= 0.9),
                                     choices=sorted({len(x['choices']) for x in rows}))
    s = o['m1_status']
    return OrderedDict(
        note='M1 alone is measured on every task but enters a verdict only through composition C (T1) and the T3 model condition. '
             'per_task counts every evaluated item M1 answered (T3 includes the 3 windows excluded by the 5 s lead rule; the T3 rates use the 412 kept windows).',
        t1_cell_b_undetermined=prop(o['T1']['undetermined_acc']['M1']), t1_cell_b_all=prop(o['T1']['all_acc']['M1']),
        t1_cells_A_P=o['T1_counts_AP'],
        t2=OrderedDict(acc=prop(o['T2']['m1']), dangerous=o['T2']['m1_dangerous'], answered=o['T2']['m1_answered']),
        t4=OrderedDict(acc=prop(o['T4']['m1']), dangerous=o['T4']['m1_dangerous'], answered=o['T4']['m1_answered']),
        t3=OrderedDict(recall=prop(o['T3']['m1']['recall']), fpr=prop(o['T3']['m1']['fpr']), level_acc=prop(o['T3']['m1_level_acc']),
                       threshold=o['T3']['threshold']),
        per_task=per_task,
        status=OrderedDict((k, s[k]) for k in ('items_with_m1', 'judged_items', 'judged_failed', 'run_invalid', 'partial_failed', 'missing_perms',
                                               'truncated_items', 'human_check', 'ties', 'confident_wrong', 'spread_quantiles', 'prob_quantiles')))


def unseen(u):
    t1, t3 = u['T1'], u['T3']
    return OrderedDict(
        T1=OrderedDict(verdict_if_alone=t1['verdict'], cell_b=t1['n_cell_b'], undetermined=t1['n_undetermined'], undetermined_keys=t1['undetermined_keys'],
                       accuracy=[OrderedDict(method=m, undetermined=prop(t1['undetermined_acc'][m]), all_cell_b=prop(t1['all_acc'][m]))
                                 for m in ('R0', 'R1', 'M1', 'C', 'R0-가림')],
                       c_minus_r0=diff(t1['diff_C_minus_R0']), determined_r0=prop(t1['determined_acc_R0']),
                       risk4={c: {m: dict(tp=r[m]['tp'], fn=r[m]['fn'], fp=r[m]['fp']) for m in ('C', 'R0', 'M1')} | {'n_pos': r['n_pos']}
                              for c, r in t1['risk4'].items()}),
        T2=OrderedDict(items=u['T2']['n'], r0=prop(u['T2']['r0']), dangerous=u['T2']['r0_dangerous'], m1=prop(u['T2']['m1'])),
        T4=OrderedDict(items=u['T4']['n'], r0=prop(u['T4']['r0']), dangerous=u['T4']['r0_dangerous'], m1=prop(u['T4']['m1'])),
        T3=OrderedDict(windows=t3['n_windows'], pos_runs=t3['n_pos_runs'], neg_runs=t3['n_neg_runs'], channel_pos_runs=t3['channel_pos_runs'],
                       r0_recall=prop(t3['r0']['recall']), r0_fpr=prop(t3['r0']['fpr']), m1_recall=prop(t3['m1']['recall']), m1_fpr=prop(t3['m1']['fpr']),
                       verdict_if_alone=t3['verdict']))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=str(C.RES / 'tables.json'))
    a = ap.parse_args()
    J, items, R, P = C.load()
    if P is None:
        print('repository mode: results/m1_perms.jsonl.gz is absent (it is in the Zenodo record only). The report tables need M1 '
              'probabilities; results/tables.json was made in full mode. The rule-side numbers are recomputed by scripts/check.py '
              '(results/check_output_repo.json). Nothing written.')
        return
    M = {x['item_id']: C.m1_item(x, P.get(x['item_id'], [])) for x in items}
    o, _ = C.compute()
    tabs = OrderedDict(
        schema='tr08-tables.v1',
        source='results/items.jsonl.gz · rules_pred.jsonl.gz · m1_perms.jsonl.gz through scripts/check.py (independent of the official scorer)',
        eval_splits=o['eval_splits'], n_items=o['n_items'],
        verdict_table=verdict_table(o, J),
        t1_detail=t1_detail(o['T1']),
        t2_t4=OrderedDict((k, OrderedDict(items=o[k]['n'], r0=prop(o[k]['r0']), dangerous=o[k]['r0_dangerous'], r1_fallback=o[k]['r0_fallback'],
                                          r0_by_cell=o[k]['r0_by_cell'])) for k in ('T2', 'T4')),
        t3_detail=t3_detail(o['T3'], J),
        m1_alone=m1_alone(o, M, items, R),
        test_unseen=unseen(o['test_unseen']))
    Path(a.out).write_text(json.dumps(tabs, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for r in tabs['verdict_table']:
        print(r['task'], r['verdict'])


if __name__ == '__main__':
    main()
