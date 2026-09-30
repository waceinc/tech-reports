#!/usr/bin/env python3
"""TR-2026-03 공식 실행기 — 사전 등록 v0.3 §4 의 원본 기준 38 회 + 변종 3,680 회를 고정 순서로 돌린다.

하는 일은 고정 입력 확인·변종 래더 준비·순서 정하기·호출·기록뿐이다. 판정·4단계 분류·집계는 하지 않는다(분석은 별도).
- 조합 순서: 셀 A → 셀 B → 포장 셀(짧은 셀 먼저). 셀마다 원본 기준(시나리오 × 2 회) → 추출 변종(목록 번호 순) × 시나리오(§4 표 순).
  번호는 이 순서로 1 부터. --list 로 전체와 셀별 수를 찍고, 사전 등록 §3-2 값과 다르면 실행하지 않는다.
- 변종 래더: 고정 생성기(고정입력/TR-03_변종적용_컴파일검사.mjs)로 <회차>/ladders/ 에 만든다(레포 ladders/ 에 쓰지 않는다).
  래더마다 sha256 을 ladders-sha256.json 과 ledger 에 남긴다.
- 출력: plc-twin-lab/experiments/S2/runs/<회차>/<번호>-<설명>/ · 기록: <회차>/ledger.jsonl(한 건 끝날 때마다 1 줄 append)
- 상태: <회차>/STATUS.txt 첫 줄 「상태: 진행 중 | 완료 | 중단(사유)」
- 이어서 실행: 같은 --round 로 다시 부르면 ledger 에 있는 번호는 건너뛴다. 무효 실행은 재실행하지 않는다(§7).
  기록 없이 폴더만 남은 번호(실행기가 끊긴 경우)는 <회차>/_interrupted/ 로 옮기고 다시 돌린다 — 편 전체 2 회까지(§7 재시도 상한).
- 한 건 시간 제한: 300 초 + 틱 × 0.02 초. 넘으면 프로세스 묶음을 끝내고 rc='timeout' 으로 기록한다(재실행하지 않는다).
- 원본 기준 실행이 오류(rc≠0 · 시간 초과)로 끝난 (셀, 시나리오)는 그 셀 변종 실행을 돌리지 않고 skipped 로 기록한다(§4).
- trace.jsonl · reference-10ms-differences.json 은 끝난 뒤 gzip 으로 바꾼다(원본 sha256 을 ledger 에 먼저 남김).
  포장 셀 10,000 틱 1 회가 약 0.5 GB 라, 원본 그대로 두면 변종 실행 전체가 약 640 GB 로 남은 디스크를 넘는다.
- --max-seconds: 그 시간을 넘으면 다음 건을 시작하지 않고 「중단(분할 종료 …)」으로 끝낸다(종료 코드 4). 같은 --round 로 이어서.

사용: python3 TR-03_공식실행.py --round tr03-official-1 [--list] [--max-seconds 540]
      python3 TR-03_공식실행.py --prepare-ladders <plc-twin-lab 안 폴더>   (변종 래더만 만들고 해시 확인, 실행 없음)
"""
import argparse, hashlib, importlib.util, json, os, signal, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMON = HERE / 'TR03_공통.py'
COMMON_SHA = '508322e8d397659f932342310c78044b201ac759c58277748424ad1ec67ec92c'
ADAPTER = HERE / 'TR-03_변종실행_어댑터.py'
ADAPTER_SHA = '0caed4f0d7fe72c62e9eb76048413778afc0c3b5610679463a959454fc84b2a7'
MAX_INTERRUPTS = 2


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_common():
    if sha(COMMON) != COMMON_SHA:
        return None
    spec = importlib.util.spec_from_file_location('tr03_common', COMMON)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def run_one(C, c, rel, ladder):
    """어댑터를 새 프로세스 묶음으로 띄운다. 시간 초과면 묶음 전체를 끝낸다."""
    cmd = [sys.executable, str(ADAPTER), '--cell', c['cell'], '--ladder', str(ladder), '--scenario', c['scenario'],
           '--seed', str(c['seed']), '--ticks', str(c['ticks']), '--output', str(rel)]
    if c['flow'] is not None:
        cmd += ['--flow', str(c['flow'])]
    if c['variant_id']:
        cmd += ['--variant-id', c['variant_id']]
    limit = 300 + c['ticks'] * 0.02
    p = subprocess.Popen(cmd, cwd=C.LAB, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=limit)
        return p.returncode, out[-600:]
    except subprocess.TimeoutExpired:
        for sig, wait in ((signal.SIGTERM, 15), (signal.SIGKILL, 15)):
            try:
                os.killpg(p.pid, sig)
            except ProcessLookupError:
                break
            try:
                p.communicate(timeout=wait)
                break
            except subprocess.TimeoutExpired:
                continue
        return 'timeout', f'시간 제한 {limit:.0f} 초 초과'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--round')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--max-seconds', type=float)
    ap.add_argument('--prepare-ladders', type=Path)
    a = ap.parse_args()
    C = load_common()
    if C is None:
        print('[FAIL] TR03_공통.py sha256 불일치')
        return 2
    if sha(ADAPTER) != ADAPTER_SHA:
        print('[FAIL] 어댑터 sha256 불일치')
        return 2
    data = C.load_list()
    if data is None:
        print('[FAIL] 변종 목록 sha256 불일치 — 사전 등록 §8')
        return 2
    cs = C.combos(data)
    table, bad = C.count_check(data, cs)
    if a.list:
        for c in cs:
            print(c['name'])
        for cell, t in table.items():
            print(f'{cell}: 원본 기준 {t["baseline_runs"]} · 변종 {t["variants"]} · 변종 실행 {t["variant_runs"]} · 추정 {t["est_hours"]} 시간')
        print(f'[{"OK" if not bad else "FAIL"}] 전체 {len(cs)} 실행' + (f' — 사전 등록과 다름: {bad}' if bad else ''))
        return 0 if not bad else 3
    if bad:
        print(f'[FAIL] 조합 수가 사전 등록과 다름: {bad}')
        return 3
    if a.prepare_ladders:
        dst = a.prepare_ladders.resolve()
        if not dst.is_relative_to(C.LAB / C.RUNS_REL):
            print('[FAIL] 준비 폴더는 plc-twin-lab/experiments/S2/runs 아래만')
            return 2
        lt, lsha, errs = C.prepare_ladders(dst, data)
        print(json.dumps(dict(ladders=len(lt or {}), table_sha256=lsha, errors=errs), ensure_ascii=False))
        return 0 if not errs else 1
    if not a.round:
        ap.error('--round 필요')

    root = C.LAB / C.RUNS_REL / a.round
    root.mkdir(parents=True, exist_ok=True)
    status, ledger, header = root / 'STATUS.txt', root / 'ledger.jsonl', root / 'run-header.json'
    self_sha = sha(__file__)

    def set_status(line, extra=''):
        status.write_text(f'{line}\n{extra}', encoding='utf-8')

    fixed_bad = C.fixed_input_check()
    (root / f'fixed-inputs-{time.strftime("%Y%m%d-%H%M%S")}.json').write_text(
        json.dumps(dict(when=now(), mismatch=fixed_bad), ensure_ascii=False) + '\n', encoding='utf-8')
    if fixed_bad:
        set_status('상태: 중단(고정 입력 sha256 불일치 — 사전 등록 §7 무효 기준)', '\n'.join(fixed_bad) + '\n')
        return 2
    ldir = root / 'ladders'
    if header.exists():
        h = json.loads(header.read_text(encoding='utf-8'))
        if h['runner_sha256'] != self_sha or h['common_sha256'] != COMMON_SHA or h['adapter_sha256'] != ADAPTER_SHA:
            set_status('상태: 중단(실행기·어댑터가 첫 시작 때와 다름)', f'첫 시작 {h}\n')
            return 2
        lt, lbad = C.verify_ladders(ldir)
        if lbad or C.sha(ldir / 'ladders-sha256.json') != h['ladders_table_sha256']:
            set_status('상태: 중단(변종 래더가 준비 때와 다름)', f'{lbad[:20]}\n')
            return 2
    elif ldir.exists():
        set_status('상태: 중단(래더 폴더는 있는데 첫 시작 기록이 없음 — 준비 도중 끊김, 사람이 확인)', '')
        return 2
    else:
        lt, lsha, errs = C.prepare_ladders(ldir, data)
        if errs:
            set_status('상태: 중단(변종 래더 준비 실패)', '\n'.join(errs[:20]) + '\n')
            return 2
        header.write_text(json.dumps(dict(started=now(), runner_sha256=self_sha, common_sha256=COMMON_SHA, adapter_sha256=ADAPTER_SHA,
                                          list_sha256=C.LIST_SHA, generator_mjs_sha256=C.MJS_SHA, manifest_sha256=C.MANIFEST_SHA,
                                          ladders_table_sha256=lsha, python=sys.version.split()[0], counts=table),
                                     ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    records = {}
    if ledger.exists():
        for line in ledger.read_text(encoding='utf-8').splitlines():
            if line.strip():
                r = json.loads(line)
                records[r['no']] = r
    ilog = root / 'interrupted.jsonl'
    interrupts = sum(1 for l in ilog.read_text(encoding='utf-8').splitlines() if l.strip()) if ilog.exists() else 0
    for c in cs:
        d = root / c['name']
        if c['no'] not in records and d.exists():
            if interrupts >= MAX_INTERRUPTS:
                set_status(f'상태: 중단(끊긴 실행 재시도 상한 {MAX_INTERRUPTS} 회 초과 — {c["name"]})', '')
                return 2
            interrupts += 1
            dest = root / '_interrupted' / f'{c["name"]}-{interrupts}'
            dest.parent.mkdir(exist_ok=True)
            d.rename(dest)
            with ilog.open('a', encoding='utf-8') as f:
                f.write(json.dumps(dict(no=c['no'], name=c['name'], moved_to=str(dest.relative_to(root)), when=now()), ensure_ascii=False) + '\n')

    total = len(cs)
    started = time.time()
    set_status('상태: 진행 중', f'시작 {now()} · 실행기 {self_sha} · 공통 {COMMON_SHA} · 어댑터 {ADAPTER_SHA} · 기록 {len(records)}/{total}\n')
    for c in cs:
        if c['no'] in records:
            continue
        if a.max_seconds is not None and time.time() - started > a.max_seconds:
            set_status('상태: 중단(분할 종료 — 같은 --round 로 이어서 실행)', f'끝 {now()} · 기록 {len(records)}/{total}\n')
            return 4
        ladder = (C.LAB / f'ladders/{c["cell"]}/correct/program.ldprog.json' if c['kind'] == 'baseline'
                  else ldir / c['variant_id'] / 'program.ldprog.json')
        rel = C.RUNS_REL / a.round / c['name']
        rec = {k: c[k] for k in ('no', 'name', 'kind', 'cell', 'variant_id', 'group', 'key', 'scenario', 'seed', 'flow', 'ticks', 'rep')}
        rec['ladder_sha256'] = sha(ladder)
        base_err = [r for r in records.values() if r['kind'] == 'baseline' and r['cell'] == c['cell'] and r['key'] == c['key'] and r['rc'] != 0]
        if c['kind'] == 'variant' and base_err:
            rec.update(rc=None, skipped='원본 기준 실행 오류 — §4 에 따라 이 셀에서 무효', seconds=0, ended=now())
        else:
            t0 = time.time()
            rc, tail = run_one(C, c, rel, ladder)
            out = C.LAB / rel
            side = out / 'tr03-adapter.json'
            s = json.loads(side.read_text()) if side.exists() else None
            procs = json.loads((out / 'processes.json').read_text()).get('status') if (out / 'processes.json').exists() else None
            fail = json.loads((out / 'failure.json').read_text()) if (out / 'failure.json').exists() else None
            packed = [C.gzip_replace(out / n) for n in ('trace.jsonl', 'reference-10ms-differences.json')]
            rec.update(rc=rc, seconds=round(time.time() - t0, 1), trace_hash=s and s['trace_hash'], status=s and s['status'],
                       processes=procs, failure=fail and fail.get('error', '')[:300], files=[x for x in packed if x],
                       tail=None if s else tail, ended=now())
        with ledger.open('a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        records[c['no']] = rec
        set_status('상태: 진행 중', f'{c["no"]}/{total} · 마지막 {c["name"]} rc={rec["rc"]}\n')
    after = C.fixed_input_check()
    (root / f'fixed-inputs-{time.strftime("%Y%m%d-%H%M%S")}-end.json').write_text(
        json.dumps(dict(when=now(), mismatch=after), ensure_ascii=False) + '\n', encoding='utf-8')
    if after:
        set_status('상태: 중단(실행 중 고정 입력 변경 감지 — 사전 등록 §7 무효 기준)', '\n'.join(after) + '\n')
        return 2
    n = len(records)
    set_status('상태: 완료' if n == total else f'상태: 중단(기록 {n}/{total})', f'끝 {now()}\n')
    return 0 if n == total else 2


if __name__ == '__main__':
    sys.exit(main())
