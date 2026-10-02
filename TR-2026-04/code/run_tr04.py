"""TR-2026-04 batch runner. Meant to be started detached from any agent session (nohup), e.g.
  nohup python3 run_tr04.py --config local.json --phase all > run.log 2>&1 &
Resumable: finished units (unit.json / verdict.json) are skipped. Phases: check, baseline, generate, judge, summary, all.

Config keys (local paths and the engine marker text live only here): engine_host, engine_marker, bridge_root, ladders (reference ladders), results_root (inside bridge_root), work_root,
packages (make_tasks.py output), task_list, tests {cell: file}, deny_read [..], probe_file, allow_write [..],
claude_bin, g1_model, codex_bin, codex_model_check, g3_server_bin, g3_gguf, g3_url, g3_ctx, timeout_s,
fixed_hashes {path: sha256} (checked before any phase).
Status file <results_root>/STATUS.md starts with three lines: 상태 · 요약 · 판정할 것.
"""
import argparse, hashlib, json, subprocess, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = [(g, r) for g in ('G1', 'G2', 'G3') for r in (1, 2, 3)]
CELLS = ('cell-a', 'cell-b', 'cell-b-pack')


def status(cfg, state, summary, decide='0건', body=''):
    p = Path(cfg['results_root']) / 'STATUS.md'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'상태: {state}\n요약: {summary}\n판정할 것: {decide}\n\n{body}\n', encoding='utf-8')


def py(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)


def check(cfg):
    bad = [p for p, h in cfg['fixed_hashes'].items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != h]
    if bad:
        raise SystemExit(f'fixed input hash mismatch: {bad}')
    r = py(HERE / 'isolate.py', '--selftest', '--workdir', Path(cfg['work_root']) / '_selftest', '--probe-file', cfg['probe_file'],
           *sum((['--deny-read', d] for d in cfg['deny_read']), []))
    if r.returncode != 0:
        raise SystemExit('isolation self-check failed:\n' + r.stdout)
    return r.stdout


def tasks(cfg):
    return json.loads(Path(cfg['task_list']).read_text())['tasks']


def baseline(cfg):
    """Reference ladders must pass judgments 1-3 before any generation (units BASE-<cell>)."""
    res = {}
    order = ['cell-b-pack'] + [c for c in CELLS if c != 'cell-b-pack']  # pack first: its packfault run is the J1 baseline
    for cell in order:
        t = next(x for x in tasks(cfg) if x['cell'] == cell and x['kind'] == '전체')
        prog = Path(cfg['ladders']) / cell / 'correct' / 'program.ldprog.json'
        unit = f'BASE-{cell}'
        args = ['--config', cfg['_path'], '--program', prog, '--io', Path(cfg['packages']) / t['id'] / 'io.json', '--cell', cell,
                '--tests', cfg['tests'][cell], '--unit', unit]
        pf = Path(cfg['results_root']) / 'BASE-cell-b-pack' / 's3-packfault-seed1'
        args += ['--packfault-baseline', pf]
        py(HERE / 'judge_one.py', *args)
        v = json.loads((Path(cfg['results_root']) / unit / 'verdict.json').read_text())
        res[cell] = v
    ok = all(v['j1'] == v['j2'] == v['j3'] == '[PASS]' for v in res.values())
    return ok, res


def g3_server(cfg):
    proc = subprocess.Popen([cfg['g3_server_bin'], '-m', cfg['g3_gguf'], '-c', str(cfg['g3_ctx']), '--host', '127.0.0.1',
                             '--port', cfg['g3_url'].rsplit(':', 1)[1].strip('/'), '-np', '1', '--no-webui'],
                            stdout=open(Path(cfg['results_root']) / 'g3_server.log', 'ab'), stderr=subprocess.STDOUT)
    for _ in range(600):
        try:
            if json.loads(urllib.request.urlopen(cfg['g3_url'] + '/health', timeout=5).read()).get('status') == 'ok':
                return proc
        except Exception:
            time.sleep(5)
    proc.terminate()
    raise SystemExit('llama-server did not become ready')


