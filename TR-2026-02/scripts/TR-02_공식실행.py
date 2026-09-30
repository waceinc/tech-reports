#!/usr/bin/env python3
"""TR-2026-02 공식 실행기 — 사전 등록 v0.3 §4 의 816 실행을 고정 순서로 돌린다.

하는 일은 순서 정하기·호출·기록뿐이다. 판정·집계는 하지 않는다(결과 분석은 별도 스크립트).
- 조합 순서: 공장 연결 12 → 펄스 없는 기준 4 → 짧은 펄스 800. 번호는 이 순서로 1 부터.
- 출력: plc-twin-lab/experiments/S2/runs/<회차>/<번호>-<설명>/ (어댑터가 쓰는 곳)
- 실행 기록: <회차>/ledger.jsonl — 한 건 끝날 때마다 1 줄 append(끊겨도 남는다)
- 상태: <회차>/STATUS.txt 첫 줄 「상태: 진행 중 | 완료 | 중단(사유)」
- 다시 부르면 ledger 에 끝난 번호는 건너뛴다(같은 회차 이어서). 무효 실행은 재실행하지 않는다 — 사전 등록 §6.

사용: python3 TR-02_공식실행.py --round tr02-official-1 [--list]
"""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADAPTER = HERE.parent / '고정입력' / 'TR-02_연결조건_어댑터.py'
ADAPTER_SHA = 'f5241b5f5d5286ff6366bdff33da8ec599e343d67ba6fd1ebaf129f1a7d10c40'
LAB = Path('<repos>/plc-twin-lab')
MODES = ['history', 'boundary']
PULSE_TAGS = ['A.PB.stop_nc', 'A.PB.estop_nc', 'A.Sen.left', 'A.Sen.right']
WIDTHS = [5, 15, 25, 35, 45]
PHASES = list(range(0, 50, 5))
TIMEOUT_S = 1800


def combos():
    out = []
    for v in ['correct', 'late-reverse', 'swapped-sensors']:
        for m in MODES:
            for rep in (1, 2):
                out.append(dict(kind='plant', variant=v, mode=m, rep=rep, ticks=1000, pulse=None))
    for m in MODES:
        for rep in (1, 2):
            out.append(dict(kind='baseline', variant='correct', mode=m, rep=rep, ticks=200, pulse=None))
    for tag in PULSE_TAGS:
        for w in WIDTHS:
            for ph in PHASES:
                for m in MODES:
                    for rep in (1, 2):
                        out.append(dict(kind='pulse', variant='correct', mode=m, rep=rep, ticks=200,
                                        pulse=f'{tag}:100:{ph}:{w}'))
    for i, c in enumerate(out, 1):
        p = c['pulse'].replace(':', '-').replace('.', '') if c['pulse'] else c['kind']
        c['no'] = i
        c['name'] = f"{i:04d}-{c['variant']}-{c['mode']}-r{c['rep']}-{p}"
    return out


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--round', required=True)
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    cs = combos()
    assert len(cs) == 816, len(cs)
    if a.list:
        for c in cs:
            print(c['name'])
        print(f'[OK] {len(cs)} 실행')
        return 0
    rel = Path('experiments/S2/runs') / a.round
    root = LAB / rel
    root.mkdir(parents=True, exist_ok=True)
    status = root / 'STATUS.txt'
    ledger = root / 'ledger.jsonl'

    def set_status(line, extra=''):
        status.write_text(f'{line}\n{extra}')

    if sha(ADAPTER) != ADAPTER_SHA:
        set_status('상태: 중단(어댑터 sha256 불일치 — 사전 등록 §6 무효 기준)')
        return 2
    done = set()
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)['no'])
    set_status('상태: 진행 중', f'시작 {time.strftime("%Y-%m-%d %H:%M:%S")} · 실행기 {sha(__file__)} · 어댑터 {ADAPTER_SHA}\n')
    for c in cs:
        if c['no'] in done:
            continue
        out_rel = rel / c['name']
        cmd = [sys.executable, str(ADAPTER), '--mode', c['mode'], '--variant', c['variant'],
               '--ticks', str(c['ticks']), '--output', str(out_rel)]
        if c['pulse']:
            cmd += ['--pulse', c['pulse']]
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=LAB, capture_output=True, text=True, timeout=TIMEOUT_S)
            rc, tail = p.returncode, (p.stdout + p.stderr)[-600:]
        except subprocess.TimeoutExpired:
            rc, tail = 'timeout', ''
        side = LAB / out_rel / 'tr02-adapter.json'
        procs = LAB / out_rel / 'processes.json'
        rec = dict(no=c['no'], name=c['name'], kind=c['kind'], variant=c['variant'], mode=c['mode'], rep=c['rep'],
                   ticks=c['ticks'], pulse=c['pulse'], rc=rc, seconds=round(time.time() - t0, 1),
                   trace_hash=json.loads(side.read_text())['trace_hash'] if side.exists() else None,
                   status=json.loads(side.read_text())['status'] if side.exists() else None,
                   processes=json.loads(procs.read_text()).get('status') if procs.exists() else None,
                   tail=None if side.exists() else tail, ended=time.strftime('%Y-%m-%d %H:%M:%S'))
        with ledger.open('a') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        set_status('상태: 진행 중', f'{c["no"]}/816 · 마지막 {c["name"]} rc={rc}\n')
    n = sum(1 for l in ledger.read_text().splitlines() if l.strip())
    set_status('상태: 완료' if n == 816 else f'상태: 중단(기록 {n}/816)', f'끝 {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
