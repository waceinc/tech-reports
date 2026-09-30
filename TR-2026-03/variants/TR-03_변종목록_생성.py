"""TR-2026-03 변종 목록 생성기 (사전 등록 v0.3 고정 입력).

정답 래더 3개(plc-twin-lab 커밋 af9cc40)를 git 객체에서 읽어, 세는 규칙(TR-2026-03 v0.3 §3)대로
대상 직렬 인터록 조건을 세고, 셀별 실행 수가 상한을 넘으면 기능 묶음별 층화 무작위 추출로 줄인다.
결과를 보기 전 단계다 — 래더를 실행하지 않는다. 실행: python3 TR-03_변종목록_생성.py <출력.json>

전력 흐름 해석은 공급 엔진 컴파일러(vendor/plc-simulator packages/runtime/src/sim-engine/compile/rung.ts,
설계 R1~R6)를 그대로 옮긴 것이다: 세로선 묶음 = 정션, 행 안 contact/box/hwire/coil 연속 = 세그먼트,
세그먼트 출발 = 전원선(0열)·정션(왼쪽 칸이 vwire)·끊김.
"""
import hashlib, json, random, re, subprocess, sys
from collections import Counter

REPO = '<repos>/plc-twin-lab'
COMMIT = 'af9cc400428d63bcf3aa139bf9f6c1de66765322'
CELLS = ['cell-a', 'cell-b', 'cell-b-pack']
ACTIONS = {'MOVE', 'ADD', 'SUB', 'MUL', 'DIV'}           # 실행되는 박스 = 출력 요소
TARGET_GROUPS = ['안전', '밀기 순서', '출력', '알람', '복귀', '포장 핸드셰이크']
CAP = 2000                                              # 셀별 (변종 x 시나리오) 상한
SEED = 20260930
# 셀별 시나리오 수(TR-2026-03 v0.3 §4 표). 원본 기준 실행은 상한 계산에 넣지 않는다.
SCENARIOS = {'cell-a': 2, 'cell-b': 11, 'cell-b-pack': 6}


def git_blob(path):
    raw = subprocess.check_output(['git', '-C', REPO, 'show', f'{COMMIT}:{path}'])
    return raw, hashlib.sha256(raw).hexdigest()


def normalise(grid):
    width = max((len(r) for r in grid), default=0)
    return [[(row[c] if c < len(row) else {'k': 'empty'}) for c in range(width)] for row in grid]


def rung_graph(grid):
    """rung.ts buildRungGraph 이식. 반환: 세그먼트 목록(source, elements, sink)."""
    g = normalise(grid)
    h, w = len(g), (len(g[0]) if g else 0)
    jid = [[-1] * w for _ in range(h)]
    n = 0
    for c in range(w):
        r = 0
        while r < h:
            if g[r][c]['k'] != 'vwire':
                r += 1
                continue
            while r < h and g[r][c]['k'] == 'vwire':
                jid[r][c] = n
                r += 1
            n += 1
    segs = []
    for r in range(h):
        def source(col):
            if col == 0:
                return ('rail',)
            if g[r][col - 1]['k'] == 'vwire':
                return ('j', jid[r][col - 1])
            return ('dead',)
        open_ = None
        for c in range(w):
            cell = g[r][c]
            k = cell['k']
            if k in ('contact', 'box', 'hwire'):
                if open_ is None:
                    open_ = {'src': source(c), 'el': []}
                if k != 'hwire':
                    open_['el'].append((r, c, cell))
                continue
            if k == 'coil':
                if open_ is None:
                    open_ = {'src': source(c), 'el': []}
                segs.append((open_['src'], open_['el'], ('coil', r, c, cell)))
                open_ = 'stop'
                break
            if k == 'vwire':
                seg = open_ if open_ is not None else {'src': source(c), 'el': []}
                if open_ is not None or seg['src'][0] != 'dead':
                    segs.append((seg['src'], seg['el'], ('j', jid[r][c])))
                open_ = None
                continue
            if open_ is not None:                       # empty: 끊김
                segs.append((open_['src'], open_['el'], ('dead',)))
            open_ = None
        if open_ not in (None, 'stop'):
            segs.append((open_['src'], open_['el'], ('dead',)))
    return segs


