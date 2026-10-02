"""TR-2026-04 one generation unit: (task, generator, repetition) with up to 2 repair rounds.

  python3 gen_one.py --config local.json --package <Txx package folder> --task-json <task entry json>
                     --generator G1|G2|G3 --rep 1|2|3 [--g3-temp 0.7 --g3-seed N]

The generator runs inside isolate.py (read-deny on the configured folders, writes only in its work folder).
After each attempt the output is assembled and compiled outside the sandbox (static check S1 only);
on a compile/format error the error text is handed back, at most twice. Nothing is scanned or simulated here.
Writes <work>/unit.json (attempts, timings, versions, prompt sha256) and leaves out/ in the work folder.
Local paths come only from the config file (see run_tr04.py for the key list).
"""
import argparse, hashlib, json, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPT = ('이 폴더의 TASK.md 를 읽고 그대로 수행하라. 만들 파일 하나만 쓰고, 다른 파일은 만들거나 고치지 않는다.')
REPAIR = ('판정기가 out 폴더의 파일을 받아 컴파일했더니 아래 오류가 났다. TASK.md 규칙을 지키며 같은 파일을 고쳐 다시 써라.\n\n오류:\n')
MAX_REPAIRS = 2


def sha(b):
    return hashlib.sha256(b).hexdigest()


def isolate(cfg, work, net, cmd, timeout, log):
    base = [sys.executable, str(HERE / 'isolate.py'), '--workdir', str(work), '--net', net, '--probe-file', cfg['probe_file'], '--deny-siblings']
    for d in cfg['deny_read']:
        base += ['--deny-read', d]
    for w in cfg.get('allow_write', []):
        base += ['--allow-write', w]
    t0 = time.time()
    with open(log, 'ab') as f:
        try:
            rc = subprocess.run(base + ['--'] + cmd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            rc = 'timeout'
    return rc, round(time.time() - t0, 1)


def g3_cmd(cfg, prompt_file, out_rel, temp, seed):
    return [sys.executable, str(HERE / 'g3_client.py'), '--url', cfg['g3_url'], '--prompt-file', prompt_file,
            '--out', out_rel, '--temperature', str(temp), '--seed', str(seed)]


def assemble_and_compile(cfg, work, task, kind):
    rec = work / f'assemble-{int(time.time() * 1000)}.json'
    prog = work / 'assembled.ldprog.json'
    subprocess.run([sys.executable, str(HERE / 'assemble.py'), '--task', str(work), '--kind', kind,
                    '--start', str(task['rungs'][0]), '--marker', cfg['engine_marker'], '--out', str(prog), '--record', str(rec)],
                   capture_output=True)
    r = json.loads(rec.read_text())
    if not r['format_ok']:
        return False, 'output file: ' + r.get('error', 'missing')
    out = work / 'compile.json'
    subprocess.run(['node', str(HERE / 'static_check.mjs'), '--engine-host', cfg['engine_host'], '--program', str(prog),
                    '--io', str(work / 'io.json'), '--patterns', str(HERE / 'patterns.json'), '--out', str(out)], capture_output=True)
    s1 = next(c for c in json.loads(out.read_text())['checks'] if c['id'] == 'S1')
    return s1['status'] == '[PASS]', s1.get('detail', '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--package', required=True)
    ap.add_argument('--task-json', required=True)
    ap.add_argument('--generator', choices=['G1', 'G2', 'G3'], required=True)
    ap.add_argument('--rep', type=int, required=True)
    ap.add_argument('--g3-temp', type=float, default=0.7)
    ap.add_argument('--g3-seed', type=int)
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    task = json.loads(Path(a.task_json).read_text())
    kind = 'whole' if task['kind'] == '전체' else 'blank'
    unit = f"{task['id']}-{a.generator}-r{a.rep}" + (f'-t{a.g3_temp}' if a.generator == 'G3' and a.g3_temp != 0.7 else '')
    work = Path(cfg['work_root']) / unit
    if (work / 'unit.json').exists():
        print('skip (done)', unit)
        return 0
    if work.exists():
        work.rename(work.with_name(unit + f'.incomplete-{int(time.time())}'))
    shutil.copytree(a.package, work)
    (work / 'out').mkdir(exist_ok=True)
    out_rel = 'out/program.ldprog.json' if kind == 'whole' else 'out/blank.json'
    log = work / 'generator.log'
    attempts = []
    prompt = PROMPT
    for attempt in range(1 + MAX_REPAIRS):
        (work / f'prompt-{attempt}.txt').write_text(prompt, encoding='utf-8')
        if a.generator == 'G1':
            cmd = [cfg['claude_bin'], '-p', prompt, '--model', cfg['g1_model'], '--output-format', 'json',
                   '--allowedTools', 'Read,Write,Edit,Glob,Grep', '--disallowedTools', 'Bash,WebFetch,WebSearch',
                   '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}']
            rc, secs = isolate(cfg, work, 'any', cmd, cfg['timeout_s'], log)
        elif a.generator == 'G2':
            cmd = [cfg['codex_bin'], 'exec', '--skip-git-repo-check', '-C', str(work),
                   '--dangerously-bypass-approvals-and-sandbox', prompt]
            rc, secs = isolate(cfg, work, 'any', cmd, cfg['timeout_s'], log)
        else:
            rc, secs = isolate(cfg, work, 'local', g3_cmd(cfg, f'prompt-{attempt}.txt', out_rel, a.g3_temp, a.g3_seed or a.rep),
                               cfg['timeout_s'], log)
        ok, err = assemble_and_compile(cfg, work, task, kind)
        attempts.append({'attempt': attempt, 'rc': rc, 'seconds': secs, 'prompt_sha256': sha(prompt.encode()), 'compile_ok': ok,
                         'error': None if ok else str(err)[:2000]})
        if ok or rc == 'timeout':
            break
        prompt = REPAIR + str(err)[:4000]
    result = {'unit': unit, 'task': task['id'], 'generator': a.generator, 'rep': a.rep, 'g3_temp': a.g3_temp if a.generator == 'G3' else None,
              'g3_seed': (a.g3_seed or a.rep) if a.generator == 'G3' else None, 'attempts': attempts,
              'repairs_used': len(attempts) - 1, 'compile_ok': attempts[-1]['compile_ok'],
              'output_sha256': sha((work / out_rel).read_bytes()) if (work / out_rel).exists() else None,
              'finished': time.strftime('%Y-%m-%dT%H:%M:%S')}
    (work / 'unit.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    print(unit, 'compile_ok' if result['compile_ok'] else 'compile_fail', 'repairs', result['repairs_used'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
