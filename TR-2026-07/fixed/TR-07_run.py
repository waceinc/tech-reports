#!/usr/bin/env python3
"""TR-2026-07 official runner: dispatch rules in a simulated fleet-control lab, replicated over independent authorings.

For each authoring k = 1..N the application builds the lab from the fixed layout file through its own authoring
stage (new random object identifiers each time). The authored project is checked to equal every other authoring once
identifiers are replaced by one token, identifier-keyed maps are compared as unordered collections and save time, asset
salt and asset signatures are dropped (canonical sha256). Then it is run once under
each of four dispatch rules:
  return      pooled, not predictive: a vehicle drives back to its start position after unloading
  predictive  a vehicle that finished takes the next job where it is (rebalance)
  lookahead   predictive + two-job (joint) dispatch
  charge      predictive + batteries; the vehicle starting at (-7, -4) starts at 20 % (P5 only, not compared)
The first authoring whose four runs are valid runs every rule a second time (determinism check).
A run that ends without a result (crash, timeout) is run again on the same project at most twice; every attempt is kept.
Before anything runs, the layout and every script listed in --fixed must match their fixed sha256.
Output: <out>/results.jsonl (one row per run attempt that counts), <out>/run.json (ledger), per run exit.json.

usage: TR-07_run.py --app <studio binary> --layout <layout.json> --fixed <fixed.json> --product-commit <40 hex>
                    --out <new dir> [--authorings 20] [--horizon 150] [--parallel 4] [--limit 540]
The display (an X server with OpenGL) is taken from the environment.
"""
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

RULES = {
    'return': {'predictiveDispatch': False, 'lookaheadDispatch': False},
    'predictive': {'predictiveDispatch': True, 'lookaheadDispatch': False},
    'lookahead': {'predictiveDispatch': True, 'lookaheadDispatch': True},
    'charge': {'predictiveDispatch': True, 'lookaheadDispatch': False, 'battery': True},
}
BATTERY = {'capacityWh': 1, 'chargeBelowSoc': 0.25, 'connector': 'generic', 'enabled': True, 'idleW': 0.1, 'maxChargeW': 180,
           'payloadWhPerKgMeter': 0.0002, 'reserveSoc': 0.1, 'targetSoc': 0.9, 'travelWhPerMeter': 0.002}
LOW_BATTERY_START = (-7.0, -4.0)
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    """Every identifier becomes "ID"; a map keyed only by identifiers becomes an unordered (sorted) list of its values;
    per-save fields (save time, asset salt, asset signatures) are dropped."""
    if isinstance(value, dict):
        if value and all(UUID.fullmatch(key) for key in value):
            return sorted(json.dumps(canonical(v), ensure_ascii=False, sort_keys=True) for v in value.values())
        return {k: canonical(v) for k, v in value.items() if k not in ('savedAt', 'assetSalt', 'sourceHmacSha256')}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    if isinstance(value, str):
        return UUID.sub('ID', value)
    return value


