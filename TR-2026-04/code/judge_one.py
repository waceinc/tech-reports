"""TR-2026-04 judgments 1-3 for one assembled program.

  python3 judge_one.py --config local.json --program <assembled.ldprog.json> --io <io.json> --cell <cell>
                       --tests <cell tests json> --unit <name> [--packfault-baseline <run folder>]

1 static (static_check.mjs, all of S1-S4) -> 2 input forcing (force_test.mjs, needs S1) ->
3 plant connection (bridge run per scenario + io_judge.py, needs 1 [PASS]). Writes <results_root>/<unit>/verdict.json.
The bridge run module and the program location must be inside the bridge work root (config keys bridge_root, results_root).
"""
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIOS = {  # (scenario, seed, ticks) — pre-registered
    'cell-a': [('normal', 1, 1000)],
    'cell-b': [('normal', 1, 5000), ('normal', 2, 5000), ('normal', 3, 5000), ('curtain', 1, 1000),
               ('recovery', 1, 3420), ('recovery-retract', 1, 3420)],
    'cell-b-pack': [('normal', 1, 10000), ('normal', 2, 10000), ('normal', 3, 10000), ('packfault', 1, 6000)],
}
RUN = ('import sys,json;sys.path.insert(0,sys.argv[1]);import run as R;'
       'r=R.run(sys.argv[2],sys.argv[3],sys.argv[4],ticks=int(sys.argv[5]),seed=int(sys.argv[6]),scenario=sys.argv[7])')


def node(script, *args):
    return subprocess.run(['node', str(HERE / script), *args], capture_output=True, text=True, timeout=3600)


def main():
    ap = argparse.ArgumentParser()
    for k in ('--config', '--program', '--io', '--cell', '--tests', '--unit'):
        ap.add_argument(k, required=True)
    ap.add_argument('--packfault-baseline')
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    unit_dir = Path(cfg['results_root']) / a.unit
    if (unit_dir / 'verdict.json').exists():
        print('skip (done)', a.unit)
        return 0
    unit_dir.mkdir(parents=True, exist_ok=True)
    prog = unit_dir / 'program.ldprog.json'
    shutil.copyfile(a.program, prog)
    v = {'unit': a.unit, 'cell': a.cell, 'j1': '[NOT_RUN]', 'j2': '[NOT_RUN]', 'j3': '[NOT_RUN]', 'j3_runs': []}
    node('static_check.mjs', '--engine-host', cfg['engine_host'], '--program', str(prog), '--io', a.io,
         '--patterns', str(HERE / 'patterns.json'), '--out', str(unit_dir / 'static.json'))
    st = json.loads((unit_dir / 'static.json').read_text())
    v['j1'] = st['status']
    s1 = next((c['status'] for c in st['checks'] if c['id'] == 'S1'), '[FAIL]')
    if s1 == '[PASS]':
        node('force_test.mjs', '--engine-host', cfg['engine_host'], '--program', str(prog), '--tests', a.tests,
             '--out', str(unit_dir / 'force.json'))
        ft = json.loads((unit_dir / 'force.json').read_text())
        v['j2'] = ft['status']
        v['j2_passed'] = f"{ft['passed']}/{ft['tests']}"
    if v['j1'] == '[PASS]':
        variant = os.path.relpath(unit_dir, Path(cfg['bridge_root']) / 'ladders' / a.cell)
        ok = True
        for scenario, seed, ticks in SCENARIOS[a.cell]:
            out = unit_dir / f's3-{scenario}-seed{seed}'
            try:
                p = subprocess.run([sys.executable, '-c', RUN, str(Path(cfg['bridge_root']) / 'bridge'), a.cell, variant, str(out),
                                    str(ticks), str(seed), scenario], cwd=cfg['bridge_root'], capture_output=True, text=True,
                                   timeout=3600, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                rc = p.returncode
            except subprocess.TimeoutExpired:
                rc = 'timeout'
            item = {'scenario': scenario, 'seed': seed, 'ticks': ticks, 'bridge_rc': rc}
            procs = out / 'processes.json'
            item['processes'] = json.loads(procs.read_text())['status'] if procs.exists() else '[FAIL]'
            # The bridge's own end-of-run summary may read ladder-internal probes that a generated ladder does not have
            # (it then writes failure.json after the last tick). Judgment 3 uses only the trace, so a run counts as finished
            # when every tick is in the trace and the child processes closed cleanly.
            fail = json.loads((out / 'failure.json').read_text()) if (out / 'failure.json').exists() else None
            finished = (out / 'trace.jsonl').exists() and item['processes'] == '[PASS]' and (fail is None or fail.get('completed_ticks') == ticks)
            item['bridge_summary_error'] = fail.get('error') if fail else None
            if finished:
                jargs = [sys.executable, str(HERE / 'io_judge.py'), '--run', str(out), '--cell', a.cell, '--scenario', scenario,
                         '--out', str(out / 'io_verdict.json')]
                if scenario == 'packfault':
                    jargs += ['--baseline', a.packfault_baseline]
                subprocess.run(jargs, capture_output=True)
                item['status'] = json.loads((out / 'io_verdict.json').read_text())['status']
            else:
                item['status'] = '[FAIL]'
                item['reason'] = 'run did not finish (ticks missing, no trace or child process not closed)'
            ok = ok and item['status'] == '[PASS]'
            v['j3_runs'].append(item)
        v['j3'] = '[PASS]' if ok else '[FAIL]'
    (unit_dir / 'verdict.json').write_text(json.dumps(v, ensure_ascii=False, indent=1) + '\n')
    print(a.unit, v['j1'], v['j2'], v['j3'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
