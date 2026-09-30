"""TR-2026-03 공식 실행 공통 부품 — 고정 입력 확인 · 조합 순서 · 변종 래더 준비 · 기록 압축.

판정·집계는 하지 않는다. 사전 등록 v0.3 §3(변종) · §4(시나리오) · §7(실행 규칙) · §8(고정 입력)만 따른다.
TR-03_공식실행.py 가 이 파일의 sha256 을 확인한 뒤 불러온다.
"""
import gzip, hashlib, json, os, shutil, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXED = HERE.parent / '고정입력'
GH = Path('<repos>')
LAB = GH / 'plc-twin-lab'
RUNS_REL = Path('experiments/S2/runs')

# 사전 등록 §8 고정 입력
LIST = FIXED / 'TR-03_변종목록_v1.json'
LIST_SHA = 'bc61eab488b39600724eda60071b1d86da05af33b56965582464ebcb62ef1f67'
GEN = FIXED / 'TR-03_변종목록_생성.py'
GEN_SHA = '06e4c11258f2486598c1e73019cfaa2d74cc109bde3a9b3ce61d071327c9387c'
MJS = FIXED / 'TR-03_변종적용_컴파일검사.mjs'
MJS_SHA = '0268f45bc684e7ad9200c64ee46e6e9f08e075c8ae06a9b05bcd473bbbf63fbf'
MANIFEST = FIXED / '고정입력_매니페스트_2026-09-30.json'
MANIFEST_SHA = '5630e09569d9eadeed58a2d2dd507919a022fe22bf492c05b221d91d8993eb8d'
REPO_ROOTS = {'plc-twin-lab': LAB, 'vexplor-vision-2-extctl': GH / 'vexplor-vision-2-extctl',
              'plc-devices': GH / 'plc-devices', 'plc-simulator': LAB / 'vendor/plc-simulator'}

CELLS = ['cell-a', 'cell-b', 'cell-b-pack']          # 짧은 셀 먼저
# §4 시나리오 표 순서: (키, run() 시나리오, 시드, 유량, 틱)
SCENARIOS = {
    'cell-a': [('normal', 'normal', 1, None, 1000), ('cycle-stop', 'cycle-stop', 1, None, 1200)],
    'cell-b': [('normal-s1', 'normal', 1, None, 5000), ('normal-s2', 'normal', 2, None, 5000),
               ('normal-s3', 'normal', 3, None, 5000), ('cycle-stop', 'cycle-stop', 1, None, 1200),
               ('curtain', 'curtain', 1, None, 1000), ('recovery', 'recovery', 1, None, 3420),
               ('recovery-retract', 'recovery-retract', 1, None, 3420), ('batch', 'batch', 1, None, 2600),
               ('stroke75', 'stroke75', 1, None, 2600), ('flow060', 'flow-sweep', 1, 0.60, 1000),
               ('flow045', 'flow-sweep', 1, 0.45, 1000)],
    'cell-b-pack': [('normal-s1', 'normal', 1, None, 10000), ('normal-s2', 'normal', 2, None, 10000),
                    ('normal-s3', 'normal', 3, None, 10000), ('cycle-stop', 'cycle-stop', 1, None, 1200),
                    ('curtain', 'curtain', 1, None, 1000), ('packfault', 'packfault', 1, None, 6000)],
}
# §3-2 표의 값. 조합을 만든 뒤 이 값과 다르면 실행하지 않는다.
EXPECTED = {'cell-a': dict(variants=25, runs=50), 'cell-b': dict(variants=156, runs=1716),
            'cell-b-pack': dict(variants=319, runs=1914), 'baseline_runs': 38, 'variants': 500, 'variant_runs': 3680}
# 소요 추정용(실행하지 않고 틱 수로만): 틱/초, 실행 1 건당 시동·압축 여유 초
SPEED = {'cell-a': 1250, 'cell-b': 1000, 'cell-b-pack': 190}
OVERHEAD_S = 1.5


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha(p):
    return sha_bytes(Path(p).read_bytes())


def load_list():
    """변종 목록을 읽기 전에 sha256 을 확인한다. 다르면 None."""
    raw = LIST.read_bytes()
    return json.loads(raw) if sha_bytes(raw) == LIST_SHA else None


