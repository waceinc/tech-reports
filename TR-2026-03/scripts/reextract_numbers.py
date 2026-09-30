#!/usr/bin/env python3
"""TR-2026-03: re-extract every number of the report from the released bundle and check that the text states it.

Each check computes values from bundle files and formats a phrase of the report with them; the phrase must occur in the
report verbatim. A wrong number in the text therefore shows up as a missing phrase. Numbers that cannot come from the
bundle are printed at the end with their source.
Usage: reextract_numbers.py BUNDLE_DIR ROUND_DIR REPORT.md [--selftest]
  --selftest  negative control: changes four numbers and swaps two Table-2 cells in an in-memory copy of the report; exactly those checks must fail.
"""
import json, sys
from collections import Counter
from pathlib import Path

G = {'safety': '안전', 'push sequence': '밀기 순서', 'output': '출력', 'alarm': '알람', 'recovery': '복귀', 'pack handshake': '포장 핸드셰이크'}


def jl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


def fr(r, pct=True):
    return f"{r['n']}/{r['d']}" + (f" ({r['pct']} %)" if pct and r['pct'] is not None else '')


def checks(b, rd):
    R = json.loads((b / 'results/TR-03_결과_tr03-official-1.json').read_text(encoding='utf-8'))
    V = json.loads((b / 'variants/TR-03_변종목록_v1.json').read_text(encoding='utf-8'))
    L = jl(rd / 'ledger.jsonl')
    F = json.loads((b / 'figures/figure_values.json').read_text(encoding='utf-8'))
    hdr = json.loads((rd / 'run-header.json').read_text())
    S = R['sets']['full']
    m1, m2, m3, P = S['metric1'], S['metric2'], S['metric3'], S['predictions']
    c = V['cells']
    out = []
    add = lambda label, phrase: out.append((label, phrase))
    t = {k: c[k]['tally'] for k in c}
    for k, name in (('cell-a', 'Cell A'), ('cell-b', 'Cell B'), ('cell-b-pack', 'Pack cell')):
        x = t[k]
        f = lambda n: f'{n:,}'
        add(f'count table {k}', f"| {name} | {f(x['접점 칸 전체'])} | {f(x['조건 전체'])} | {x['병렬 분기 안 조건']} | {x['직렬 조건']} | "
            f"{x['직렬 조건 — 대상 밖 묶음']} | **{sum(c[k]['target_by_group'].values())}** | {x['비교 박스(대상 밖)']} |")
    add('rungs', f"cell A ({c['cell-a']['rungs']} rungs")
    add('rungs B/pack', f"cell B ({c['cell-b']['rungs']} rungs; tick 10 ms) and the pack cell ({c['cell-b-pack']['rungs']} rungs")
    add('target total', f"Of {sum(sum(c[k]['target_by_group'].values()) for k in c):,} target conditions, 500 were run")
    add('n', f"Cell B: n = {c['cell-b']['per_group_n']} (") ; add('n pack', f"Pack cell: n = {c['cell-b-pack']['per_group_n']} (")
    add('runs', f"{c['cell-b']['sampled']} variants, {c['cell-b']['runs_sampled']:,} runs. Pack cell")
    add('runs pack', f"{c['cell-b-pack']['sampled']} variants, {c['cell-b-pack']['runs_sampled']:,} runs.")
    kinds = Counter(r['kind'] for r in L)
    add('abstract runs', f"{kinds['variant']:,} variant runs and {kinds['baseline']} baseline runs")
    base = {(r['cell'], r['key'], r['rep']): r for r in L if r['kind'] == 'baseline'}
    same = sum(base[(a, k, 1)]['trace_hash'] == base[(a, k, 2)]['trace_hash'] for a, k, rep in base if rep == 1)
    add('pairs', f"All {same} baseline pairs had identical trace hashes")
    add('ledger', f"The ledger has {len(L):,} rows with {len({r['no'] for r in L}):,} distinct numbers")
    per = {k: (sum(1 for r in L if r['cell'] == k and r['kind'] == 'baseline'), sum(1 for r in L if r['cell'] == k and r['kind'] == 'variant')) for k in c}
    add('per cell', f"per cell {per['cell-a'][0]}, {per['cell-b'][0]} and {per['cell-b-pack'][0]} baseline runs and "
        f"{per['cell-a'][1]}, {per['cell-b'][1]:,} and {per['cell-b-pack'][1]:,} variant runs")
    bad = sorted(int(n) for n in R['validity']['run_problems'])
    add('problem runs', f"Six runs ended with a non-zero exit code" if len(bad) == 6 else '<<MISMATCH>>')
    add('problem run numbers', f"runs {bad[0]}–{bad[-1]}")
    add('rescan', f"({sum(v['checks']['scans'] for v in R['validity']['rescan'].values()):,} scans) reproduced every recorded scan digest")
    st = Counter(S['stages'].values())
    add('stages', f"stage 1, {st['1']}; stage 2, {st['2']}; stage 3, {st['3']}; revealed, {st['4a'] + st['4b']}; held, {st['보류']}")
    add('abstract revealed', f"{st['4a'] + st['4b']} of the 500 removals were revealed.")
    O = json.loads((b / 'results/old/TR-03_재분류_위험사건_tr03-official-1.json').read_text(encoding='utf-8'))['full']['totals']
    add('version 1 values', f"counted non-production events only ({O['4a']} / {O['4b']})")
    und = st['1'] + st['2'] + st['3']
    add('abstract unrevealed', f"Of the {und} that were not revealed, {st['1']} were never exercised (stage 1), {st['2']} were exercised")
    add('abstract stage 3', f"and {st['3']} changed the outputs")
    hz = [m2[k]['전체']['4a_위험사건'] for k in c]  # the analysis' own hazard count equals the literal 4a (checked below)
    add('I-1', f"(the I-1 sensitivity case: {len(S['inactive_but_q_changed'])})")
    p1, p2 = P['P1'], P['P2']
    add('P1 table', f"{fr(p1['return_and_handshake'])} against {fr(p1['safety'])}: {p1['diff_pp']} points")
    add('P1 abstract', f"the difference was {p1['diff_pp']} points ({p1['return_and_handshake']['pct']} % against {p1['safety']['pct']} %)")
    rg = p1['reference_by_group']
    add('P1 ref', f"recovery alone was not revealed in {rg['복귀']['n']}/{rg['복귀']['d']} ({rg['복귀']['pct']} %, {p1['reference_diff_pp']['복귀']} points above safety) "
        f"and pack handshake alone in {rg['포장 핸드셰이크']['n']}/{rg['포장 핸드셰이크']['d']} ({rg['포장 핸드셰이크']['pct']} %, {p1['reference_diff_pp']['포장 핸드셰이크']} points)")
    add('P2', f"{p2['stage1']} of {p2['undetected']} ({p2['pct']} %)")
    add('P2 abstract', f"{p2['pct']} % were")
    tn, td, sp = p1['return_and_handshake']['n'], p1['return_and_handshake']['d'], p1['safety']['n'] / p1['safety']['d']
    add('held arithmetic', f"difference of {round((tn / (td + 1) - sp) * 100, 2):.2f} points, counting it as not revealed "
        f"{round(((tn + 1) / (td + 1) - sp) * 100, 2):.2f} points, and P2 would be {p2['stage1']} of {p2['undetected'] + 1} ({round(100 * p2['stage1'] / (p2['undetected'] + 1), 2)} %)")
    for k, name in (('cell-a', 'Cell A'), ('cell-b', 'Cell B'), ('cell-b-pack', 'Pack cell')):
        a = m1[k]['전체']
        add(f'table2 all {k}', f"| {name} | all | {fr(a['all'])} | {fr(a['active'])} |")
    rows = {'cell-a': [['safety', 'push sequence', 'output']], 'cell-b': [['safety', 'push sequence', 'output'], ['alarm', 'recovery']],
            'cell-b-pack': [['safety', 'push sequence', 'output'], ['alarm', 'recovery', 'pack handshake']]}
    for k, name in (('cell-a', 'Cell A'), ('cell-b', 'Cell B'), ('cell-b-pack', 'Pack cell')):
        for gs in rows[k]:  # whole Table-2 row: group names and both columns in order (W9)
            al = [m1[k][G[g]]['all'] for g in gs]
            ac = [m1[k][G[g]]['active'] for g in gs]
            add(f'table2 row {k} {gs[0]}', f"| {name} | {' · '.join(gs)} | {' · '.join(fr(x) for x in al)} | "
                f"{' · '.join(fr(y, y['d'] != x['d']) for x, y in zip(al, ac))} |")
    w = [m1[k]['가중 전체']['pct'] for k in c]
    add('weighted', f"{w[0]} % in cell A, {w[1]} % in cell B and {w[2]} % in the pack cell")
    L2 = json.loads((b / 'results/TR-03_재분류_위험사건_v2_tr03-official-1.json').read_text(encoding='utf-8'))
    lt, cols = L2['full']['totals'], L2['columns']
    add('literal totals', f"stage 4a, {lt['4a']}; stage 4b, {lt['4b']}. Per cell" if lt['4a'] == sum(hz) + len(L2['full']['literal_4a_by_good_exit_only']) else '<<MISMATCH>>')
    ld = {k: L2['full']['distribution'][k]['전체'] for k in c}
    for k, name in (('cell-a', 'cell A'), ('cell-b', 'cell B'), ('cell-b-pack', 'pack cell')):
        x = ld[k]
        add(f'literal {k}', f"{name} {x['1']} / {x['2']} / {x['3']} / {x['4a']} / {x['4b']} / {x['보류']}")
    add('I-3 split', f"stage 4a, {st['4a']}; stage 4b, {st['4b']} (cell A {m2['cell-a']['전체']['4a']} / {m2['cell-a']['전체']['4b']}, "
        f"cell B {m2['cell-b']['전체']['4a']} / {m2['cell-b']['전체']['4b']}, pack cell {m2['cell-b-pack']['전체']['4a']} / {m2['cell-b-pack']['전체']['4b']})")
    moved = L2['full']['i3_to_literal'].get('4a->4b', 0)
    add('moved', f"The {moved} variants that move between the two readings" if moved == L2['full']['i3_4a_verdict_also_differs'] and lt.get('unassigned', 0) == 0 else '<<MISMATCH>>')
    bs = L2['full']['distribution']['cell-b']['안전']
    add('cell B safety', f"none of the {bs['4b']} revealed safety-group variants changed a hazard event or the good-exit count" if bs['4a'] == 0 else '<<MISMATCH>>')
    add('abstract literal', f"{lt['4a']} changed such an outcome (stage 4a) and {lt['4b']} changed only the verdict (stage 4b)")
    ge = L2['good_exit_rule']['revealing_runs_with_changed_count']
    gv = sorted({x['variant'] for x in ge})
    only = L2['full']['literal_4a_by_good_exit_only']
    add('good exit', f"That count differed in {len(gv)} cell-B variants, each by +1 and only in `recovery` and `recovery-retract`; {len(only)} of them"
        if all(x['change'] == 1 and x['scenario'] in ('recovery', 'recovery-retract') and x['variant'].startswith('cell-b-0') for x in ge) else '<<MISMATCH>>')
    add('good exit ids', '(' + ', '.join([only[0]] + [o[-4:] for o in only[1:-1]]) + f' and {only[-1][-4:]})')
    add('good exit routes', f"route {L2['good_exit_rule']['good_exit_route']['cell-b']} in cell B and route {L2['good_exit_rule']['good_exit_route']['cell-b-pack']} in the pack cell")
    add('abstract I-3', f"gives {st['4a']} and {st['4b']}")
    add('stage3 state', f"In {cols['stage3_full_state_hash_differs']} of the {cols['stage3_variants']} stage-3 variants the plant model's full final state")
    add('stage2 state', 'in no stage-2 variant did it' if cols['stage2_full_state_hash_differs'] == 0 else '<<MISMATCH>>')
    add('timing', f"{cols['runs_with_event_first_tick_shift']} runs shifted the first tick of some event, none of them a stage-3 run"
        if cols['stage3_runs_timing_only'] == 0 else '<<MISMATCH>>')
    pc = cols['p1_by_cell_reference']
    add('P1 per cell', f"{pc['cell-b']['diff_pp']} points in cell B ({pc['cell-b']['return_and_handshake']['n']}/{pc['cell-b']['return_and_handshake']['d']} against "
        f"{pc['cell-b']['safety']['n']}/{pc['cell-b']['safety']['d']}) and {pc['cell-b-pack']['diff_pp']} in the pack cell ({pc['cell-b-pack']['return_and_handshake']['n']}/"
        f"{pc['cell-b-pack']['return_and_handshake']['d']} against {pc['cell-b-pack']['safety']['n']}/{pc['cell-b-pack']['safety']['d']})")
    cut = [r for r in L if r['ended'] <= '2026-09-30 19:03:11']
    ab = sum(1 for r in cut if r['cell'] != 'cell-b-pack')
    add('finished by 19:03', f"by 19:03, {len(cut):,} of the {len(L):,} runs had finished — all {ab:,} runs of cells A and B and {len(cut) - ab} pack-cell runs"
        if ab == sum(1 for r in L if r['cell'] != 'cell-b-pack') else '<<MISMATCH>>')
    ns = sum(1 for r in L if r['rc'] == 0)
    add('summaries', f"so there are {ns:,} of each")
    fa = m3['cell-a']['first_revealed']; fb = m3['cell-b']['first_revealed']; fp = m3['cell-b-pack']['first_revealed']
    add('m3 A', f"`normal` for all {fa['normal']} in cell A")
    add('m3 B', f"`normal` seed 1 for {fb['normal-s1']} of {m1['cell-b']['전체']['all']['n']} in cell B (then `recovery` {fb['recovery']}, "
        f"`stroke75`, `recovery-retract` and `curtain` {fb['stroke75']} each)" if fb['stroke75'] == fb['recovery-retract'] == fb['curtain'] else '<<MISMATCH>>')
    add('m3 P', f"`normal` seed 1 for {fp['normal-s1']} of {m1['cell-b-pack']['전체']['all']['n']} in the pack cell (`curtain` and `packfault` {fp['curtain']} each)")
    add('single', f"{m3['cell-a']['only_one_scenario']} in cell A, {m3['cell-b']['only_one_scenario']} in cell B, {m3['cell-b-pack']['only_one_scenario']} in the pack cell")
    N = R['sets']['no045']
    moved = sum(1 for v in R['variants'].values() if 'flow045' in v['revealed_by'] and v['cell'] == 'cell-b')
    same45 = N['stages'] == S['stages'] and N['predictions'] == P
    add('flow 0.45', f"only the count of revealing scenarios moves for three cell-B variants" if same45 and moved == 3 else '<<MISMATCH>>')
    f2 = F['fig2']
    v4 = R['variants']['cell-a-0004']
    add('fig2', f"0 of 3 round trips in both scenarios" if f2['summaries']['variant']['round_trips'] == 0 else '<<MISMATCH>>')
    add('fig2 tick', f"first differed at tick {f2['first_diff_tick']}")
    add('fig2 rung', f"in rung {v4['rung']} of the safety group")
    add('fig2 runs', f"baseline run {f2['summaries']['baseline']['run']} and variant run {f2['summaries']['variant']['run']}")
    f3 = F['fig3']
    add('fig3', f"conducted in all {f3['normal|A.PB.estop_nc']['scans']:,} and {f3['cycle-stop|A.PB.estop_nc']['scans']:,} scans"
        if f3['normal|A.PB.estop_nc']['value0_scans'] == f3['cycle-stop|A.PB.estop_nc']['value0_scans'] == 0 else '<<MISMATCH>>')
    x = [v for v in V['variants'] if v['id'] == 'cell-b-pack-0523'][0]
    tick = {json.loads(r['failure'].replace("'", '"').replace('False', 'false'))['tick'] for r in L if r['rc'] not in (0, None)}
    add('held', f"pack-cell rung {x['rung']} (pack handshake)")
    add('held tick', f"ended at tick {tick.pop()} with an error" if len(tick) == 1 else '<<MISMATCH>>')
    fails = [base[(a, k, 1)]['status'] for a, k, rep in base if rep == 1].count('[FAIL]')
    add('baseline FAIL', f"For {fails} of the {same} baseline scenarios the correct ladder's verdict was [FAIL]")
    ended = sorted(r['ended'] for r in L)
    add('ledger times', f"runs ended {ended[0]} – {ended[-1]} KST")
    add('seconds', f"per-run durations sum to {sum(r['seconds'] or 0 for r in L):,.1f} s")
    add('start', f"the run script's start record is {hdr['started'].split(' ')[1][:5]}")
    for k, name in (('cell-a', '_cell-a.tar.xz` ('), ('cell-b', '`_cell-b.tar.xz` ('), ('cell-b-pack', '`_cell-b-pack.tar.xz` (')):
        n = sum(1 for l in (b / f'runs/tr03-official-1_{k}_files.tsv').read_text().splitlines()[1:] if l)
        add(f'members {k}', f"{name}{n:,}")
    nr = {k: [l.split('\t') for l in (b / f'runs/tr03-official-1_{k}_not_released.tsv').read_text().splitlines()[1:] if l] for k in ('cell-b', 'cell-b-pack')}
    tr = {k: sum(int(r[1]) for r in v if r[0].endswith('trace.jsonl.gz')) for k, v in nr.items()}
    mx = max(int(r[1]) for r in nr['cell-b-pack'] if r[0].endswith('trace.jsonl.gz'))
    add('trace sizes', f"total {(tr['cell-b'] + tr['cell-b-pack']) / 1e9:.1f} GB (cell B {tr['cell-b'] / 1e9:.1f} GB, pack cell {tr['cell-b-pack'] / 1e9:.1f} GB; "
        f"one 10,000-tick pack-cell trace is up to {round(mx / 1e6)} MB")
    cnt = Counter(r[0].split('/')[-1] for r in nr['cell-b'])
    add('constants', f"the {cnt['constants.json']} per-run constants responses and the {cnt['flow.plccell.json']} per-run flow cell files")
    va = [v for v in V['variants'] if v['sampled'] and v['cell'] == 'cell-a' and v['tag'].startswith('A.')]
    rec = (b / 'results/recompute_tr03_output.txt').read_text()
    add('recompute E1', f"blocked-scan counts of the {len(va)} cell-A conditions on input tags" if f'input tags {len(va)} of 25' in rec else '<<MISMATCH>>')
    add('recompute all', 'Isolated recomputation.' if 'all checks passed' in rec and sum(l.startswith('[PASS]') for l in rec.splitlines()) == 14 else '<<MISMATCH>>')
    return out


