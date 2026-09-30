#!/usr/bin/env python3
"""TR-2026-03: stage 4 split read literally from the pre-registration (section 5), computed from the result file only.

The pre-registration names stage 4a "hazard events: physical events of the plant model (person-zone motion, drop,
collision, JAM, defective part through the good exit, ...) differ" and 4b "the physical events are the same and the
control verdict differs". The analysis applied interpretation I-3, fixed before the results: 4a = any difference in event
counts by name (production events included) or in the parts' final outcome; non-production ("hazard") differences were
counted separately. This script keeps every stage of the result file and only re-splits the revealed variants:
  run level   4a-literal if the run's non-production event counts differ (`hazard_diff`);
              4b-literal if not, and the run's verdict differs (`judgment_diff` or `status_diff`);
              otherwise the run reveals nothing under the literal reading ("unassigned"; reported, expected 0)
  variant     4a-literal if any revealing run is 4a-literal, else 4b-literal if any is, else unassigned
It also reports three columns the report cites: stage-3 variants whose full final plant-state hash differs in at least
one run, runs whose first event tick moved, and stage-3 runs (event counts equal) whose first event tick moved.
The analysis scripts are not changed. Output is deterministic (no times, no paths).
Usage: reclassify_hazard.py RESULT_JSON OUT_JSON
"""
import json, sys
from collections import Counter

GROUPS = ['안전', '밀기 순서', '출력', '알람', '복귀', '포장 핸드셰이크']
CELLS = ['cell-a', 'cell-b', 'cell-b-pack']
SETS = {'full': lambda k: True, 'no045': lambda k: k != 'flow045'}


def rate(n, d):
    return dict(n=n, d=d, pct=round(100 * n / d, 2) if d else None)


def main(src, out):
    R = json.loads(open(src, encoding='utf-8').read())
    res = {}
    for sname, keep in SETS.items():
        stages = R['sets'][sname]['stages']
        lit, why = {}, {}
        for vid, st in stages.items():
            if st not in ('4a', '4b'):
                lit[vid] = st
                continue
            runs = [r for k, r in R['run_levels'][vid].items() if keep(k) and isinstance(r, dict) and r['level'] in ('4a', '4b')]
            levels = ['4a' if r['hazard_diff'] else '4b' if (r['judgment_diff'] or r['status_diff']) else 'none' for r in runs]
            lit[vid] = '4a' if '4a' in levels else '4b' if '4b' in levels else 'unassigned'
            why[vid] = dict(i3=st, literal=lit[vid])
        dist = {}
        for c in CELLS:
            dist[c] = {}
            for g in GROUPS + ['전체']:
                vs = [v for v, x in R['variants'].items() if x['cell'] == c and (g == '전체' or x['group'] == g)]
                if vs:
                    cnt = Counter(lit[v] for v in vs)
                    dist[c][g] = {s: cnt[s] for s in ('1', '2', '3', '4a', '4b', '보류', 'unassigned')}
        moved = Counter((why[v]['i3'], why[v]['literal']) for v in why)
        res[sname] = dict(distribution=dist, totals=dict(sorted(Counter(lit.values()).items())),
                          i3_to_literal={f'{a}->{b}': n for (a, b), n in sorted(moved.items())},
                          i3_4a_verdict_also_differs=sum(1 for v in why if why[v]['i3'] == '4a' and why[v]['literal'] == '4b'),
                          stages_literal=dict(sorted(lit.items())))
    full = R['sets']['full']['stages']
    s3 = [v for v, s in full.items() if s == '3']
    s3_state = [v for v in s3 if any(isinstance(r, dict) and not r['strict_state_hash_same'] for r in R['run_levels'][v].values())]
    s2_state = [v for v, s in full.items() if s == '2' and any(isinstance(r, dict) and not r['strict_state_hash_same'] for r in R['run_levels'][v].values())]
    runs = [r for d in R['run_levels'].values() for r in d.values() if isinstance(r, dict)]
    shift = sum(1 for r in runs if r['event_first_tick_shift'])
    s3_timing_only = sum(1 for d in R['run_levels'].values() for r in d.values()
                         if isinstance(r, dict) and r['level'] == '3' and r['event_first_tick_shift'])
    per_cell = {}
    for c in ('cell-b', 'cell-b-pack'):
        def u(groups):
            vs = [v for v, x in R['variants'].items() if x['cell'] == c and x['group'] in groups and full[v] != '보류']
            return rate(sum(1 for v in vs if full[v] in ('1', '2', '3')), len(vs))
        a, b = u({'복귀', '포장 핸드셰이크'}), u({'안전'})
        per_cell[c] = dict(return_and_handshake=a, safety=b, diff_pp=round(a['pct'] - b['pct'], 2))
    res['columns'] = dict(stage3_variants=len(s3), stage3_full_state_hash_differs=len(s3_state),
                          stage2_full_state_hash_differs=len(s2_state), runs_with_event_first_tick_shift=shift,
                          stage3_runs_timing_only=s3_timing_only, p1_by_cell_reference=per_cell)
    open(out, 'w', encoding='utf-8').write(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    f = res['full']
    print('full literal totals', f['totals'], '· I-3 -> literal', f['i3_to_literal'])
    print('columns', json.dumps(res['columns'], ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
