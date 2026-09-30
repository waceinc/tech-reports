#!/usr/bin/env python3
"""TR-2026-03 결과 분석 — 사전 등록 v0.3 §5(4단계) · §6(지표 1~3) · §7(예측 P1·P2 · 무효 기준)을 정의 그대로 집계한다.

입력(읽기만): 공식 실행 결과 폴더(<plc-twin-lab>/experiments/S2/runs/<회차>/) 의 ledger.jsonl · STATUS.txt · run-header.json ·
fixed-inputs-*.json · 번호별 summary.json · tr03-adapter.json · processes.json · trace.jsonl[.gz] · failure.json.
출력: 이 폴더의 TR-03_결과_<회차>.json · TR-03_결과_<회차>.md — 시각·실행 환경·절대 경로를 넣지 않아 두 번 돌리면 바이트가 같다.
1단계(미활성)는 원본 래더를 원본 기준 실행(반복 1)의 스캔별 입력으로 다시 스캔해 정한다(TR03_분석_재스캔.mjs, 브리지 reconstruct).
결과 전에 고정한 해석은 TR-03_분석_고정기록.md 「결과 전 해석」(I-1~I-8).
사용: python3 TR-03_분석.py <결과 폴더> [--lab <plc-twin-lab 루트>] [--jobs N]
"""
import argparse, hashlib, json, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True  # 레포·고정입력에 __pycache__ 를 만들지 않는다
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from TR03_분석_읽기 import AUDIT_ERRORS, Rescan, compare, extract  # noqa: E402
from TR03_분석_집계 import CELLS, SETS, classify, metrics, predictions, representatives  # noqa: E402
from TR03_분석_표 import render  # noqa: E402

LIST = HERE.parent / '고정입력' / 'TR-03_변종목록_v1.json'
LIST_SHA = 'bc61eab488b39600724eda60071b1d86da05af33b56965582464ebcb62ef1f67'
ADAPTER_SHA = '0caed4f0d7fe72c62e9eb76048413778afc0c3b5610679463a959454fc84b2a7'
BASE_LADDER_SHA = {'cell-a': '5058bd0b97644e66c0310a540a0403931bf6bd8195445576430d6dd1cabf8ef1',
                   'cell-b': '05999e23b90b265f9907e0cd05f5469eccec6195e43326310bb9b491bd4ed0b1',
                   'cell-b-pack': '5a4cc91db8f6e53197e613ff87426bc94438a0b7c3226946417b2aa407b53fb1'}
SCEN_ORDER = {'cell-a': ['normal', 'cycle-stop'],
              'cell-b': ['normal-s1', 'normal-s2', 'normal-s3', 'cycle-stop', 'curtain', 'recovery', 'recovery-retract',
                         'batch', 'stroke75', 'flow060', 'flow045'],
              'cell-b-pack': ['normal-s1', 'normal-s2', 'normal-s3', 'cycle-stop', 'curtain', 'packfault']}
EXPECTED = {'cell-a': (25, 50), 'cell-b': (156, 1716), 'cell-b-pack': (319, 1914)}
MODULES = ['TR-03_분석.py', 'TR03_분석_읽기.py', 'TR03_분석_집계.py', 'TR03_분석_표.py', 'TR03_분석_재스캔.mjs']


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read_json(p):
    return json.loads(Path(p).read_text(encoding='utf-8')) if Path(p).is_file() else None


def run_check(root, r, ladders_table):
    """실행 1 건의 무효 기준(§7 → TR-2026-02 §6) 대조. 반환: (사유 목록, 기록된 trace 원본 sha256)."""
    if r.get('skipped'):
        return ['건너뜀: ' + r['skipped']], None
    d, why = root / r['name'], []
    fail = read_json(d / 'failure.json')
    if r['rc'] != 0:
        err = (fail or {}).get('error', r.get('failure') or '')
        audit = any(a in (err or '') for a in AUDIT_ERRORS)
        why.append(('무효: 입력 복원 감사 실패' if audit else '실행 오류(분류 밖)') + f" rc={r['rc']} {str(err)[:160]}")
    if r.get('processes') != '[PASS]':
        why.append(f"무효: 자식 프로세스 회수 {r.get('processes')}")
    side, summ = read_json(d / 'tr03-adapter.json'), read_json(d / 'summary.json')
    if r['rc'] == 0:
        if not side or side.get('adapter_sha256') != ADAPTER_SHA:
            why.append('무효: 어댑터 sha256 기록 불일치')
        if not summ or not side or not (summ['trace_hash'] == side['trace_hash'] == r['trace_hash']) or summ['status'] != r['status']:
            why.append('무효: summary·어댑터·ledger 해시 불일치')
        want = BASE_LADDER_SHA[r['cell']] if r['kind'] == 'baseline' else (ladders_table.get(r['variant_id']) or {}).get('program')
        if r.get('ladder_sha256') != want or (side and side.get('ladder_sha256') != want):
            why.append('무효: 래더 sha256 불일치')
    rec = next((f['sha256'] for f in r.get('files') or [] if f.get('file') == 'trace.jsonl'), None)
    return why, rec


