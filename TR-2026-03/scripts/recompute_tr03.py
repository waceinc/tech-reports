#!/usr/bin/env python3
"""TR-2026-03: recompute what can be recomputed from the released bundle alone and compare it with the result file.

  A. validity from the ledger and the run records: row counts, repetition hashes of the 19 baseline pairs,
     summary / adapter / ledger trace-hash and status agreement, adapter and ladder SHA-256 in every run
  B. cell A trace hashes: the trace hash of each of the 54 cell-A runs recomputed from its released trace
     (SHA-256 of the compact, key-sorted JSON list of the per-tick `hash` fields) equals the ledger
  C. the separate check script (scripts/TR-03_리드독립검산.py, unchanged) on the extracted records: its output
     equals the output recorded in results/TR-03_리드독립검산_tr03-official-1.md (stage 4 = 4a/4b per variant, P1)
  D. cell A run levels 2-4: the released analysis functions `extract` and `compare` (scripts/TR03_분석_읽기.py) on the
     released traces reproduce `run_levels` of the result file for the 50 cell-A variant runs
  E. cell A stage 1 for input tags: scan inputs rebuilt with the released `reconstruct` (runner_thin_layer/bridge/run.py)
     from the baseline traces give the blocked-scan counts of the result file (tags that are internal bits need the
     private PLC engine and are counted as not recomputed)
  G. the main stage-4 split: scripts/reclassify_hazard_v2.py re-run on the result file and the released summaries gives
     results/TR-03_재분류_위험사건_v2_tr03-official-1.json byte for byte
  F. re-aggregation: the released `classify`, `metrics`, `predictions` and `representatives` (scripts/TR03_분석_집계.py)
     applied to the result file's per-run levels and blocked-scan counts reproduce every table of both sets (with and
     without flow 0.45). This re-runs the same code on recorded intermediate values; it is not an independent check.
Usage: recompute_tr03.py BUNDLE_DIR ROUND_DIR [--inject]
  ROUND_DIR = tr03-official-1/ extracted from the three runs/*.tar.xz archives
  --inject  negative control: alters one run level, one blocked-scan count, one recorded check line and the hazard
            flags of one stage-4a variant in memory;
            the run must then report those differences and exit non-zero.
"""
import copy, hashlib, json, re, subprocess, sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
ADAPTER_SHA = '0caed4f0d7fe72c62e9eb76048413778afc0c3b5610679463a959454fc84b2a7'
PREREG = {'cell-a': '5058bd0b97644e66c0310a540a0403931bf6bd8195445576430d6dd1cabf8ef1',
          'cell-b': '05999e23b90b265f9907e0cd05f5469eccec6195e43326310bb9b491bd4ed0b1',
          'cell-b-pack': '5a4cc91db8f6e53197e613ff87426bc94438a0b7c3226946417b2aa407b53fb1'}
OUT, FAILS = [], []


def say(ok, label, detail=''):
    OUT.append(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f' — {detail}' if detail else ''))
    if not ok:
        FAILS.append(label)


