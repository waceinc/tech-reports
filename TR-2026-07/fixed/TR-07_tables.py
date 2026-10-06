#!/usr/bin/env python3
"""TR-2026-07 tables and pre-registered verdicts from <round>/results.jsonl and run.json (written by TR-07_run.py).

Definitions (pre-registration sections 7 and 8):
- A run is good when its exit code is 0, its state is horizon_reached, it has no error and it was measured.
- An authoring is valid when its authoring stage passed, its four rule runs (repeat 1) are good and the return run
  completed at least one transfer.
- The round is valid when (a) every authored project has the same canonical sha256, (b) the determinism authoring (the
  first valid one) repeats completed transfers, empty travel and completion times exactly under every rule, (c) at most
  2 authorings are invalid, and (d) every planned run has a row. Otherwise every verdict is "void".
- r_k = (predictive empty travel / predictive completed) / (return empty travel / return completed), exact fractions of
  the stored binary values; predictive completed 0 gives r_k = +infinity. Median of an even count = mean of the middle two.
usage: TR-07_tables.py <round dir> [--json out.json]
"""
import argparse
import json
import statistics
import sys
from fractions import Fraction
from pathlib import Path

RULES = ('return', 'predictive', 'lookahead', 'charge')
INF = float('inf')


def good(row):
    return row is not None and row.get('exit') == 0 and row.get('state') == 'horizon_reached' and not row.get('error') \
        and not row.get('measureError') and isinstance(row.get('completed'), int)


def per_transfer(row):
    return Fraction(row['emptyTravelMeters']) / row['completed'] if row['completed'] else None


