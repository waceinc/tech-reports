"""TR-2026-04 judgment 3 — plant-connected verdict from I/O and plant state only.

Reads one bridge run folder (trace.jsonl) and never uses ladder-internal probes, so a generated ladder
with any internal naming is judged the same way as the reference ladder.
  python3 io_judge.py --run <run folder> --cell cell-a|cell-b|cell-b-pack --scenario <name> [--baseline <run folder>] [--out verdict.json]
Rules (criteria file v1, same numbering):
  J1 no physical plant event (production and neutral bookkeeping events excluded); in packfault, where faults
     are injected on purpose, J1 = physical event names and counts equal the reference ladder's packfault run (--baseline)
  J2 no bridge I/O judgment (e.g. output on while the light curtain is interrupted, handshake done not acknowledged)
  J3 normal scenario completes: A = right/left visited 3 times each in order and all outputs off at the end;
     B = 20 parts, defective parts in the chute or collected route, good parts at the good exit;
     pack = 60 parts packed at the expected stage with one production event each
  J4 curtain: interruption detected while running, drive and pusher commands off while interrupted,
     belt and pusher stopped within 0.265 s of detection
  J5 recovery: recovery step word sequence as specified; recovery-retract likewise
  J6 packfault: pack fault device word and pack fault code word sequences as specified
"""
import argparse, json
from collections import Counter
from pathlib import Path

NEUTRAL = {'PACK_PLACED', 'CONTAINER_EXCHANGED', 'PART_COLLECTED'}
PRODUCTION = {'PART_PACKED', 'REJECT_COLLECTED'}
RECOVERY = {'recovery': [0, 1, 2, 3, 4, 5, 6, 7, 8, 0], 'recovery-retract': [0, 1, 2, 4, 5, 6, 7, 8, 0]}
PACKFAULT = {'P.HMI.faultDevice': [0, 1, 0, 4, 0], 'P.HMI.faultCode': [0, 105, 0, 135, 0]}


def load(run):
    lines = [json.loads(x) for x in (Path(run) / 'trace.jsonl').read_text().splitlines() if x.strip()]
    return [r for r in lines if r.get('type') == 'tick']


def word_sequence(rows, tag):
    seq = []
    for r in rows:
        for s in r['scans']:
            v = s['Q'].get(tag)
            if v is not None and (not seq or seq[-1] != v):
                seq.append(v)
    return seq


def visits(rows):
    seen = []
    for r in rows:
        wanted = 'right' if len(seen) % 2 == 0 else 'left'
        if len(seen) < 6 and any(e['tag'] == f'A.Sen.{wanted}' and e['value'] for e in r['edges']):
            seen.append(wanted)
    return seen


def curtain(rows):
    active = [r for r in rows if r['stimuli'].get('operator.present')]
    hit = next((r for r in active if r['I'].get('B.Safety.curtain')), None)
    if not hit:
        return False, {'reason': 'curtain never detected'}
    before = rows[hit['tick'] - 2]
    stop = next((r for r in rows[hit['tick'] - 1:] if abs(r['state']['belt_v']) < 1e-9 and abs(r['state']['pusher_v']) < 1e-9), None)
    lag = (stop['tick'] - hit['tick']) * .01 if stop else None
    off = all(not r['Q_next']['B.Conv.run'] and not r['Q_next']['B.Psh.sol'] for r in rows[hit['tick'] - 1:] if r['I']['B.Safety.curtain'])
    ok = bool(before['Q']['B.Conv.run']) and off and lag is not None and lag <= .265
    return ok, {'detected_tick': hit['tick'], 'stop_after_s': lag, 'commands_off': off, 'running_before': bool(before['Q']['B.Conv.run'])}


def physical_events(rows):
    return [e for r in rows for e in r['events'] if e['name'] not in NEUTRAL | PRODUCTION]


def judge(run, cell, scenario, baseline=None):
    rows = load(run)
    events = [e for r in rows for e in r['events']]
    physical = physical_events(rows)
    judgments = [j for r in rows for j in r.get('judgments', [])]
    names = Counter(e['name'] for e in physical)
    if scenario == 'packfault':
        if baseline is None:
            raise ValueError('packfault needs --baseline (reference ladder run)')
        expected = Counter(e['name'] for e in physical_events(load(baseline)))
        j1 = (names == expected, {'events': dict(names), 'reference': dict(expected)})
    else:
        j1 = (not physical, {'events': dict(names)})
    checks = {'J1': j1,
              'J2': (not judgments, {'judgments': sorted({j['name'] for j in judgments})})}
    last = rows[-1]
    if scenario == 'normal':
        if cell == 'cell-a':
            v = visits(rows)
            checks['J3'] = (v == ['right', 'left'] * 3 and not any(last['Q_next'].values()), {'visits': v})
        elif cell == 'cell-b':
            parts = last['state']['parts']
            good = [p['id'] for p in parts if not (p['route'] in (1, 3) if p['class'] else p['route'] == 2)]
            checks['J3'] = (len(parts) == 20 and not good, {'parts': len(parts), 'wrong_or_unfinished': good})
        else:
            packed = last['state']['pack']['parts']
            prod = {(e['name'], e['part_id']) for e in events if e['name'] in PRODUCTION}
            ok = len(packed) == 60 and all(p['stage'] == (4 if p['reason'] else 2) for p in packed) and len(prod) == 60
            checks['J3'] = (ok, {'packed': len(packed), 'production_events': len(prod)})
    if scenario == 'curtain':
        checks['J4'] = curtain(rows)
    if scenario in RECOVERY:
        seq = word_sequence(rows, 'B.HMI.recoveryStep')
        checks['J5'] = (seq == RECOVERY[scenario], {'sequence': seq})
    if scenario == 'packfault':
        seqs = {t: word_sequence(rows, t) for t in PACKFAULT}
        checks['J6'] = (all(seqs[t] == PACKFAULT[t] for t in PACKFAULT), seqs)
    status = '[PASS]' if all(ok for ok, _ in checks.values()) else '[FAIL]'
    return {'run': Path(run).name, 'cell': cell, 'scenario': scenario, 'ticks': len(rows), 'status': status,
            'checks': {k: {'status': '[PASS]' if ok else '[FAIL]', 'detail': d} for k, (ok, d) in checks.items()}}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--cell', required=True, choices=['cell-a', 'cell-b', 'cell-b-pack'])
    ap.add_argument('--scenario', required=True)
    ap.add_argument('--baseline')
    ap.add_argument('--out')
    a = ap.parse_args()
    v = judge(a.run, a.cell, a.scenario, a.baseline)
    if a.out:
        Path(a.out).write_text(json.dumps(v, ensure_ascii=False, indent=1) + '\n')
    print(v['status'], a.cell, a.scenario, {k: c['status'] for k, c in v['checks'].items()})