def _extract(job):
    root, name, rec_sha = job
    x = extract(Path(root) / name)
    if 'error' not in x and rec_sha and x['trace_sha256'] != rec_sha:
        x = dict(error='trace 원본 sha256 이 ledger 기록과 다름')
    return name, x


def _baseline(job):
    lab, root, name, rec_sha, ladder, tags = job
    rs = Rescan(Path(lab), Path(ladder), tags)
    x = extract(Path(root) / name, on_row=rs.row)
    out = rs.close()
    if 'error' not in x and rec_sha and x['trace_sha256'] != rec_sha:
        x = dict(error='trace 원본 sha256 이 ledger 기록과 다름')
    if 'error' in x:
        out['ok'] = False
    return name, x, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('result_dir', type=Path)
    ap.add_argument('--lab', type=Path)
    ap.add_argument('--jobs', type=int, default=1)
    ap.add_argument('--out-dir', type=Path, default=HERE, help='시험(합성 입력)용. 공식 분석은 기본값(이 폴더)')
    a = ap.parse_args()
    root = a.result_dir.resolve()
    lab = (a.lab or root.parents[3]).resolve()
    raw = LIST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LIST_SHA:
        print('[FAIL] 변종 목록 sha256 불일치 — 사전 등록 §8')
        return 2
    vlist = json.loads(raw)
    vmap = {v['id']: v for v in vlist['variants']}
    ledger = [json.loads(l) for l in (root / 'ledger.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    ltable = read_json(root / 'ladders' / 'ladders-sha256.json') or {}
    status_line = ((root / 'STATUS.txt').read_text(encoding='utf-8').splitlines() or [''])[0] if (root / 'STATUS.txt').is_file() else None
    fixed = [dict(file=p.name, mismatch=read_json(p)['mismatch']) for p in sorted(root.glob('fixed-inputs-*.json'))]
    res = dict(round=root.name, ledger_sha256=sha(root / 'ledger.jsonl'), variant_list_sha256=LIST_SHA,
               modules={m: sha(HERE / m) for m in MODULES}, bridge_run_py_sha256=sha(lab / 'bridge/run.py'),
               engine_mjs_sha256=sha(lab / 'bridge/engine.mjs'))
    header = read_json(root / 'run-header.json') or {}
    v = dict(status_line=status_line, fixed_input_checks=fixed, fixed_input_mismatch=any(f['mismatch'] for f in fixed),
             header={k: header.get(k) for k in ('runner_sha256', 'common_sha256', 'adapter_sha256', 'list_sha256', 'ladders_table_sha256')},
             ladders_table_sha_ok=bool(ltable) and sha(root / 'ladders' / 'ladders-sha256.json') == header.get('ladders_table_sha256'),
             ledger_rows=len(ledger), distinct_no=len({r['no'] for r in ledger}))
    checks, rec_sha = {}, {}
    for r in ledger:
        checks[r['no']], rec_sha[r['no']] = run_check(root, r, ltable)
    v['run_problems'] = {str(no): w for no, w in sorted(checks.items()) if w}
    counts = {}
    for cell in CELLS:
        vs = {r['variant_id'] for r in ledger if r['cell'] == cell and r['kind'] == 'variant'}
        counts[cell] = dict(variants=len(vs), variant_runs=sum(1 for r in ledger if r['cell'] == cell and r['kind'] == 'variant'),
                            baseline_runs=sum(1 for r in ledger if r['cell'] == cell and r['kind'] == 'baseline'),
                            expected=list(EXPECTED[cell]))
    v['counts'], v['counts_match_prereg'] = counts, all((c['variants'], c['variant_runs']) == tuple(c['expected']) and c['baseline_runs'] == 2 * len(SCEN_ORDER[k]) for k, c in counts.items())

    # 원본 기준: 반복 1·2 해시 일치 + 두 반복 모두 문제없음 → 그 (셀, 시나리오) 유효
    base = {(r['cell'], r['key'], r['rep']): r for r in ledger if r['kind'] == 'baseline'}
    valid, excluded = {c: [] for c in CELLS}, {}
    for cell in CELLS:
        for key in SCEN_ORDER[cell]:
            b1, b2 = base.get((cell, key, 1)), base.get((cell, key, 2))
            if not b1 or not b2:
                excluded[f'{cell}/{key}'] = '원본 기준 실행 기록 없음'
            elif checks[b1['no']] or checks[b2['no']]:
                excluded[f'{cell}/{key}'] = '원본 기준 실행 문제: ' + '; '.join(checks[b1['no']] + checks[b2['no']])
            elif b1['trace_hash'] != b2['trace_hash']:
                excluded[f'{cell}/{key}'] = '무효: 결정성 해시 불일치(반복 1·2)'
            else:
                valid[cell].append(key)
    v['valid_scenarios'], v['excluded_scenarios'] = valid, excluded

    sampled = [x for x in vlist['variants'] if x['sampled']]  # 기록이 없는 추출 변종도 넣는다(누락 = 보류로 드러나게)
    tags = {c: sorted({x['tag'] for x in sampled if x['cell'] == c}) for c in CELLS}
    bjobs = [(str(lab), str(root), base[(c, k, 1)]['name'], rec_sha[base[(c, k, 1)]['no']],
              str(lab / f'ladders/{c}/correct/program.ldprog.json'), tags[c]) for c in CELLS for k in valid[c] if tags[c]]
    vruns = [r for r in ledger if r['kind'] == 'variant' and r['key'] in valid[r['cell']] and not checks[r['no']]]
    rescans, bext, cmp = {}, {}, {}
    with ProcessPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        bout = {name: (x, rs) for name, x, rs in ex.map(_baseline, bjobs)}
        for c in CELLS:
            for k in valid[c]:
                if tags[c]:
                    bext[(c, k)], rescans[(c, k)] = bout[base[(c, k, 1)]['name']]
        # 변종 기록은 읽는 대로 원본과 비교하고 Q 목록은 버린다(메모리)
        by_name = {r['name']: r for r in vruns}
        for name, x in ex.map(_extract, [(str(root), r['name'], rec_sha[r['no']]) for r in vruns], chunksize=4):
            r = by_name[name]
            bx = bext.get((r['cell'], r['key'])) or dict(error='원본 재스캔 대상 아님')
            cmp[name] = ('기록 읽기 실패: ' + x['error'] if 'error' in x else '원본 기록 읽기 실패: ' + bx['error'] if 'error' in bx
                         else dict(no=r['no'], **compare(bx, x)))
    v['rescan'] = {f'{c}/{k}': dict(ok=rs['ok'], checks=rs['checks'], node_exit=rs['node_exit']) for (c, k), rs in sorted(rescans.items())}

    runs = {}  # runs[variant_id][key] = compare 결과 또는 누락 사유
    for r in ledger:
        if r['kind'] != 'variant':
            continue
        slot = runs.setdefault(r['variant_id'], {})
        if r['key'] not in valid[r['cell']]:
            slot[r['key']] = '시나리오 제외: ' + excluded.get(f"{r['cell']}/{r['key']}", '')
        elif checks[r['no']]:
            slot[r['key']] = '; '.join(checks[r['no']])
        else:
            slot[r['key']] = cmp[r['name']]
    per_set = {}
    for sname, keep in SETS.items():
        results = {}
        for x in sampled:
            rsc = {k: rescans.get((x['cell'], k)) for k in valid[x['cell']]}
            results[x['id']] = classify(x, valid[x['cell']], rsc, runs.get(x['id'], {}), keep)
        m1, m2, m3 = metrics(sampled, results, {c: vlist['cells'][c]['target_by_group'] for c in CELLS})
        per_set[sname] = dict(metric1=m1, metric2=m2, metric3=m3, predictions=predictions(sampled, results),
                              predictions_outcome_first=predictions(sampled, results, 'stage_outcome_first'),
                              representatives=representatives(sampled, results),
                              inactive_but_q_changed=sorted(i for i, r in results.items() if r['inactive_but_q_changed']),
                              stages={i: r['stage'] for i, r in sorted(results.items())})
        if sname == 'full':
            res['variants'] = {x['id']: dict(cell=x['cell'], group=x['group'], tag=x['tag'], mode=x['mode'], rung=x['rung'],
                                             cells=x['cells'], **results[x['id']]) for x in sampled}
    res['validity'], res['sets'] = v, per_set
    res['run_levels'] = {i: {k: (s if isinstance(s, str) else {kk: s[kk] for kk in sorted(s)}) for k, s in sorted(d.items())}
                         for i, d in sorted(runs.items())}
    res['baseline_outcome'] = {f'{c}/{k}': dict(status=x.get('status'), sub_status=x.get('sub_status'), events=x.get('events'),
                                                judgments=x.get('judgments'), ticks=x.get('ticks'), error=x.get('error'))
                               for (c, k), x in sorted(bext.items())}
    (a.out_dir / f'TR-03_결과_{root.name}.json').write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    (a.out_dir / f'TR-03_결과_{root.name}.md').write_text(render(res), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