def canon(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def jl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


def main(bundle, rd, inject):
    bundle, rd = Path(bundle), Path(rd)
    sys.path[:0] = [str(bundle / 'scripts'), str(bundle / 'runner_thin_layer' / 'bridge')]
    from TR03_분석_읽기 import extract, compare
    from TR03_분석_집계 import CELLS, SETS, classify, metrics, predictions, representatives
    from run import reconstruct
    R = json.loads((bundle / 'results' / 'TR-03_결과_tr03-official-1.json').read_text(encoding='utf-8'))
    vlist = json.loads((bundle / 'variants' / 'TR-03_변종목록_v1.json').read_text(encoding='utf-8'))
    table = json.loads((bundle / 'variants' / 'ladders-sha256.json').read_text(encoding='utf-8'))
    record = (bundle / 'results' / 'TR-03_리드독립검산_tr03-official-1.md').read_text(encoding='utf-8')
    if inject:
        R = copy.deepcopy(R)
        R['run_levels']['cell-a-0002']['normal']['level'] = '4a'
        R['variants']['cell-a-0005']['active_scans']['normal'] = 1
        record = record.replace("P1: 복귀", "P1: 복귀 ")
        hz = next(v for v, st in R['sets']['full']['stages'].items() if st == '4a'
                  and any(isinstance(r, dict) and r['hazard_diff'] for r in R['run_levels'][v].values()))
        for r in R['run_levels'][hz].values():
            if isinstance(r, dict):
                r['hazard_diff'] = False
    ledger = jl(rd / 'ledger.jsonl')
    say(ledger == jl(bundle / 'runs' / 'ledger.jsonl'), 'A1 ledger in the archive equals runs/ledger.jsonl')
    say(len(ledger) == R['validity']['ledger_rows'] == len({r['no'] for r in ledger}) == 3718, 'A2 ledger rows and distinct numbers', str(len(ledger)))
    cnt = {c: [sum(1 for r in ledger if r['cell'] == c and r['kind'] == k) for k in ('baseline', 'variant')] for c in PREREG}
    say(all(cnt[c] == [R['validity']['counts'][c]['baseline_runs'], R['validity']['counts'][c]['variant_runs']] for c in cnt), 'A3 runs per cell', json.dumps(cnt))
    base = {(r['cell'], r['key'], r['rep']): r for r in ledger if r['kind'] == 'baseline'}
    pairs = [(c, k) for (c, k, rep) in base if rep == 1]
    same = sum(base[(c, k, 1)]['trace_hash'] == base[(c, k, 2)]['trace_hash'] for c, k in pairs)
    say(same == len(pairs) == 19, 'A4 baseline repetitions with identical trace hashes', f'{same}/{len(pairs)}')
    rc_bad = sorted(r['no'] for r in ledger if r['rc'] != 0)
    say([str(n) for n in rc_bad] == sorted(R['validity']['run_problems'], key=int), 'A5 runs with non-zero exit = result file run problems', str(rc_bad))
    agree = adapt = lad = procs = 0
    for r in ledger:
        d = rd / r['name']
        procs += r['processes'] == '[PASS]'
        if r['rc'] != 0:
            continue
        s, a = json.loads((d / 'summary.json').read_text()), json.loads((d / 'tr03-adapter.json').read_text())
        agree += s['trace_hash'] == a['trace_hash'] == r['trace_hash'] and s['status'] == r['status'] == a['status']
        adapt += a['adapter_sha256'] == ADAPTER_SHA
        want = PREREG[r['cell']] if r['kind'] == 'baseline' else table[r['variant_id']]['program']
        lad += r['ladder_sha256'] == want == a['ladder_sha256']
    n_ok = len(ledger) - len(rc_bad)
    say(agree == adapt == lad == n_ok, 'A6 trace hash, status, adapter and ladder SHA-256 agree in every completed run', f'{agree}/{n_ok}')
    say(procs == len(ledger), 'A7 child-process check [PASS] in every run', f'{procs}/{len(ledger)}')

    th = sum(hashlib.sha256(canon([t['hash'] for t in jl(rd / r['name'] / 'trace.jsonl') if t.get('type') == 'tick'])).hexdigest()
             == r['trace_hash'] for r in ledger if r['cell'] == 'cell-a')
    say(th == 54, 'B1 cell-A trace hashes recomputed from the released traces', f'{th}/54')

    p = subprocess.run([sys.executable, '-B', str(bundle / 'scripts' / 'TR-03_리드독립검산.py'), str(rd)], capture_output=True, text=True)
    block = re.search(r'```\n(.*?)```', record, re.S).group(1)
    say(p.returncode == 0 and p.stdout == block, 'C1 separate check script output equals the recorded output', f'{len(p.stdout.splitlines())} lines')

    bx = {k: extract(rd / base[('cell-a', k, 1)]['name']) for k in ('normal', 'cycle-stop')}
    eq = tot = 0
    for r in ledger:
        if r['cell'] == 'cell-a' and r['kind'] == 'variant':
            got = dict(no=r['no'], **compare(bx[r['key']], extract(rd / r['name'])))
            tot += 1
            eq += canon(got) == canon(R['run_levels'][r['variant_id']][r['key']])
    say(eq == tot == 50, 'D1 cell-A variant run levels from the released traces', f'{eq}/{tot}')

    sampled = [x for x in vlist['variants'] if x['sampled']]
    inputs = set(jl(rd / base[('cell-a', 'normal', 1)]['name'] / 'trace.jsonl')[1]['I'])
    va = [x for x in sampled if x['cell'] == 'cell-a' and x['tag'] in inputs]
    blocked = {k: Counter() for k in bx}
    for k in bx:
        for t in jl(rd / base[('cell-a', k, 1)]['name'] / 'trace.jsonl'):
            if t.get('type') == 'tick':
                for img in reconstruct(t['I_start'], dict(dt_s=t['dt_s'], edges=t['edges'], I=t['I'])):
                    for x in va:
                        blocked[k][x['id']] += (img[x['tag']] is False) if x['mode'] == 'NO' else (img[x['tag']] is True)
    e1 = sum(blocked[k][x['id']] == R['variants'][x['id']]['active_scans'][k] for x in va for k in bx)
    say(e1 == 2 * len(va), 'E1 cell-A blocked-scan counts for input-tag conditions', f'{e1}/{2 * len(va)} (input tags {len(va)} of 25 cell-A variants; '
        f'{25 - len(va)} internal-bit conditions need the private engine)')

    valid = R['validity']['valid_scenarios']
    ok_rs = {k: v['ok'] for k, v in R['validity']['rescan'].items()}
    pop = {c: vlist['cells'][c]['target_by_group'] for c in CELLS}
    for sname, keep in SETS.items():
        res = {}
        for x in sampled:
            act = R['variants'][x['id']]['active_scans']
            rsc = {k: dict(ok=ok_rs[f"{x['cell']}/{k}"], values={x['tag']: {'0': act[k] if x['mode'] == 'NO' else 0,
                                                                            '1': act[k] if x['mode'] == 'NC' else 0}})
                   for k in valid[x['cell']] if k in act}
            res[x['id']] = classify(x, valid[x['cell']], rsc, R['run_levels'].get(x['id'], {}), keep)
        m1, m2, m3 = metrics(sampled, res, pop)
        mine = dict(metric1=m1, metric2=m2, metric3=m3, predictions=predictions(sampled, res),
                    predictions_outcome_first=predictions(sampled, res, 'stage_outcome_first'),
                    representatives=representatives(sampled, res),
                    inactive_but_q_changed=sorted(i for i, r in res.items() if r['inactive_but_q_changed']),
                    stages={i: r['stage'] for i, r in sorted(res.items())})
        diff = [k for k in mine if canon(json.loads(canon(mine[k]))) != canon(R['sets'][sname][k])]
        say(not diff, f'F1 re-aggregation, set {sname}', 'all tables equal' if not diff else 'differs: ' + ', '.join(diff))
        st = Counter(mine['stages'].values())
        OUT.append(f"      set {sname}: stages {dict(sorted(st.items()))} · P1 {mine['predictions']['P1']['verdict']} "
                   f"{mine['predictions']['P1']['diff_pp']} %p · P2 {mine['predictions']['P2']['verdict']} {mine['predictions']['P2']['pct']} %")
    rc = bundle / 'results' / 'TR-03_재분류_위험사건_v2_tr03-official-1.json'
    tmp = Path(rd) / '_reclassify_check.json'
    src = bundle / 'results' / 'TR-03_결과_tr03-official-1.json'
    if inject:
        src = Path(rd) / '_injected_result.json'
        src.write_text(json.dumps(R, ensure_ascii=False))
    q = subprocess.run([sys.executable, '-B', str(bundle / 'scripts' / 'reclassify_hazard_v2.py'), str(src), str(rd), str(tmp)], capture_output=True, text=True)
    lit = json.loads(tmp.read_text()) if q.returncode == 0 else {}
    say(q.returncode == 0 and tmp.read_bytes() == rc.read_bytes(), 'G1 main stage-4 split (v2) reproduced byte for byte',
        json.dumps(lit.get('full', {}).get('totals', {}), ensure_ascii=False))
    OUT.append(f'{len(FAILS)} FAIL' if FAILS else 'all checks passed')
    print('\n'.join(OUT))
    return 1 if FAILS else 0


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--inject']
    if len(a) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(a[0], a[1], '--inject' in sys.argv))