def judge(cfg):
    pf = Path(cfg['results_root']) / 'BASE-cell-b-pack' / 's3-packfault-seed1'
    for work in sorted(Path(cfg['work_root']).glob('T*-G*-r*')):
        if not (work / 'unit.json').exists() or '.incomplete' in work.name:
            continue
        u = json.loads((work / 'unit.json').read_text())
        t = next(x for x in tasks(cfg) if x['id'] == u['task'])
        prog = work / 'assembled.ldprog.json'
        if not u['compile_ok'] or not prog.exists():
            vd = Path(cfg['results_root']) / work.name
            vd.mkdir(parents=True, exist_ok=True)
            if not (vd / 'verdict.json').exists():
                (vd / 'verdict.json').write_text(json.dumps({'unit': work.name, 'cell': t['cell'], 'j1': '[FAIL]', 'j2': '[NOT_RUN]',
                                                            'j3': '[NOT_RUN]', 'reason': 'no compilable output after repairs'}) + '\n')
            continue
        py(HERE / 'judge_one.py', '--config', cfg['_path'], '--program', prog, '--io', work / 'io.json', '--cell', t['cell'],
           '--tests', cfg['tests'][t['cell']], '--unit', work.name, '--packfault-baseline', pf)


def summary(cfg):
    # sample = 189 units Txx-Gy-rN; the G3 temperature-0 determinism units (suffix -t0.0) are reported apart
    rows = [json.loads(p.read_text()) for p in Path(cfg['results_root']).glob('T*/verdict.json') if '-t' not in p.parent.name]
    passed12 = [r for r in rows if r['j1'] == '[PASS]' and r['j2'] == '[PASS]']
    only3 = [r for r in passed12 if r['j3'] == '[FAIL]']
    s = f"판정 {len(rows)} · ①② 통과 {len(passed12)} · 그중 ③만 [FAIL] {len(only3)}"
    (Path(cfg['results_root']) / 'summary.json').write_text(json.dumps({'units': len(rows), 'passed_1_2': len(passed12),
                                                                      'only_3_fail': len(only3), 'rows': rows}, ensure_ascii=False, indent=1))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--phase', choices=['check', 'baseline', 'generate', 'judge', 'summary', 'all'], required=True)
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    cfg['_path'] = str(Path(a.config).resolve())
    status(cfg, '진행 중', f'단계 {a.phase} 시작')
    try:
        log = check(cfg)
        if a.phase in ('baseline', 'all'):
            ok, res = baseline(cfg)
            if not ok:
                status(cfg, '중단(기준 래더가 판정 ①②③ 중 하나를 통과하지 못함)', '기준 래더 점검 실패', '1건',
                       '- [대표께] 기준 래더 점검 실패 — 추천안: 원인 조사 전 생성 금지\n\n' + json.dumps(res, ensure_ascii=False, indent=1))
                return 1
        if a.phase in ('generate', 'all'):
            server = None
            try:
                generate_cloud = [(g, r) for g, r in ORDER if g != 'G3']
                for gen, rep in generate_cloud:
                    _gen_round(cfg, gen, rep, [])
                server = g3_server(cfg)
                for rep in (1, 2, 3):
                    _gen_round(cfg, 'G3', rep, ['--g3-temp', '0.7', '--g3-seed', str(rep)])
                _gen_round(cfg, 'G3', 1, ['--g3-temp', '0', '--g3-seed', '1'])  # determinism control, outside the sample
            finally:
                if server:
                    server.terminate()
        if a.phase in ('judge', 'all'):
            judge(cfg)
        s = summary(cfg) if a.phase in ('summary', 'judge', 'all') else f'단계 {a.phase} 끝'
        status(cfg, '완료', s, body=log)
        return 0
    except SystemExit as e:
        status(cfg, f'중단({e})', '점검 실패')
        return 1


def _gen_round(cfg, gen, rep, extra):
    for t in tasks(cfg):
        tj = Path(cfg['work_root']) / '_tasks' / f"{t['id']}.json"
        tj.parent.mkdir(parents=True, exist_ok=True)
        tj.write_text(json.dumps(t, ensure_ascii=False))
        py(HERE / 'gen_one.py', '--config', cfg['_path'], '--package', Path(cfg['packages']) / t['id'], '--task-json', tj,
           '--generator', gen, '--rep', rep, *extra)
    status(cfg, '진행 중', f'생성 {gen} r{rep}{" " + " ".join(extra) if extra else ""} 끝')


if __name__ == '__main__':
    sys.exit(main())
