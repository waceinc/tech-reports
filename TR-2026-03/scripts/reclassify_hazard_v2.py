#!/usr/bin/env python3
"""TR-2026-03: stage-4 split by the pre-registration's wording (section 5), version 2.

Pre-registration §5, stage 4a: "hazard events: physical events of the plant model (person-zone motion, drop, collision,
JAM, a defective part through the good exit, ...) differ"; 4b: "the physical events are the same and the control verdict
differs". The analysis applied I-3 (fixed before the results): 4a = any difference in event counts by name (production
included) or in the parts' final outcome. Version 1 of this script (scripts/old/reclassify_hazard.py) judged 4a from
non-production event counts only and so missed the example "a defective part through the good exit", which the records
keep as final part state, not as an event. Version 2 judges every listed example:
  events       non-production event counts by name differ (the result file's per-run `hazard_diff`; motion in a zone,
               drop, collision, JAM and every other event that the runner's verdict code does not treat as production)
  final parts  the number of defective parts that ended at the good exit differs from the baseline's (repetition 1,
               same scenario), read from `classification` in the run summaries (fields id, defective, route, correct):
               good exit = route 2 in cell B and route 5 in the pack cell, as in the runner's verdict code (`correct`:
               a good part is correct at route 2 / 5; a defective one at routes 1, 3 / 6) and as in every baseline run
               (good parts at 2 / 5, defective parts at 1 / 6 or not yet routed, 0; no baseline used route 3). Cell A has no sorting exit
               (one good part, route 0), so this count is 0 there.
  run level    4a-literal if either differs; else 4b-literal if the verdict differs (`judgment_diff` or `status_diff`);
               else "unassigned" (reported; expected 0)
  variant      4a-literal if any revealing run is, else 4b-literal if any is, else unassigned
Only the revealed variants (stage 4 in the result file) are re-split; every other stage is kept. Also reported: the
stage-3 full-state, event-timing and per-cell P1 columns of version 1, unchanged. Deterministic (no times, no paths).
Usage: reclassify_hazard_v2.py RESULT_JSON ROUND_DIR OUT_JSON   (ROUND_DIR = extracted tr03-official-1/)
"""
import json, sys
from collections import Counter
from pathlib import Path

GROUPS = ['안전', '밀기 순서', '출력', '알람', '복귀', '포장 핸드셰이크']
CELLS = ['cell-a', 'cell-b', 'cell-b-pack']
SETS = {'full': lambda k: True, 'no045': lambda k: k != 'flow045'}
GOOD_EXIT = {'cell-a': None, 'cell-b': 2, 'cell-b-pack': 5}


def rate(n, d):
    return dict(n=n, d=d, pct=round(100 * n / d, 2) if d else None)


def main(src, rd, out):
    R = json.loads(Path(src).read_text(encoding='utf-8'))
    rd = Path(rd)
    ledger = [json.loads(l) for l in (rd / 'ledger.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    name = {r['no']: r['name'] for r in ledger}
    base = {(r['cell'], r['key']): r['name'] for r in ledger if r['kind'] == 'baseline' and r['rep'] == 1}
    cache = {}

    def bad_at_good_exit(run_name, cell):
        if run_name not in cache:
            cls = json.loads((rd / run_name / 'summary.json').read_text(encoding='utf-8'))['classification']
            ex = GOOD_EXIT[cell]
            cache[run_name] = 0 if ex is None else sum(1 for p in cls if p['defective'] and p['route'] == ex)
        return cache[run_name]

    res, part_runs = {}, set()
    for sname, keep in SETS.items():
        stages = R['sets'][sname]['stages']
        lit, why = {}, {}
        for vid, st in stages.items():
            if st not in ('4a', '4b'):
                lit[vid] = st
                continue
            cell = R['variants'][vid]['cell']
            levels = []
            for k, r in sorted(R['run_levels'][vid].items()):
                if not (keep(k) and isinstance(r, dict) and r['level'] in ('4a', '4b')):
                    continue
                d = bad_at_good_exit(name[r['no']], cell) - bad_at_good_exit(base[(cell, k)], cell)
                if d:
                    part_runs.add((vid, k, d))
                levels.append('4a' if (r['hazard_diff'] or d) else '4b' if (r['judgment_diff'] or r['status_diff']) else 'none')
            lit[vid] = '4a' if '4a' in levels else '4b' if '4b' in levels else 'unassigned'
            why[vid] = dict(i3=st, literal=lit[vid], by_parts_only=lit[vid] == '4a' and not any(
                isinstance(r, dict) and r['hazard_diff'] and keep(k) for k, r in R['run_levels'][vid].items()))
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
                          literal_4a_by_good_exit_only=sorted(v for v in why if why[v]['by_parts_only']),
                          stages_literal=dict(sorted(lit.items())))
    res['good_exit_rule'] = dict(field='classification: defective and route', good_exit_route=GOOD_EXIT,
                                 revealing_runs_with_changed_count=[dict(variant=v, scenario=k, change=d) for v, k, d in sorted(part_runs)])
    full = R['sets']['full']['stages']
    s3 = [v for v, s in full.items() if s == '3']
    diff_state = lambda v: any(isinstance(r, dict) and not r['strict_state_hash_same'] for r in R['run_levels'][v].values())
    runs = [r for d in R['run_levels'].values() for r in d.values() if isinstance(r, dict)]
    per_cell = {}
    for c in ('cell-b', 'cell-b-pack'):
        def u(groups):
            vs = [v for v, x in R['variants'].items() if x['cell'] == c and x['group'] in groups and full[v] != '보류']
            return rate(sum(1 for v in vs if full[v] in ('1', '2', '3')), len(vs))
        a, b = u({'복귀', '포장 핸드셰이크'}), u({'안전'})
        per_cell[c] = dict(return_and_handshake=a, safety=b, diff_pp=round(a['pct'] - b['pct'], 2))
    res['columns'] = dict(stage3_variants=len(s3), stage3_full_state_hash_differs=sum(1 for v in s3 if diff_state(v)),
                          stage2_full_state_hash_differs=sum(1 for v, s in full.items() if s == '2' and diff_state(v)),
                          runs_with_event_first_tick_shift=sum(1 for r in runs if r['event_first_tick_shift']),
                          stage3_runs_timing_only=sum(1 for r in runs if r['level'] == '3' and r['event_first_tick_shift']),
                          p1_by_cell_reference=per_cell)
    Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    f = res['full']
    print('full literal totals', f['totals'], '· I-3 -> literal', f['i3_to_literal'], '· 4a by good exit only', f['literal_4a_by_good_exit_only'])


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:4])
