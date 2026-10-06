#!/usr/bin/env python3
"""TR-2026-07 independent recompute. Never reads results.jsonl or the runner's measurements: it reads either the raw
round (a??/<rule>/run?/attempt?/{exit.json,result.json,diag.json,run.log} and a??/author/result.json) or the public
version (runs/*.json written by TR-07_public.py from the raw files), recomputes every pre-registered quantity with
separately written code and compares all of them, verdicts included, with a tables.json from TR-07_tables.py.
Exit 0 when everything matches.
usage: TR-07_recompute.py <round or public dir> <tables.json>
"""
import glob
import json
import os
import sys
from fractions import Fraction

RULES = ['return', 'predictive', 'lookahead', 'charge']
INF = float('inf')


def load(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def raw_run(folder):
    """The counting attempt is the last one; values straight from the application's files."""
    attempts = sorted(glob.glob(os.path.join(folder, 'attempt*')))
    if not attempts:
        return None
    last = attempts[-1]
    code = load(os.path.join(last, 'exit.json'))['exit']
    if not all(os.path.exists(os.path.join(last, f)) for f in ('result.json', 'diag.json', 'run.log')):
        return {'exit': code, 'measured': False}
    result = load(os.path.join(last, 'result.json'))
    samples = load(os.path.join(last, 'diag.json')).get('samples', [])
    fleet = result.get('fleet') or {}
    low = None
    project = load(os.path.join(os.path.dirname(folder), 'project', 'factory.vexplor'))
    for amr in project['amrs']:
        battery = amr['profile'].get('battery') or {}
        if battery.get('enabled') and battery.get('initialSoc') == 0.2:
            low = amr['sceneId']
    docked = sum(1 for s in samples for v in s.get('runtime', {}).get('vehicles', []) if v.get('chargeDocked') and v.get('amrId') == low)
    double = 0
    for s in samples:
        held = [v['charger'] for v in s.get('runtime', {}).get('vehicles', []) if v.get('charger')]
        double += len(held) != len(set(held))
    return {'exit': code, 'measured': True, 'state': result.get('state'), 'error': result.get('error'),
            'completed': result.get('completedTransfers'), 'empty': fleet.get('emptyTravelMeters', 0),
            'times': fleet.get('completionTimes', []), 'contacts': result.get('amrPeerContactCount'), 'lowDocked': docked, 'double': double}


def public_run(path):
    if not os.path.exists(path):
        return None
    r = load(path)
    return {'exit': r['exit'], 'measured': r['measured'], 'state': r.get('state'), 'error': r.get('error'), 'completed': r.get('completedTransfers'),
            'empty': r.get('emptyTravelMeters'), 'times': r.get('completionTimes'), 'contacts': r.get('amrPeerContactCount'),
            'lowDocked': r.get('lowBatteryDockedSamples'), 'double': r.get('doubleChargerReservations')}


def ok(run):
    return run is not None and run['exit'] == 0 and run['measured'] and run['state'] == 'horizon_reached' and not run['error'] \
        and isinstance(run['completed'], int)


def mid(values):
    s = sorted(values)
    if not s:
        return None
    lo, hi = s[(len(s) - 1) // 2], s[len(s) // 2]
    return INF if INF in (lo, hi) else (lo + hi) / 2


def main():
    base, tables = sys.argv[1], load(sys.argv[2])
    ledger = load(os.path.join(base, 'run.json'))
    public = os.path.isdir(os.path.join(base, 'runs'))
    get = (lambda k, rule, rep: public_run(os.path.join(base, 'runs', f'a{k:02d}_{rule}_run{rep}.json'))) if public else \
          (lambda k, rule, rep: raw_run(os.path.join(base, f'a{k:02d}', rule, f'run{rep}')))
    planned = ledger['authorings']
    events = {e['authoring']: e for e in ledger['events']}
    if public:
        passed = [k for k in range(1, planned + 1) if events.get(k, {}).get('authorStatus') == 'PASS']
    else:
        passed = [k for k in range(1, planned + 1) if os.path.exists(os.path.join(base, f'a{k:02d}', 'author', 'result.json'))
                  and load(os.path.join(base, f'a{k:02d}', 'author', 'result.json')).get('status') == 'PASS']
    runs = {(k, rule, 1): get(k, rule, 1) for k in passed for rule in RULES}
    valid = [k for k in passed if all(ok(runs[(k, rule, 1)]) for rule in RULES) and runs[(k, 'return', 1)]['completed'] >= 1]
    invalid = [k for k in range(1, planned + 1) if k not in valid]
    first = next((k for k in passed if all(ok(runs[(k, rule, 1)]) for rule in RULES)), None)
    second = {rule: get(first, rule, 2) for rule in RULES} if first else {}
    same = bool(second) and all(ok(second[rule]) and (runs[(first, rule, 1)]['completed'], runs[(first, rule, 1)]['empty'], runs[(first, rule, 1)]['times'])
                                == (second[rule]['completed'], second[rule]['empty'], second[rule]['times']) for rule in RULES)
    present = all(runs[(k, rule, 1)] is not None for k in passed for rule in RULES) and all(second.get(rule) is not None for rule in RULES) if first else False
    canon = {events[k].get('canonicalSha256') for k in passed}
    checks = {'canonicalIdentical': len(canon) == 1, 'deterministic': same, 'invalidAtMost2': len(invalid) <= 2, 'allPlannedRunsPresent': present}
    valid_round = all(checks.values())
    n = len(valid)
    ratio = {}
    for k in valid:
        r, p = runs[(k, 'return', 1)], runs[(k, 'predictive', 1)]
        ratio[k] = INF if p['completed'] == 0 else (Fraction(p['empty']) * r['completed']) / (Fraction(r['empty']) * p['completed'])
    m = mid(list(ratio.values()))
    below = sum(1 for v in ratio.values() if v < 1)
    kept = sum(1 for k in valid if runs[(k, 'predictive', 1)]['completed'] >= runs[(k, 'return', 1)]['completed'])
    counted = [runs[(k, rule, 1)] for k in valid for rule in RULES] + (list(second.values()) if first in valid else [])
    touching = sum(1 for run in counted if run['contacts'] != 0)
    charged = sum(1 for k in valid if runs[(k, 'charge', 1)]['lowDocked'] > 0 and runs[(k, 'charge', 1)]['double'] == 0)

    def call(good):
        return ('held' if good else 'wrong') if valid_round else 'void'
    number = lambda v: None if v is None else ('inf' if v == INF else float(v))
    mine = {
        'validAuthorings': valid, 'invalidAuthorings': invalid, 'checks': checks, 'roundValid': valid_round, 'determinismAuthoring': first,
        'ratios': {str(k): number(v) for k, v in sorted(ratio.items())},
        'P1': (number(m), call(m is not None and m <= Fraction(95, 100))),
        'P2': (f'{below}/{n}', call(n > 0 and 5 * below >= 4 * n)),
        'P3': (f'{kept}/{n}', call(n > 0 and 10 * kept >= 7 * n)),
        'P4': (f'{touching}/{len(counted)}', call(touching == 0)),
        'P5': (f'{charged}/{n}', call(n > 0 and charged == n)),
        'F1': (m is not None and m >= 1) if valid_round else 'void',
        'F2': (2 * (n - kept) > n) if valid_round else 'void',
    }
    theirs = {
        'validAuthorings': tables['validAuthorings'], 'invalidAuthorings': tables['invalidAuthorings'], 'checks': tables['checks'],
        'roundValid': tables['roundValid'], 'determinismAuthoring': tables['determinismAuthoring'], 'ratios': tables['ratios'],
        **{p: (tables['predictions'][p]['value'], tables['predictions'][p]['verdict']) for p in ('P1', 'P2', 'P3', 'P4', 'P5')},
        'F1': tables['falsifiers']['F1']['triggered'], 'F2': tables['falsifiers']['F2']['triggered'],
    }
    differences = [(key, mine[key], theirs[key]) for key in mine if mine[key] != theirs[key]]
    for key, a, b in differences:
        print(f'MISMATCH {key}: recomputed={a} tables={b}')
    print(f"TR07_RECOMPUTE source={'public' if public else 'raw'} valid={n} P1={number(m)} {'MATCH' if not differences else 'MISMATCH'}")
    return 0 if not differences else 1


if __name__ == '__main__':
    sys.exit(main())