def middle(values):
    ordered = sorted(values)
    if not ordered:
        return None
    a, b = ordered[(len(ordered) - 1) // 2], ordered[len(ordered) // 2]
    return INF if INF in (a, b) else (a + b) / 2


def as_number(value):
    return None if value is None else ('inf' if value == INF else float(value))


def tables(rows, ledger):
    by = {(r['authoring'], r['rule'], r['repeat']): r for r in rows}
    events = {e['authoring']: e for e in ledger['events']}
    planned = ledger['authorings']
    authored = [k for k in range(1, planned + 1) if events.get(k, {}).get('authorStatus') == 'PASS']
    valid, invalid = [], []
    for k in range(1, planned + 1):
        runs = [by.get((k, rule, 1)) for rule in RULES]
        if k in authored and all(good(r) for r in runs) and runs[0]['completed'] >= 1:
            valid.append(k)
        else:
            invalid.append(k)
    canon = {events[k].get('canonicalSha256') for k in authored}
    first = ledger.get('determinismAuthoring')
    pairs = [(by.get((first, rule, 1)), by.get((first, rule, 2))) for rule in RULES] if first else []
    deterministic = bool(pairs) and all(good(a) and good(b) and (a['completed'], a['emptyTravelMeters'], a['completionTimes']) ==
                                        (b['completed'], b['emptyTravelMeters'], b['completionTimes']) for a, b in pairs)
    complete = all((k, rule, 1) in by for k in authored for rule in RULES) and all((first, rule, 2) in by for rule in RULES) if first else False
    checks = {'canonicalIdentical': len(canon) == 1, 'deterministic': deterministic, 'invalidAtMost2': len(invalid) <= 2,
              'allPlannedRunsPresent': complete}
    round_valid = all(checks.values())
    n = len(valid)
    ratios = {}
    for k in valid:
        ret, pre = by[(k, 'return', 1)], by[(k, 'predictive', 1)]
        p, r = per_transfer(pre), per_transfer(ret)
        ratios[k] = INF if p is None else p / r
    med = middle(list(ratios.values()))
    lower = sum(1 for v in ratios.values() if v < 1)
    not_fewer = sum(1 for k in valid if by[(k, 'predictive', 1)]['completed'] >= by[(k, 'return', 1)]['completed'])
    fewer = n - not_fewer
    counted = [by[(k, rule, 1)] for k in valid for rule in RULES] + ([b for _, b in pairs] if first in valid else [])
    contacts = sum(1 for r in counted if r.get('amrPeerContactCount') != 0)
    charge_ok = sum(1 for k in valid if by[(k, 'charge', 1)]['lowBatteryDockedSamples'] > 0 and by[(k, 'charge', 1)]['doubleChargerReservations'] == 0)

    def verdict(held):
        return ('held' if held else 'wrong') if round_valid else 'void'
    predictions = {
        'P1': {'text': 'median r_k <= 0.95', 'value': as_number(med), 'verdict': verdict(med is not None and med <= Fraction(95, 100))},
        'P2': {'text': 'r_k < 1 in at least 80 % of valid authorings (5x >= 4n)', 'value': f'{lower}/{n}', 'verdict': verdict(n > 0 and 5 * lower >= 4 * n)},
        'P3': {'text': 'predictive completed >= return completed in at least 70 % of valid authorings (10x >= 7n)',
               'value': f'{not_fewer}/{n}', 'verdict': verdict(n > 0 and 10 * not_fewer >= 7 * n)},
        'P4': {'text': 'no AMR-to-AMR contact in any counted run of a valid authoring (including the determinism repeats)',
               'value': f'{contacts}/{len(counted)}', 'verdict': verdict(contacts == 0)},
        'P5': {'text': 'charge rule: the low-battery vehicle docks and no charger is double-reserved, in every valid authoring',
               'value': f'{charge_ok}/{n}', 'verdict': verdict(n > 0 and charge_ok == n)},
    }
    falsifiers = {
        'F1': {'text': 'median r_k >= 1.00', 'triggered': (med is not None and med >= 1) if round_valid else 'void'},
        'F2': {'text': 'predictive completed fewer transfers than return in more than half of valid authorings (2x > n)',
               'value': f'{fewer}/{n}', 'triggered': (2 * fewer > n) if round_valid else 'void'},
    }

    def describe(rule):
        rs = [by[(k, rule, 1)] for k in valid]
        def stats(key, transform=lambda v: v):
            values = [transform(r) for r in rs]
            values = [v for v in values if isinstance(v, (int, float, Fraction))]
            return {'n': len(values), 'median': as_number(middle(values)), 'min': as_number(min(values)) if values else None,
                    'max': as_number(max(values)) if values else None}
        refusals = {}
        for r in rs:
            for reason, count in r['refusals'].items():
                refusals[reason] = refusals.get(reason, 0) + count
        return {'completed': stats('completed', lambda r: r['completed']), 'emptyTravelMeters': stats('e', lambda r: r['emptyTravelMeters']),
                'emptyPerTransfer': stats('p', per_transfer), 'completedIn60s': stats('c', lambda r: r['completedIn60s']),
                'meanTransferSeconds': stats('m', lambda r: r['meanTransferSeconds']),
                'shareAtLeast3Moving': stats('s', lambda r: r['shareAtLeast3Moving']),
                'minMovingAfter10s': stats('v', lambda r: r['minMovingAfter10s']),
                'refusalsTotal': dict(sorted(refusals.items())),
                'peakSpeedMax': max((max(r['peakSpeeds'].values()) for r in rs if r['peakSpeeds']), default=None)}
    look = [per_transfer(by[(k, 'lookahead', 1)]) / per_transfer(by[(k, 'predictive', 1)]) for k in valid
            if by[(k, 'lookahead', 1)]['completed'] and by[(k, 'predictive', 1)]['completed'] and by[(k, 'predictive', 1)]['emptyTravelMeters'] > 0]
    exploratory = {'E1_lookahead_over_predictive_median': as_number(middle(look)),
                   'E1_identical_completion_times': f"{sum(1 for k in valid if by[(k, 'lookahead', 1)]['completionTimes'] == by[(k, 'predictive', 1)]['completionTimes'])}/{n}"}
    return {'schema': 'tr07.tables.v2', 'roundValid': round_valid, 'checks': checks, 'determinismAuthoring': first,
            'validAuthorings': valid, 'invalidAuthorings': invalid, 'denominatorBelow20': n < 20,
            'ratios': {str(k): as_number(v) for k, v in sorted(ratios.items())}, 'predictions': predictions, 'falsifiers': falsifiers,
            'describe': {rule: describe(rule) for rule in RULES}, 'exploratory': exploratory,
            'perAuthoring': {str(k): {rule: {key: by[(k, rule, 1)][key] for key in ('completed', 'emptyTravelMeters', 'completedIn60s',
                                                                                   'meanTransferSeconds', 'amrPeerContactCount')}
                                      for rule in RULES} for k in valid}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('round', type=Path)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in (args.round / 'results.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    ledger = json.loads((args.round / 'run.json').read_text(encoding='utf-8'))
    out = tables(rows, ledger)
    text = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True)
    if args.json:
        args.json.write_text(text + '\n', encoding='utf-8')
    print(f"TR07_TABLES roundValid={out['roundValid']} valid={len(out['validAuthorings'])} " +
          ' '.join(f"{p}={v['verdict']}" for p, v in out['predictions'].items()) + ' ' +
          ' '.join(f"{f}={v['triggered']}" for f, v in out['falsifiers'].items()))
    return 0 if out['roundValid'] else 1


if __name__ == '__main__':
    sys.exit(main())
