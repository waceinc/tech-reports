"""TR-03 분석 스크립트 시험용 합성 결과 폴더 생성기(스크래치 전용). 공식 실행 결과를 읽지 않는다.
원본 기준 trace 는 실제 엔진(브리지 engine.mjs)을 합성 입력으로 스캔해 만들고(digest·Q 가 진짜), 변종 trace 는 그 사본에 의도한 차이를 넣는다.
사용: python3 make_synth.py <출력 회차 폴더> [--corrupt-digest]
"""
import gzip, hashlib, json, subprocess, sys
from pathlib import Path

LAB = Path('<repos>/plc-twin-lab')
WORK = Path('<work>/06_제품개발/2026H2_PLC트윈실험환경/TR공개')
HELPER = WORK / '실행/TR03_분석_재스캔.mjs'
sys.path.insert(0, str(LAB / 'bridge'))
sys.dont_write_bytecode = True
from run import reconstruct  # noqa

def canon(v): return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
def sha(b): return hashlib.sha256(b).hexdigest()
ADAPTER_SHA = '0caed4f0d7fe72c62e9eb76048413778afc0c3b5610679463a959454fc84b2a7'
BASE_SHA = {'cell-a': '5058bd0b97644e66c0310a540a0403931bf6bd8195445576430d6dd1cabf8ef1',
            'cell-b': '05999e23b90b265f9907e0cd05f5469eccec6195e43326310bb9b491bd4ed0b1'}