def analyse(grid):
    """조건마다 그 조건을 모두 막으면 전력이 끊기는 출력 요소 수."""
    segs = rung_graph(grid)
    succ, targets = {}, []
    def add(a, b):
        succ.setdefault(a, []).append(b)
    for src, els, sink in segs:
        prev = 'RAIL' if src[0] == 'rail' else (('J', src[1]) if src[0] == 'j' else None)
        if prev is None:
            prev = ('DEAD', id(els))
        for r, c, cell in els:
            node = ('E', r, c)
            add(prev, node)
            prev = node
            if cell['k'] == 'box' and cell['fb'] in ACTIONS:
                targets.append(node)
        if sink[0] == 'coil':
            node = ('C', sink[1], sink[2])
            add(prev, node)
            targets.append(node)
        elif sink[0] == 'j':
            add(prev, ('J', sink[1]))
    def reach(blocked=frozenset()):
        seen, stack = {'RAIL'}, ['RAIL']
        while stack:
            for nxt in succ.get(stack.pop(), []):
                if nxt not in blocked and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen
    live = reach()
    # 조건 = 같은 렁 안 같은 태그·같은 모드 접점 묶음. 생성기가 병렬 가지마다 같은 인터록을 되풀이해 적으므로
    # 접점 하나가 아니라 조건 하나를 막았을 때 끊기는 출력 요소가 있는지로 판정한다.
    conds = {}
    for _, els, _ in segs:
        for r, c, cell in els:
            if cell['k'] == 'contact':
                conds.setdefault((cell['tag'], cell['mode']), []).append((r, c))
    out = []
    for (tag, mode), cells in conds.items():
        nodes = frozenset(('E', r, c) for r, c in cells)
        cut = reach(nodes)
        dom = [t for t in targets if t in live and t not in cut]
        out.append(dict(cells=sorted(cells), tag=tag, mode=mode, live=any(x in live for x in nodes), dominates=len(dom)))
    coils = {s[2][3]['tag'] for s in segs if s[2][0] == 'coil'}
    return out, coils


def group_of(comment):
    m = re.match(r'\[([^\]]+)\]', comment or '')
    return m.group(1) if m else None


def main(out_path):
    result = dict(schema='tr03-variants/1', source=dict(repo='plc-twin-lab', commit=COMMIT), rule_version='TR-2026-03 v0.3 §3',
                  cap=CAP, seed=SEED, scenarios=SCENARIOS, target_groups=TARGET_GROUPS, python=sys.version.split()[0], cells={})
    variants = []
    for cell in CELLS:
        path = f'ladders/{cell}/correct/program.ldprog.json'
        raw, digest = git_blob(path)
        prog = json.loads(raw)
        tally = Counter()
        found = []
        for i, rung in enumerate(prog['rungs']):
            group = group_of(rung.get('comment'))
            info, coils = analyse(rung['grid'])
            for x in info:
                tally['조건 전체'] += 1
                tally['접점 칸 전체'] += len(x['cells'])
                if not x['live']:
                    tally['전원 없는 조건'] += 1
                    continue
                if x['dominates'] == 0:
                    tally['병렬 분기 안 조건'] += 1
                    continue
                if x['mode'] in ('P', 'N'):
                    tally['에지 검출 조건(P/N)'] += 1
                    continue
                if x['tag'] in coils:
                    tally['자기유지 조건'] += 1
                    continue
                tally['직렬 조건'] += 1
                if group not in TARGET_GROUPS:
                    tally['직렬 조건 — 대상 밖 묶음'] += 1
                    continue
                found.append(dict(cell=cell, rung=i, rung_id=rung['id'], cells=x['cells'], row=x['cells'][0][0], col=x['cells'][0][1],
                                  tag=x['tag'], mode=x['mode'], group=group))
        boxes = Counter(c['fb'] for r in prog['rungs'] for row in r['grid'] for c in row if c['k'] == 'box')
        tally['비교 박스(대상 밖)'] = sum(v for k, v in boxes.items() if k not in ACTIONS)
        by_group = Counter(v['group'] for v in found)
        s = SCENARIOS[cell]
        total_runs = len(found) * s
        if total_runs <= CAP:
            per_group, chosen = None, found
        else:
            groups = [g for g in TARGET_GROUPS if by_group[g]]
            per_group = CAP // (s * len(groups))
            rng = random.Random(f'{SEED}:{cell}')
            chosen = []
            for g in groups:
                pool = [v for v in found if v['group'] == g]
                chosen += pool if len(pool) <= per_group else sorted(rng.sample(pool, per_group), key=lambda v: (v['rung'], v['row'], v['col']))
        chosen_keys = {(v['rung'], v['row'], v['col']) for v in chosen}
        for n, v in enumerate(found, 1):
            v['id'] = f"{cell}-{n:04d}"
            v['sampled'] = (v['rung'], v['row'], v['col']) in chosen_keys
            variants.append(v)
        result['cells'][cell] = dict(ladder=path, ladder_sha256=digest, rungs=len(prog['rungs']), tally=dict(tally),
                                     target_by_group={g: by_group[g] for g in TARGET_GROUPS},
                                     scenarios=s, runs_if_all=total_runs, stratified=per_group is not None,
                                     per_group_n=per_group, sampled=len(chosen), runs_sampled=len(chosen) * s)
    result['variants'] = variants
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + '\n'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(text)
    print(json.dumps({k: {x: y for x, y in v.items() if x != 'ladder'} for k, v in result['cells'].items()}, ensure_ascii=False, indent=1))
    print('sha256', hashlib.sha256(text.encode()).hexdigest())


if __name__ == '__main__':
    main(sys.argv[1])