def fixed_input_check():
    """고정 입력(§8) 전부를 작업 트리에서 다시 잰다. 반환: 어긋난 항목 목록(빈 목록 = 일치)."""
    bad = [str(p) for p, h in ((LIST, LIST_SHA), (GEN, GEN_SHA), (MJS, MJS_SHA), (MANIFEST, MANIFEST_SHA)) if sha(p) != h]
    if str(MANIFEST) in bad:
        return bad
    for item in json.loads(MANIFEST.read_text(encoding='utf-8'))['items']:
        root = REPO_ROOTS[item['repo']]
        if item['path'].endswith('/**'):                 # 빌드 산출물 묶음(매니페스트 계산식 그대로)
            base = root / item['path'][:-3]
            files = sorted(p for p in base.rglob('*') if p.is_file())
            lines = ''.join(f'{sha(p)}  {p.relative_to(root)}\n' for p in files)
            ok = sha_bytes(lines.encode()) == item['sha256']
        else:
            p = root / item['path']
            ok = p.is_file() and sha(p) == item['sha256']
        if not ok:
            bad.append(f"{item['repo']}:{item['path']}")
    return bad


def combos(data):
    """고정 순서: 셀마다 원본 기준 실행(시나리오 × 2 회) → 추출 변종 × 시나리오. 번호는 1 부터."""
    out = []
    for cell in CELLS:
        for key, scen, seed, flow, ticks in SCENARIOS[cell]:
            for rep in (1, 2):
                out.append(dict(kind='baseline', cell=cell, variant_id=None, group=None, key=key, scenario=scen,
                                seed=seed, flow=flow, ticks=ticks, rep=rep))
        for v in (x for x in data['variants'] if x['cell'] == cell and x['sampled']):
            for key, scen, seed, flow, ticks in SCENARIOS[cell]:
                out.append(dict(kind='variant', cell=cell, variant_id=v['id'], group=v['group'], key=key, scenario=scen,
                                seed=seed, flow=flow, ticks=ticks, rep=1))
    for i, c in enumerate(out, 1):
        c['no'] = i
        c['name'] = (f"{i:04d}-base-{c['cell']}-{c['key']}-r{c['rep']}" if c['kind'] == 'baseline'
                     else f"{i:04d}-{c['variant_id']}-{c['key']}")
    return out


def count_check(data, cs):
    """조합 수를 사전 등록 §3-2 · 변종 목록 cells 값과 대조. 반환: (셀별 표, 어긋남 목록)."""
    table, bad = {}, []
    for cell in CELLS:
        base = sum(1 for c in cs if c['cell'] == cell and c['kind'] == 'baseline')
        runs = sum(1 for c in cs if c['cell'] == cell and c['kind'] == 'variant')
        nvar = len({c['variant_id'] for c in cs if c['cell'] == cell and c['kind'] == 'variant'})
        est = sum(c['ticks'] / SPEED[cell] + OVERHEAD_S for c in cs if c['cell'] == cell)
        table[cell] = dict(baseline_runs=base, variants=nvar, variant_runs=runs, est_hours=round(est / 3600, 2))
        info = data['cells'][cell]
        if (nvar, runs) != (EXPECTED[cell]['variants'], EXPECTED[cell]['runs']) or (nvar, runs) != (info['sampled'], info['runs_sampled']):
            bad.append(f'{cell}: 변종 {nvar} · 실행 {runs} (사전 등록 {EXPECTED[cell]} · 목록 {info["sampled"]}/{info["runs_sampled"]})')
        if info['scenarios'] != len(SCENARIOS[cell]):
            bad.append(f'{cell}: 시나리오 수 {len(SCENARIOS[cell])} ≠ 목록 {info["scenarios"]}')
    tot = {k: sum(t[k] for t in table.values()) for k in ('baseline_runs', 'variants', 'variant_runs')}
    if (tot['baseline_runs'], tot['variants'], tot['variant_runs']) != (EXPECTED['baseline_runs'], EXPECTED['variants'], EXPECTED['variant_runs']):
        bad.append(f'합계 {tot}')
    return table, bad


