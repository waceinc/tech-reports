#!/usr/bin/env python3
"""TR-2026-02: recompute metric 1 (runner verdicts) and metric 2 (missed Boolean edges) from released files only.

Uses the released thin layer of the test-bench runner (runner_thin_layer/bridge: run.py with `reconstruct`
and `verdict`, transport.py which run.py imports, scenarios_3j.py / scenarios_3i.py with
`negative_judgments`, and experiments/S2/criteria-3k.md), the released adapter and the released analysis
script's `missed_edges`. No PLC engine, plant model or extctl code is needed or loaded.

Metric 1: for every one of the 816 runs, the per-tick judgments are recomputed with negative_judgments,
the end-sensor visit list is recomputed with the same lines run() uses inline (copied below), and
run.verdict(...) is called on the trace rows. The result must equal the verdict fields of the run's
summary.json and the ledger status; then metric 1 (false alarm / missed negative) is recomputed and
compared with the result file. The verdict consumes plant events, plant state and PLC probes recorded
in the trace; those values come from the private plant model and engine and are read, not recomputed.
Metric 2: the analysis script's missed_edges with the adapter's restoration, on the 8 runs of the result
file, compared field by field with result JSON metric2.

Usage: recompute_metrics_1_2.py BUNDLE_DIR RUN_DIR      (RUN_DIR = extracted tr02-official-1/)
Exit code 0 only if everything matches. Python 3 standard library only.
"""
import importlib.util, json, sys
from pathlib import Path

BUNDLE, RUN = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
sys.dont_write_bytecode = True
sys.path[:0] = [str(BUNDLE / 'runner_thin_layer' / 'bridge'), str(BUNDLE / 'scripts')]
import run as runner  # noqa: E402  released thin layer (imports transport only)
from scenarios_3j import negative_judgments  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


adapter = load('tr02_adapter', BUNDLE / 'adapter' / 'TR-02_연결조건_어댑터.py')  # `import run` reuses the module above
assert adapter.R is runner, 'adapter must use the released run.py'
analysis = load('tr02_analysis', BUNDLE / 'scripts' / 'TR-02_분석.py')
res = json.loads((BUNDLE / 'results' / 'TR-02_결과_tr02-official-1.json').read_text(encoding='utf-8'))
ledger = [json.loads(l) for l in (RUN / 'ledger.jsonl').read_text().splitlines() if l.strip()]
FIELDS = ['status', 'completed', 'event_count', 'events', 'production_events', 'judgment_count', 'judgments',
          'visits', 'routes', 'classification', 'probes']
bad = []


def ticks(name):
    rows = [json.loads(l) for l in (RUN / name / 'trace.jsonl').read_text().splitlines() if l.strip()]
    return [r for r in rows if r.get('type') == 'tick']


# ---- metric 1: verdict of every run ----
status = {}
judg_mismatch = 0
for r in ledger:
    rows = ticks(r['name'])
    visits = []
    for row in rows:
        # copied from run.run(): end-sensor visit list (cell A)
        wanted = 'right' if len(visits) % 2 == 0 else 'left'
        if len(visits) < 6 and any(e['tag'] == f'A.Sen.{wanted}' and e['value'] for e in row['edges']):
            visits.append(wanted)
        probes = row['scans'][-1]['probes']
        if negative_judgments('cell-a', row['I'], row['Q_next'], probes, row['tick']) != row['judgments']:
            judg_mismatch += 1
    v = runner.verdict('cell-a', rows, rows[-1]['scans'][-1]['probes'], visits)
    s = json.loads((RUN / r['name'] / 'summary.json').read_text())
    diff = [f for f in FIELDS if v[f] != s[f]]
    if diff or v['status'] != r['status']:
        bad.append(('verdict', r['no'], diff))
    status[r['no']] = v['status']
m1 = dict(false_alarm=[0, 0], missed_negative=[0, 0], detail={})
plant = {(r['variant'], r['mode'], r['rep']): r['no'] for r in ledger if r['kind'] == 'plant'}
for lad in ('correct', 'late-reverse', 'swapped-sensors'):
    h, b = plant[(lad, 'history', 1)], plant[(lad, 'boundary', 1)]
    m1['detail'][lad] = dict(history=[h, status[h]], boundary=[b, status[b]])
    if lad == 'correct':
        m1['false_alarm'][1] += 1
        m1['false_alarm'][0] += status[h] == '[PASS]' and status[b] == '[FAIL]'
    else:
        m1['missed_negative'][1] += 1
        m1['missed_negative'][0] += status[h] == '[FAIL]' and status[b] == '[PASS]'
if judg_mismatch:
    bad.append(('judgments', judg_mismatch))
if m1 != res['metric1']:
    bad.append(('metric1', m1, res['metric1']))

# ---- metric 2: missed Boolean edges (repetition 1, 8 runs) ----
names = {r['no']: r['name'] for r in ledger}
m2_ok = 0
for key, want in sorted(res['metric2'].items()):
    mode = key.split('/')[1]
    got = dict(run=want['run'], **analysis.missed_edges(adapter, mode, ticks(names[want['run']])))
    if got == want:
        m2_ok += 1
    else:
        bad.append(('metric2', key))

print(f"metric 1: {len(status)} run verdicts recomputed, {sum(1 for b in bad if b[0] == 'verdict')} differ from summary/ledger; "
      f"per-tick judgments differing: {judg_mismatch}; false alarm {m1['false_alarm'][0]}/{m1['false_alarm'][1]}, "
      f"missed negative {m1['missed_negative'][0]}/{m1['missed_negative'][1]} -> {'same as' if m1 == res['metric1'] else 'DIFFERENT from'} result file")
print(f"metric 2: {m2_ok}/{len(res['metric2'])} entries equal to result file")
print('[PASS] all equal' if not bad else '[FAIL] ' + json.dumps(bad[:10], ensure_ascii=False))
sys.exit(0 if not bad else 1)