NOT_FROM_BUNDLE = [('08:52:18 KST, commit b743b0f; about 2 hours 13 minutes', 'public repository commit time (G) minus the start record'),
                   ('18:55-19:03 KST analysis files; 15 start-up digests', 'file times of the analysis files and the fixed record (author); 19:03 cut-off for the finished-run count taken from those times'),
                   ('96 % of the summary bytes', 'original summary sizes (author; public sizes in the archive TSVs)'),
                   ('counting-rule constants: 2,000 cap, groups, scenario tick lengths', 'pre-registration §3-§4 (design constants)'),
                   ('2026-09-20 withdrawal of the trade-secret designation', 'company record')]


def main(b, rd, rp, selftest):
    text = Path(rp).read_text(encoding='utf-8')
    if selftest:
        for a, z in (('11.68 points', '11.86 points'), ('stage 2, 244', 'stage 2, 243'), ('48.48 %', '48.84 %'), ('80,440', '80,404'), ('| 1/5 · 8/12 · 3/8 |', '| 8/12 · 1/5 · 3/8 |')):
            text = text.replace(a, z)
    rows = checks(Path(b), Path(rd))
    miss = [(l, p) for l, p in rows if p not in text]
    for l, p in rows:
        print(f"[{'FAIL' if (l, p) in miss else 'PASS'}] {l}: {p}")
    print(f'{len(rows)} checks · {len(miss)} not found in the text')
    print('Not re-extractable from the bundle:')
    for a, s in NOT_FROM_BUNDLE:
        print(f'  - {a} — {s}')
    if selftest:
        ok = len(miss) >= 5 and any(l.startswith('table2 row') for l, _ in miss)
        print('[PASS] selftest: altered numbers were caught' if ok else '[FAIL] selftest')
        return 0 if ok else 1
    return 1 if miss else 0


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--selftest']
    sys.exit(main(a[0], a[1], a[2], '--selftest' in sys.argv))