def _variant_diff_ok(original_raw, variant_raw, v):
    """변종 = 원본에서 목록의 칸만 {"k":"hwire"} 로 바꾼 것인지(값 기준) 확인."""
    orig, var = json.loads(original_raw), json.loads(variant_raw)
    grid = orig['rungs'][v['rung']]['grid']
    for r, c in v['cells']:
        cell = grid[r][c]
        if cell.get('k') != 'contact' or cell.get('tag') != v['tag'] or cell.get('mode') != v['mode']:
            return False
        grid[r][c] = {'k': 'hwire'}
    return orig == var


def prepare_ladders(dst, data):
    """고정 생성기(.mjs)로 추출 변종 500 개를 만들고, 엔진이 읽는 배치(<id>/program.ldprog.json + monitor-map.json)로 둔다.
    생성기 출력(_gen/)은 그대로 남긴다. 반환: (래더 sha 표, 표 파일 sha, 오류 목록)."""
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=False)
    gen = dst / '_gen'
    p = subprocess.run(['node', str(MJS), str(LIST), str(gen)], capture_output=True, text=True)
    errors = []
    try:
        res = json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return None, None, [f'생성기 출력 해석 실패 rc={p.returncode} {p.stderr[-400:]}']
    if p.returncode != 0 or res.get('all') != EXPECTED['variants'] or res.get('pass') != EXPECTED['variants'] or res.get('fail'):
        errors.append(f'생성기 컴파일 검사 {res}')
    originals = {c: (LAB / f'ladders/{c}/correct/program.ldprog.json').read_bytes() for c in CELLS}
    table = {}
    for v in (x for x in data['variants'] if x['sampled']):
        raw = (gen / f"{v['id']}.ldprog.json").read_bytes()
        if not _variant_diff_ok(originals[v['cell']], raw, v):
            errors.append(f"{v['id']}: 목록의 칸 외 차이")
        d = dst / v['id']
        d.mkdir()
        (d / 'program.ldprog.json').write_bytes(raw)
        shutil.copyfile(LAB / f"ladders/{v['cell']}/correct/monitor-map.json", d / 'monitor-map.json')
        table[v['id']] = dict(program=sha_bytes(raw), monitor_map=sha(d / 'monitor-map.json'))
    text = json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + '\n'
    (dst / 'ladders-sha256.json').write_text(text, encoding='utf-8')
    (dst / 'generator-result.json').write_text(json.dumps(res, ensure_ascii=False) + '\n', encoding='utf-8')
    return table, sha_bytes(text.encode()), errors


def verify_ladders(dst):
    """이어서 실행할 때: 둔 변종 래더가 처음 만든 표와 같은지. 반환: (표, 어긋난 id 목록)."""
    dst = Path(dst)
    table = json.loads((dst / 'ladders-sha256.json').read_text(encoding='utf-8'))
    bad = [i for i, h in table.items()
           if sha(dst / i / 'program.ldprog.json') != h['program'] or sha(dst / i / 'monitor-map.json') != h['monitor_map']]
    return table, bad


def gzip_replace(path):
    """큰 기록 파일을 gzip(결정적: mtime 0 · 파일명 없음 · 수준 1)으로 바꾼다. 풀어서 원본 sha 와 같을 때만 원본을 지운다.
    포장 셀 10,000 틱 기록이 약 0.5 GB 라 원본 그대로면 디스크를 넘는다(§ 실행기 머리말)."""
    path = Path(path)
    if not path.exists():
        return None
    h, gz = hashlib.sha256(), path.with_name(path.name + '.gz')
    part = gz.with_name(gz.name + '.part')
    with path.open('rb') as f, part.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=1, mtime=0) as g:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
            g.write(chunk)
    back = hashlib.sha256()
    with gzip.open(part, 'rb') as g:
        for chunk in iter(lambda: g.read(1 << 20), b''):
            back.update(chunk)
    if back.hexdigest() != h.hexdigest():
        return dict(file=path.name, sha256=h.hexdigest(), gzip='[FAIL] 되풀기 불일치 — 원본 유지')
    size = path.stat().st_size
    os.replace(part, gz)
    path.unlink()
    return dict(file=path.name, sha256=h.hexdigest(), bytes=size, gz_sha256=sha(gz))