def baseline_rows(cell, ticks, stim):
    """stim(tick, I) -> edges 목록[(t_ms, tag, value)]. 실제 엔진으로 스캔해 틱 행을 만든다."""
    tm = json.loads((LAB / f'cells/{cell}.tagmap.json').read_text())
    ins = {b['tag']: (False if b.get('type', 'BOOL') == 'BOOL' else 0) for b in tm['bindings'] if b['direction'] == 'in'}
    for k in ins:
        if k.endswith('_nc') or k in ('B.Air.pressureOk',):
            ins[k] = True
    outs = {b['tag']: (False if b.get('type', 'BOOL') == 'BOOL' else 0) for b in tm['bindings'] if b['direction'] == 'out'}
    p = subprocess.Popen(['node', str(HELPER), str(LAB / 'bridge/engine.mjs'), str(LAB / f'ladders/{cell}/correct/program.ldprog.json'), '[]'],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert json.loads(p.stdout.readline())['ok']
    dt = .05 if cell == 'cell-a' else .01
    rows, cur, q = [], dict(ins), dict(outs)
    for tick in range(ticks):
        edges, nxt = [], dict(cur)
        for ms, tag, val in stim(tick):
            if nxt[tag] != val:
                edges.append(dict(t_s=ms / 1000, tag=tag, value=val)); nxt[tag] = val
        resp = dict(dt_s=dt, edges=edges, I=nxt)
        images = reconstruct(cur, resp)
        p.stdin.write(json.dumps(dict(inputs=images)) + '\n'); p.stdin.flush()
        scans = [dict(Q=s['Q'], digest=s['digest'], probes={}, scan=s['scan']) for s in json.loads(p.stdout.readline())['scans']]
        qn = scans[-1]['Q']
        rows.append(dict(type='tick', tick=tick + 1, dt_s=dt, I_start=cur, I=nxt, Q=q, Q_next=qn, stimuli={}, edges=edges, events=[],
                         judgments=[], state=dict(parts=[dict(id='part1', **{'class': 0}, route=0, x=tick * 0.01)]), state_hash=sha(canon(tick)), scans=scans))
        cur, q = nxt, qn
    p.stdin.write('{"cmd":"quit"}\n'); p.stdin.close(); p.wait()
    return rows


def write_run(root, name, rec, rows, status='[PASS]', rc=0, processes='[PASS]', failure=None, variant_sha=None):
    d = root / name; d.mkdir(parents=True)
    if rc != 0:
        (d / 'failure.json').write_text(json.dumps(dict(status='[FAIL]', error=failure, completed_ticks=0)))
        rec.update(rc=rc, trace_hash=None, status=None, processes=processes, failure=failure, files=[])
        return rec
    th = sha(canon([sha(canon(r)) for r in rows]))
    summ = dict(type='summary', status=status, completed=True, trace_hash=th, events=[], judgments=[])
    raw = b''.join(canon(x) + b'\n' for x in [dict(type='metadata', scenario=rec['scenario'])] + rows + [summ])
    with open(d / 'trace.jsonl.gz', 'wb') as f, gzip.GzipFile(filename='', mode='wb', fileobj=f, mtime=0) as g:
        g.write(raw)
    (d / 'summary.json').write_text(json.dumps(summ))
    lsha = variant_sha or BASE_SHA[rec['cell']]
    (d / 'tr03-adapter.json').write_text(json.dumps(dict(adapter_sha256=ADAPTER_SHA, trace_hash=th, status=status, ladder_sha256=lsha)))
    rec.update(rc=0, trace_hash=th, status=status, processes=processes, failure=None, ladder_sha256=lsha,
               files=[dict(file='trace.jsonl', sha256=sha(raw), bytes=len(raw))])
    return rec


def main():
    root = Path(sys.argv[1]); corrupt = '--corrupt-digest' in sys.argv
    root.mkdir(parents=True)
    vl = json.loads((WORK / '고정입력/TR-03_변종목록_v1.json').read_text())
    stim_a = lambda t: [(10, 'A.PB.start', True)] if t == 6 else [(10, 'A.PB.start', False)] if t == 7 else \
        [(20, 'A.Sen.right', True)] if t == 20 else [(30, 'A.Sen.right', False)] if t == 25 else []
    stim_b = lambda t: [(10, 'B.PB.start', True)] if t == 5 else [(10, 'B.PB.start', False)] if t == 7 else []
    base = {'cell-a': baseline_rows('cell-a', 60, stim_a), 'cell-b': baseline_rows('cell-b', 30, stim_b)}
    ledger, ltable, no = [], {}, 0
    def rec(kind, cell, key, scen, vid=None, group=None, rep=1):
        nonlocal no; no += 1
        name = f'{no:04d}-base-{cell}-{key}-r{rep}' if kind == 'baseline' else f'{no:04d}-{vid}-{key}'
        return dict(no=no, name=name, kind=kind, cell=cell, variant_id=vid, group=group, key=key, scenario=scen, seed=1, flow=None, ticks=0, rep=rep)
    # 셀 A: normal 원본 2 회(같은 해시) · cycle-stop 원본 2 회 오류 → 변종 cycle-stop 은 건너뜀(§4)
    for rep in (1, 2):
        rows = json.loads(json.dumps(base['cell-a']))
        if corrupt and rep == 1:
            rows[30]['scans'][2]['digest'] = 'sha256:' + '0' * 64
        r = rec('baseline', 'cell-a', 'normal', 'normal', rep=rep)
        ledger.append(write_run(root, r['name'], r, rows if not corrupt else rows))
    if corrupt:  # 반복 2 해시를 반복 1 과 맞춘다(결정성 무효가 아니라 재스캔 불일치만 시험)
        ledger[1]['trace_hash'] = ledger[0]['trace_hash']
        s = root / ledger[1]['name']
        for f in ('summary.json', 'tr03-adapter.json'):
            x = json.loads((s / f).read_text()); x['trace_hash'] = ledger[0]['trace_hash']; (s / f).write_text(json.dumps(x))
    for rep in (1, 2):
        r = rec('baseline', 'cell-a', 'cycle-stop', 'cycle-stop', rep=rep)
        ledger.append(write_run(root, r['name'], r, None, rc=1, failure='합성: 원본 cycle-stop 오류'))
    plan = {'cell-a-0006': 'q', 'cell-a-0007': 'event', 'cell-a-0008': 'judg', 'cell-a-0010': 'error', 'cell-a-0011': 'procfail', 'cell-a-0019': 'q'}
    def variant_rows(cell, how):
        rows = json.loads(json.dumps(base[cell]))
        if how == 'q': rows[40]['Q'] = {k: (not v if isinstance(v, bool) else v) for k, v in rows[40]['Q'].items()}
        if how == 'event': rows[45]['events'] = [dict(name='JAM', tick=46)]
        if how == 'judg': rows[20]['judgments'] = [dict(name='PLC_CURTAIN_IGNORED', tick=21)]
        return rows
    for v in (x for x in vl['variants'] if x['cell'] == 'cell-a' and x['sampled']):
        vsha = sha(v['id'].encode()); ltable[v['id']] = dict(program=vsha, monitor_map='x')
        how = plan.get(v['id'], 'same')
        r = rec('variant', 'cell-a', 'normal', 'normal', v['id'], v['group'])
        if how == 'error':
            ledger.append(write_run(root, r['name'], r, None, rc=1, failure='합성: 변종 실행 오류')); ledger[-1]['ladder_sha256'] = vsha
        else:
            ledger.append(write_run(root, r['name'], r, variant_rows('cell-a', how), processes='[FAIL]' if how == 'procfail' else '[PASS]', variant_sha=vsha))
        r = rec('variant', 'cell-a', 'cycle-stop', 'cycle-stop', v['id'], v['group'])
        r.update(rc=None, skipped='원본 기준 실행 오류 — §4 에 따라 이 셀에서 무효', ladder_sha256=vsha); ledger.append(r)
    # 셀 B: normal-s1 원본만. 안전 2 개 = 4a, 복귀 2 개 = 원본과 같음
    for rep in (1, 2):
        r = rec('baseline', 'cell-b', 'normal-s1', 'normal', rep=rep)
        ledger.append(write_run(root, r['name'], r, json.loads(json.dumps(base['cell-b']))))
    pick = [x for x in vl['variants'] if x['cell'] == 'cell-b' and x['sampled'] and x['group'] == '안전'][:2] + \
           [x for x in vl['variants'] if x['cell'] == 'cell-b' and x['sampled'] and x['group'] == '복귀'][:2]
    for i, v in enumerate(pick):
        vsha = sha(v['id'].encode()); ltable[v['id']] = dict(program=vsha, monitor_map='x')
        rows = json.loads(json.dumps(base['cell-b']))
        if i < 2: rows[20]['events'] = [dict(name='PART_FELL', tick=21)]
        r = rec('variant', 'cell-b', 'normal-s1', 'normal', v['id'], v['group'])
        ledger.append(write_run(root, r['name'], r, rows, variant_sha=vsha))
    (root / 'ladders').mkdir()
    text = json.dumps(ltable, ensure_ascii=False, indent=1, sort_keys=True) + '\n'
    (root / 'ladders/ladders-sha256.json').write_text(text)
    (root / 'run-header.json').write_text(json.dumps(dict(ladders_table_sha256=sha(text.encode()))))
    (root / 'STATUS.txt').write_text('상태: 완료\n합성\n')
    (root / 'fixed-inputs-20260930-000000.json').write_text(json.dumps(dict(when='합성', mismatch=[])))
    (root / 'ledger.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in ledger))
    print(json.dumps(dict(runs=len(ledger), cellb_pick=[(v['id'], v['group'], v['tag'], v['mode']) for v in pick]), ensure_ascii=False))


main()