def canonical_sha256(project_path):
    """Equal for two authorings that differ only in identifiers (and per-save fields)."""
    project = json.loads(Path(project_path).read_text(encoding='utf-8'))
    return hashlib.sha256(json.dumps(canonical(project), ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def author(app, layout, folder, limit):
    env = dict(os.environ, VEXPLOR_FLEET_LAB_LAYOUT=str(layout))
    with open(folder.parent / (folder.name + '.log'), 'wb') as log:
        try:
            code = subprocess.run([str(app), '--qa-stage', 'fleet-lab-author', '--qa-output', str(folder)], env=env,
                                  stdout=log, stderr=subprocess.STDOUT, timeout=limit, start_new_session=True).returncode
        except subprocess.TimeoutExpired:
            code = 'timeout'
    result = folder / 'result.json'
    status = json.loads(result.read_text(encoding='utf-8')).get('status') if result.exists() else None
    return code, status, folder / 'fleet-control-lab' / 'factory.vexplor'


def low_battery_vehicle(project):
    def distance(amr):
        p = next(x for x in project['primitives'] if x['id'] == amr['sceneId'])['transform']['position']
        return math.hypot(p[0] - LOW_BATTERY_START[0], p[2] - LOW_BATTERY_START[1])
    return min(project['amrs'], key=distance)['sceneId']


def rule_project(bundle, folder, flags):
    """Copy the authored project (assets linked, not copied) and set the rule flags."""
    folder.mkdir(parents=True)
    os.symlink(bundle.parent / 'assets', folder / 'assets')
    project = json.loads(bundle.read_text(encoding='utf-8'))
    process = project['dynamics']['process']
    process['predictiveDispatch'] = flags['predictiveDispatch']
    if flags['lookaheadDispatch']:
        process['lookaheadDispatch'] = True
    else:
        process.pop('lookaheadDispatch', None)
    low = low_battery_vehicle(project)
    if flags.get('battery'):
        for amr in project['amrs']:
            amr['profile']['battery'] = {**BATTERY, 'initialSoc': 0.2 if amr['sceneId'] == low else 1.0}
    (folder / 'factory.vexplor').write_text(json.dumps(project, ensure_ascii=False, indent=1), encoding='utf-8')
    return folder / 'factory.vexplor', process.get('directLoadSeconds', 2.5), low


def run_once(app, project, folder, horizon, limit):
    folder.mkdir(parents=True)
    command = [str(app), '--physical-study-child', str(project), '--physical-study-result', str(folder / 'result.json'),
               '--physical-study-diagnostics', str(folder / 'diag.json'), '--physical-study-horizon', str(horizon),
               '--physical-study-scenario', 'tr07', '--physical-study-fast']
    started = time.time()
    with open(folder / 'run.log', 'wb') as log:
        try:
            code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=limit, start_new_session=True).returncode
        except subprocess.TimeoutExpired:
            code = 'timeout'
    exit_info = {'exit': code, 'wallSeconds': round(time.time() - started, 1)}
    (folder / 'exit.json').write_text(json.dumps(exit_info) + '\n', encoding='utf-8')
    return exit_info


def produced_result(folder):
    return all((folder / name).exists() for name in ('result.json', 'diag.json', 'run.log'))


def run(app, project, folder, horizon, limit):
    """Attempt 1, and up to two more on the same project when no result was produced. Returns the counting folder."""
    attempts = []
    for attempt in range(1, 4):
        target = folder / f'attempt{attempt}'
        attempts.append(run_once(app, project, target, horizon, limit))
        if produced_result(target):
            break
    return target, attempts


def measure(folder, load_seconds, low):
    result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    diag = json.loads((folder / 'diag.json').read_text(encoding='utf-8'))
    fleet = result.get('fleet') or {}
    times = fleet.get('completionTimes', [])
    vehicles = fleet.get('vehicles', {})
    samples = diag.get('samples', [])
    loaded_at = {}
    for sample in samples:
        for transfer in sample.get('transfers', []):
            if transfer.get('phase') == 'Loaded' and transfer.get('parcel'):
                loaded_at.setdefault((transfer['amr'], transfer['parcel']), sample['seconds'])
    log = (folder / 'run.log').read_text(encoding='utf-8', errors='replace').splitlines()
    done = [dict(item.split('=', 1) for item in line.split()[1:] if '=' in item) for line in log if line.startswith('DIRECT_HANDOFF_DONE')]
    starts = sorted(loaded_at.items(), key=lambda kv: kv[1])
    durations = []
    for entry in done:
        candidates = [t for (amr, _), t in starts if amr == entry['amr'] and t <= float(entry['t'])]
        if candidates:
            durations.append(float(entry['t']) - (max(candidates) - load_seconds))
    moving = []
    for sample in samples:
        if sample['seconds'] >= 10:
            speeds = [math.hypot(a['body'].get('linearVelocity', [0, 0, 0])[0], a['body'].get('linearVelocity', [0, 0, 0])[2])
                      for a in sample.get('amrs', []) if a['body'].get('available')]
            moving.append(sum(1 for s in speeds if s > 0.05))
    refusals = {}
    for v in vehicles.values():
        for reason, count in v.get('refusals', {}).items():
            refusals[reason] = refusals.get(reason, 0) + count
    runtime = [s.get('runtime', {}).get('vehicles', []) for s in samples]
    docked_by = {}
    for vs in runtime:
        for v in vs:
            if v.get('chargeDocked'):
                docked_by[v['amrId']] = docked_by.get(v['amrId'], 0) + 1
    double = sum(1 for vs in runtime if len([v['charger'] for v in vs if v.get('charger')]) != len({v['charger'] for v in vs if v.get('charger')}))
    empty = fleet.get('emptyTravelMeters', 0)
    completed = result.get('completedTransfers')
    return {'state': result.get('state'), 'error': result.get('error'), 'completed': completed, 'produced': result.get('produced'),
            'released': result.get('released'), 'emptyTravelMeters': empty,
            'completedIn60s': sum(1 for t in times if t <= 60), 'completionTimes': times,
            'meanTransferSeconds': statistics.fmean(durations) if durations else None,
            'minMovingAfter10s': min(moving) if moving else None,
            'shareAtLeast3Moving': sum(1 for m in moving if m >= 3) / len(moving) if moving else None,
            'peakSpeeds': {k: v.get('peakSpeedMetersPerSecond', 0) for k, v in sorted(vehicles.items())},
            'refusals': dict(sorted(refusals.items())), 'lowBatteryVehicle': low,
            'lowBatteryDockedSamples': docked_by.get(low, 0), 'dockedSamplesAll': sum(docked_by.values()),
            'doubleChargerReservations': double, 'amrPeerContactCount': result.get('amrPeerContactCount')}


def check_fixed(fixed_path, layout):
    fixed = json.loads(Path(fixed_path).read_text(encoding='utf-8'))
    here = Path(__file__).resolve().parent
    actual = {'layout': sha256(layout), **{name: sha256(here / name) for name in fixed['scripts']}}
    expected = {'layout': fixed['layout'], **fixed['scripts']}
    wrong = sorted(key for key in expected if expected[key] != actual.get(key))
    return actual, wrong


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', required=True, type=Path)
    parser.add_argument('--layout', required=True, type=Path)
    parser.add_argument('--fixed', required=True, type=Path, help='{"layout": sha256, "scripts": {"TR-07_run.py": sha256, ...}}')
    parser.add_argument('--product-commit', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--authorings', type=int, default=20)
    parser.add_argument('--horizon', type=float, default=150)
    parser.add_argument('--parallel', type=int, default=4)
    parser.add_argument('--limit', type=float, default=540, help='wall seconds per authoring or run attempt')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.product_commit):
        print('TR07_RUN refused: --product-commit must be 40 hex characters')
        return 3
    app, layout = args.app.resolve(strict=True), args.layout.resolve(strict=True)
    actual, wrong = check_fixed(args.fixed, layout)
    if wrong:
        print(f'TR07_RUN refused: fixed sha256 mismatch {wrong}')
        return 3
    out = args.out
    out.mkdir(parents=True)  # a new folder only: an existing round is never touched
    ledger = {'schema': 'tr07.run.v2', 'started': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'productCommit': args.product_commit,
              'appSha256': sha256(app), 'fixedSha256': actual, 'authorings': args.authorings, 'horizonSeconds': args.horizon,
              'parallel': args.parallel, 'host': platform.platform(), 'events': []}
    projects = {}
    for k in range(1, args.authorings + 1):
        folder = out / f'a{k:02d}'
        folder.mkdir()
        code, status, bundle = author(app, layout, folder / 'author', args.limit)
        event = {'authoring': k, 'authorExit': code, 'authorStatus': status,
                 'projectSha256': sha256(bundle) if bundle.exists() else None,
                 'canonicalSha256': canonical_sha256(bundle) if bundle.exists() else None}
        ledger['events'].append(event)
        print(f"tr07 authoring {k}: exit={code} status={status} canonical={str(event['canonicalSha256'])[:12]}", flush=True)
        if status == 'PASS' and bundle.exists():
            projects[k] = {rule: rule_project(bundle, folder / rule / 'project', flags) for rule, flags in RULES.items()}

    def execute(jobs):
        rows = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futures = {pool.submit(run, app, project, folder, args.horizon, args.limit): (k, rule, repeat, load, low)
                       for k, rule, repeat, project, folder, load, low in jobs}
            for future in concurrent.futures.as_completed(futures):
                k, rule, repeat, load, low = futures[future]
                target, attempts = future.result()
                row = {'authoring': k, 'rule': rule, 'repeat': repeat, 'attempts': attempts, 'exit': attempts[-1]['exit'],
                       'folder': str(target.relative_to(out))}
                try:
                    row.update(measure(target, load, low))
                except (OSError, ValueError, KeyError, StopIteration) as error:
                    row['measureError'] = str(error)
                rows.append(row)
                print(f"tr07 a{k:02d} {rule} run{repeat}: attempts={len(attempts)} exit={row['exit']} completed={row.get('completed')}", flush=True)
        return rows

    rows = execute([(k, rule, 1, project, out / f'a{k:02d}' / rule / 'run1', load, low)
                    for k, rules in projects.items() for rule, (project, load, low) in rules.items()])
    good = lambda r: r.get('exit') == 0 and r.get('state') == 'horizon_reached' and not r.get('error') and not r.get('measureError')
    first = next((k for k in sorted(projects) if sum(1 for r in rows if r['authoring'] == k and good(r)) == len(RULES)), None)
    ledger['determinismAuthoring'] = first
    if first is not None:
        rows += execute([(first, rule, 2, project, out / f'a{first:02d}' / rule / 'run2', load, low)
                         for rule, (project, load, low) in projects[first].items()])
    rows.sort(key=lambda r: (r['authoring'], list(RULES).index(r['rule']), r['repeat']))
    with open(out / 'results.jsonl', 'w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
    ledger['finished'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    ledger['runs'] = len(rows)
    ledger['expectedRuns'] = len(RULES) * args.authorings + len(RULES)
    (out / 'run.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"TR07_RUN out={out} runs={len(rows)} expected={ledger['expectedRuns']}", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
