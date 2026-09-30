#!/usr/bin/env python3
"""TR-2026-02 결과 분석 — 사전 등록 v0.3 §5 지표 1~5 와 §3-2 예측 P1~P4 를 정의 그대로 집계한다.

입력(읽기만): plc-twin-lab experiments/S2/runs/<회차>/ 의 ledger.jsonl · 번호별 trace.jsonl · summary.json · tr02-adapter.json
출력: 이 폴더의 TR-02_결과_<회차>.json · TR-02_결과_<회차>.md — 시각·실행 환경 값을 넣지 않아 두 번 돌리면 바이트가 같다.
지표 2 의 스캔 입력은 고정 어댑터의 make_reconstruct 로 다시 만든다(어댑터는 import 만, 고치지 않는다).
사용: python3 TR-02_분석.py [--round tr02-official-1]
"""
import argparse, hashlib, importlib.util, json, sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True  # 고정입력·레포에 __pycache__ 를 만들지 않는다
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from TR02_분석_표 import render  # noqa: E402
ADAPTER = HERE.parent / '고정입력' / 'TR-02_연결조건_어댑터.py'
ADAPTER_SHA = 'f5241b5f5d5286ff6366bdff33da8ec599e343d67ba6fd1ebaf129f1a7d10c40'
RUNS = Path('<repos>/plc-twin-lab/experiments/S2/runs')
LADDERS = ['correct', 'late-reverse', 'swapped-sensors']
TAGS_UNFILTERED, TAGS_FILTERED = ['A.PB.stop_nc', 'A.PB.estop_nc'], ['A.Sen.left', 'A.Sen.right']
WIDTHS, PHASES = [5, 15, 25, 35, 45], list(range(0, 50, 5))
P3_PRED = {'boundary': dict(zip(WIDTHS, [1, 3, 5, 7, 9])), 'history': dict(zip(WIDTHS, [5, 10, 10, 10, 10]))}
WINDOW = range(100, 141)  # 지표 5: 주입 틱 100~140(0 부터 센다) = trace 행 tick 101~141


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_adapter():
    spec = importlib.util.spec_from_file_location('tr02_adapter', ADAPTER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rows(folder):
    out = [json.loads(l) for l in (folder / 'trace.jsonl').read_text().splitlines() if l.strip()]
    return [r for r in out if r.get('type') == 'tick']


def q_changes(ticks):
    """적용 Q 변화 목록 (틱(0 부터), 태그, 값). 첫 틱 Q 가 기준."""
    out, prev = [], ticks[0]['Q']
    for r in ticks[1:]:
        for tag in sorted(r['Q']):
            if r['Q'][tag] != prev[tag]:
                out.append((r['tick'] - 1, tag, r['Q'][tag]))
        prev = r['Q']
    return out


def missed_edges(adapter, mode, ticks):
    """지표 2. 어댑터 복원으로 스캔 입력을 만들고, 스캔 표본 사이에서 사라진 공장 에지를 센다."""
    rec = adapter.make_reconstruct(mode, None)
    prev, audit_fail, chain_fail, value_fail = ticks[0]['I_start'], 0, 0, 0
    samples = [(0, dict(prev))]  # (표본 시각 ms, 스캔 입력). 0 ms = 적재 시 입력(두 조건 공통 기준점)
    factory = {t: [] for t in prev}  # 태그별 공장 에지 절대 시각 ms
    for r in ticks:
        if r['I_start'] != prev:
            chain_fail += 1
        start = (r['tick'] - 1) * 50
        resp = dict(dt_s=r['dt_s'], time_s=r['tick'] * 0.05, edges=r['edges'], I=r['I'])
        try:
            images = rec(prev, resp)
        except Exception:
            audit_fail += 1
            images = None
        for e in r['edges']:
            factory[e['tag']].append(start + round(e['t_s'] * 1000))
        if images is not None:
            times = [start] * 5 if mode == 'boundary' else [start + b for b in range(10, 51, 10)]
            samples.extend(zip(times, images))
        prev = r['I']
    init = ticks[0]['I_start']
    per_tag = {}
    for tag, edges in factory.items():
        def value_at(t):
            return init[tag] ^ (sum(1 for a in edges if a <= t) % 2 == 1)
        value_fail += sum(1 for t, img in samples if img[tag] != value_at(t))
        seq = [img[tag] for _, img in samples]
        plc = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
        last = samples[-1][0]
        trailing = sum(1 for a in edges if a > last)
        lost = 0
        for (t0, _), (t1, _) in zip(samples, samples[1:]):
            c = sum(1 for a in edges if t0 < a <= t1)
            lost += c - c % 2
        per_tag[tag] = dict(factory_edges=len(edges), plc_transitions=plc, missed_pairs=lost // 2,
                            trailing_unsampled=trailing,
                            identity_ok=len(edges) - trailing - lost == plc)
    return dict(per_tag=per_tag, reconstruct_exceptions=audit_fail, I_start_chain_breaks=chain_fail,
                reconstructed_value_mismatches=value_fail)


def phase_hist(ticks):
    h = {}
    for r in ticks:
        for e in r['edges']:
            h.setdefault(e['tag'], Counter())[round(e['t_s'] * 1000)] += 1
    return {t: {str(k): v for k, v in sorted(c.items())} for t, c in sorted(h.items())}


def first_ticks(events):
    out = {}
    for e in events:
        out[e['name']] = min(out.get(e['name'], e['tick']), e['tick'])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--round', default='tr02-official-1')
    a = ap.parse_args()
    root = RUNS / a.round
    ledger = [json.loads(l) for l in (root / 'ledger.jsonl').read_text().splitlines() if l.strip()]
    by_no = {r['no']: r for r in ledger}
    res = dict(round=a.round, ledger_sha256=sha(root / 'ledger.jsonl'), adapter_sha256=sha(ADAPTER),
               analysis_sha256=sha(__file__), render_sha256=sha(HERE / 'TR02_분석_표.py'))

    # 무효 기준 재확인(§6)
    v = dict(ledger_rows=len(ledger), distinct_no=len(by_no), rc_nonzero=[], processes_not_pass=[],
             adapter_sha_mismatch=[], summary_hash_mismatch=[], rep_hash_mismatch=[])
    summaries = {}
    for r in ledger:
        d = root / r['name']
        s = json.loads((d / 'summary.json').read_text())
        side = json.loads((d / 'tr02-adapter.json').read_text())
        summaries[r['no']] = s
        if r['rc'] != 0: v['rc_nonzero'].append(r['no'])
        if r['processes'] != '[PASS]': v['processes_not_pass'].append(r['no'])
        if side['adapter_sha256'] != ADAPTER_SHA: v['adapter_sha_mismatch'].append(r['no'])
        if not (s['trace_hash'] == side['trace_hash'] == r['trace_hash'] and s['status'] == r['status']):
            v['summary_hash_mismatch'].append(r['no'])
    key = lambda r: (r['kind'], r['variant'], r['mode'], r['ticks'], r['pulse'])
    groups = {}
    for r in ledger:
        groups.setdefault(key(r), {})[r['rep']] = r
    for g in groups.values():
        if g[1]['trace_hash'] != g[2]['trace_hash']:
            v['rep_hash_mismatch'].append([g[1]['no'], g[2]['no']])
    v['combos'] = len(groups)
    v['adapter_file_sha_ok'] = res['adapter_sha256'] == ADAPTER_SHA
    v['invalid_combos'] = len(v['rep_hash_mismatch'])
    res['validity'] = v

    adapter = load_adapter()
    plant = {(r['variant'], r['mode'], r['rep']): r for r in ledger if r['kind'] == 'plant'}
    base = {(r['mode'], r['rep']): r for r in ledger if r['kind'] == 'baseline'}
    tr = {k: rows(root / r['name']) for k, r in plant.items()}

    # 지표 1 · 3 · 4 (반복 1 기준 — 반복 1·2 해시 동일 확인은 위)
    m1 = dict(false_alarm=[0, 0], missed_negative=[0, 0], detail={})
    m3, m4 = {}, {}
    for lad in LADDERS:
        h, b = plant[(lad, 'history', 1)], plant[(lad, 'boundary', 1)]
        sh, sb = summaries[h['no']], summaries[b['no']]
        m1['detail'][lad] = dict(history=[h['no'], sh['status']], boundary=[b['no'], sb['status']])
        if lad == 'correct':
            m1['false_alarm'][1] += 1
            m1['false_alarm'][0] += sh['status'] == '[PASS]' and sb['status'] == '[FAIL]'
        else:
            m1['missed_negative'][1] += 1
            m1['missed_negative'][0] += sh['status'] == '[FAIL]' and sb['status'] == '[PASS]'
        ch, cb = Counter(e['name'] for e in sh['events']), Counter(e['name'] for e in sb['events'])
        fh, fb = first_ticks(sh['events']), first_ticks(sb['events'])
        names = sorted(set(ch) | set(cb))
        m3[lad] = {n: dict(count_history=ch[n], count_boundary=cb[n], count_diff=cb[n] - ch[n],
                           first_tick_history=fh.get(n), first_tick_boundary=fb.get(n),
                           first_tick_diff=(fb[n] - fh[n]) if n in fh and n in fb else None) for n in names}
        qh, qb = q_changes(tr[(lad, 'history', 1)]), q_changes(tr[(lad, 'boundary', 1)])
        diffs = [y[0] - x[0] for x, y in zip(qh, qb)]
        first_bad = next((i for i, (x, y) in enumerate(zip(qh, qb)) if (x[1], x[2]) != (y[1], y[2]) or y[0] - x[0] != 1), None)
        m4[lad] = dict(runs=[h['no'], b['no']], changes_history=len(qh), changes_boundary=len(qb),
                       same_tag_value_order=[(x[1], x[2]) for x in qh] == [(y[1], y[2]) for y in qb],
                       tick_diff_hist={str(k): c for k, c in sorted(Counter(diffs).items())},
                       first_mismatch_index=first_bad,
                       first_mismatch=None if first_bad is None else dict(history=list(qh[first_bad]), boundary=list(qb[first_bad])),
                       history_changes=[list(x) for x in qh], boundary_changes=[list(x) for x in qb])
    res['metric1'], res['metric3'], res['metric4'] = m1, m3, m4

    # 지표 2 + 에지 위상 분포(§4)
    m2, ph = {}, {}
    for (lad, mode, rep), t in sorted(tr.items()):
        if rep == 1:
            m2[f'{lad}/{mode}'] = dict(run=plant[(lad, mode, rep)]['no'], **missed_edges(adapter, mode, t))
            ph[f'{lad}/{mode}'] = phase_hist(t)
    for (mode, rep), r in sorted(base.items()):
        if rep == 1:
            m2[f'baseline/{mode}'] = dict(run=r['no'], **missed_edges(adapter, mode, rows(root / r['name'])))
    res['metric2'], res['edge_phase_ms'] = m2, ph

    # 지표 5
    def window_q(r):
        return [x['Q'] for x in rows(root / r['name']) if x['tick'] - 1 in WINDOW]
    bq = {k: window_q(r) for k, r in base.items()}
    m5 = {}
    for r in ledger:
        if r['kind'] != 'pulse':
            continue
        tag, _, phase, width = r['pulse'].split(':')
        cell = m5.setdefault(f"{tag}|{width}|{r['mode']}", dict(tag=tag, width=int(width), mode=r['mode'],
                                                                detected={'1': [], '2': []}, runs=[]))
        cell['runs'].append(r['no'])
        if window_q(r) != bq[(r['mode'], r['rep'])]:
            cell['detected'][str(r['rep'])].append(int(phase))
    for c in m5.values():
        c['runs'].sort()
        c['count'] = {k: len(x) for k, x in c['detected'].items()}
    res['metric5'] = dict(sorted(m5.items()))
    res['baseline_reps_equal'] = {m: bq[(m, 1)] == bq[(m, 2)] for m in ('history', 'boundary')}
    res['other_status_tally'] = dict(sorted(Counter(f"{r['kind']}/{r['mode']}/{r['status']}" for r in ledger if r['kind'] != 'plant').items()))

    # 예측 판정(§3-2)
    p = {}
    bad1 = [lad for lad in LADDERS if any(x['count_diff'] for x in m3[lad].values())
            or m1['detail'][lad]['history'][1] != m1['detail'][lad]['boundary'][1]]
    p['P1'] = dict(verdict='[틀림]' if bad1 else '[맞음]', failing=bad1)
    bad2 = []
    for lad in LADDERS:
        q = m4[lad]
        ev = [n for n, x in m3[lad].items() if x['first_tick_diff'] != 1]
        if not (q['changes_history'] == q['changes_boundary'] and q['same_tag_value_order']
                and set(q['tick_diff_hist']) <= {'1'}) or ev:
            bad2.append(dict(ladder=lad, runs=q['runs'], events_not_plus1=ev))
    p['P2'] = dict(verdict='[틀림]' if bad2 else '[맞음]', failing=bad2)
    for name, tags, pred in (('P3', TAGS_UNFILTERED, P3_PRED), ('P4', TAGS_FILTERED, None)):
        bad = []
        for c in res['metric5'].values():
            if c['tag'] in tags:
                want = pred[c['mode']][c['width']] if pred else 0
                if any(n != want for n in c['count'].values()):
                    bad.append(dict(tag=c['tag'], width=c['width'], mode=c['mode'], predicted=want,
                                    observed=c['count'], detected_phases=c['detected']['1'], first_run=c['runs'][0]))
        bad.sort(key=lambda x: x['first_run'])
        p[name] = dict(verdict='[틀림]' if bad else '[맞음]', failing=bad)
    res['predictions'] = p

    out_json = HERE / f'TR-02_결과_{a.round}.json'
    out_json.write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    (HERE / f'TR-02_결과_{a.round}.md').write_text(render(res))
    return 0


if __name__ == '__main__':
    sys.exit(main())
