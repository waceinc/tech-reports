#!/usr/bin/env python3
"""TR-2026-04 결과 뒤 민감도 분석 — G3 고아 프로세스가 단위 종료 뒤 쓴 답안 8 개를 고정 판정기로 판정한다.

대표 결정 2026-10-02 「늦은 답안 8개 판정 + 상한 공개」. 본 지표가 아니다(공식 회차 밖, 결과를 본 뒤 추가한 분석).
공식 결과 폴더와 공식 작업 폴더는 읽기만 한다 — 단위 폴더를 사본으로 복사하고, 결과는 별도 폴더에 쓴다.
조립·정적 검사·판정은 고정 코드(tr04_개정1)의 assemble.py · static_check.mjs · judge_one.py 를 그대로 부른다
(gen_one.assemble_and_compile 과 run_tr04.judge 의 호출을 그대로 옮김, 수정 기회 없음).

사용: python3 TR-04_민감도_늦은답안판정.py   → 결과 plc-twin-lab/experiments/S2/runs/tr04-sens-late-1/<단위>/verdict.json, 요약 표준 출력
"""
import json, shutil, subprocess, sys, time
from pathlib import Path

FIX = Path(__file__).resolve().parent.parent / '고정입력' / 'tr04_개정1'
HOME = Path.home()
UNITS = ['T07-G3-r1', 'T08-G3-r1', 'T10-G3-r1', 'T12-G3-r1', 'T13-G3-r1', 'T14-G3-r1', 'T15-G3-r1', 'T16-G3-r1']
SENS = HOME / 'tr04-sens'
cfg = json.loads((HOME / 'tr04-run-1' / 'local.json').read_text())
off_results = Path(cfg['results_root'])
cfg['results_root'] = str(off_results.parent / 'tr04-sens-late-1')  # 판정기는 결과 폴더가 브리지 레포 안이어야 한다
cfg['work_root'] = str(SENS / 'work')
(SENS / 'work').mkdir(parents=True, exist_ok=True)
Path(cfg['results_root']).mkdir(parents=True, exist_ok=True)
cfg_path = SENS / 'local_sens.json'
cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
# packfault 기준 실행은 공식 결과의 BASE 를 그대로 쓴다(읽기만)
pf = off_results / 'BASE-cell-b-pack' / 's3-packfault-seed1'
tasks = {t['id']: t for t in json.loads(Path(cfg['task_list']).read_text())['tasks']}

rows = []
for u in UNITS:
    src = HOME / 'tr04-run-1' / 'work' / u
    dst = SENS / 'work' / u
    if not dst.exists():
        shutil.copytree(src, dst)
    t = tasks[u.split('-')[0]]
    kind = 'whole' if t['kind'] == '전체' else 'blank'
    rec = dst / f'assemble-sens-{int(time.time() * 1000)}.json'
    prog = dst / 'assembled.ldprog.json'
    subprocess.run([sys.executable, str(FIX / 'assemble.py'), '--task', str(dst), '--kind', kind, '--start', str(t['rungs'][0]),
                    '--marker', cfg['engine_marker'], '--out', str(prog), '--record', str(rec)], capture_output=True)
    r = json.loads(rec.read_text())
    if not r.get('format_ok'):
        rows.append((u, 'format FAIL', r.get('error')))
        continue
    comp = dst / 'compile.json'
    subprocess.run(['node', str(FIX / 'static_check.mjs'), '--engine-host', cfg['engine_host'], '--program', str(prog),
                    '--io', str(dst / 'io.json'), '--patterns', str(FIX / 'patterns.json'), '--out', str(comp)], capture_output=True)
    s1 = next(c for c in json.loads(comp.read_text())['checks'] if c['id'] == 'S1')
    if s1['status'] != '[PASS]':
        rows.append((u, 'compile FAIL', str(s1.get('detail'))[:120]))
        continue
    subprocess.run([sys.executable, str(FIX / 'judge_one.py'), '--config', str(cfg_path), '--program', str(prog), '--io', str(dst / 'io.json'),
                    '--cell', t['cell'], '--tests', cfg['tests'][t['cell']], '--unit', u, '--packfault-baseline', str(pf)])
    v = json.loads((Path(cfg['results_root']) / u / 'verdict.json').read_text())
    rows.append((u, v['j1'], v['j2'], v['j3'], v.get('j2_passed')))
    print(time.strftime('%H:%M:%S'), rows[-1], flush=True)

print('\n결과')
for r in rows:
    print(' ', r)
