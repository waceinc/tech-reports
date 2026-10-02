"""TR-2026-04 task packages. Deterministic: same inputs -> same bytes (package hashes are pre-registered).

  python3 make_tasks.py --ladders <ladders folder> --tagmaps <tagmap folder> --tasks <task list json>
                        --specs <folder with the three specifications and the appendix> --out <empty folder>

Per task folder Txx/: TASK.md · spec/*.md · appendix.md · io.json · (fill-in tasks) base.ldprog.json.
The reference ladder given as base has the fill-in block removed, block-only internal tags removed and no `marker`.
Prints one "sha256  path" line per file and the tree hash (sha256 of those lines).
"""
import argparse, hashlib, json
from pathlib import Path

SPECS = {'cell-a': ['TR-04_사양서_셀A_v1.md'], 'cell-b': ['TR-04_사양서_셀B_v1.md'],
         'cell-b-pack': ['TR-04_사양서_셀B_v1.md', 'TR-04_사양서_포장셀_v1.md']}
APPENDIX = 'TR-04_부록_엔진지원명령_v2.md'
CELL_NAME = {'cell-a': '셀 A', 'cell-b': '셀 B', 'cell-b-pack': '포장 셀'}


def dump(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=1) + '\n').encode()


def refs(rungs):
    read, write = set(), set()
    for r in rungs:
        for row in r['grid']:
            for c in row:
                if c['k'] == 'contact':
                    read.add(c['tag'])
                elif c['k'] == 'coil':
                    write.add(c['tag'])
                elif c['k'] == 'box':
                    read |= set(c.get('inputs', {}).values())
                    write |= set(c.get('outputs', {}).values())
    return read, write


def io_table(tagmap, ladder):
    read, write = refs(ladder['rungs'])
    rows = []
    for b in tagmap['bindings']:
        used = b['tag'] in (read if b['direction'] == 'in' else write)
        rows.append({'tag': b['tag'], 'address': b['address'], 'type': b.get('type', 'BOOL'), 'direction': b['direction'],
                     'use': 'required' if used else 'declared_only', 'meaning': b.get('meaning', '')})
    return {'io': rows}


def task_md(t, specs, base_info):
    cell = CELL_NAME[t['cell']]
    lines = [f"# 과제 {t['id']} — {cell} {'전체 래더' if t['kind'] == '전체' else '빈칸 채우기: ' + t['group']}", '',
             '## 할 일', '']
    if t['kind'] == '전체':
        lines += [f'`spec/` 의 사양서만 보고 {cell} 전체를 제어하는 래더 프로그램 파일 하나를 만든다.', '',
                  '만들 파일: `out/program.ldprog.json` — 부록(`appendix.md`) §1 형식의 프로그램 파일 전체.']
    else:
        lines += [f"`base.ldprog.json` 은 {cell}의 완성된 래더에서 「{t['group']}」 기능 묶음 렁 {t['rung_count']} 개를 뺀 것이다. "
                  f"빠진 렁은 base 의 렁 목록에서 번호 {t['rungs'][0]} 자리(0 부터 센다, 그 앞 렁 뒤)에 들어간다. 빠진 기능을 사양서대로 다시 만든다.", '',
                  '만들 파일: `out/blank.json` — `{"tags": [새로 선언할 내부 태그], "rungs": [끼울 렁들, 순서대로]}`.',
                  '', '끼울 렁이 읽어야 하는 태그(렁 밖에서 오는 것): ' + (', '.join(f'`{x}`' for x in t['input_tags']) or '없음'),
                  '', '끼울 렁이 정해야 하는 태그(렁 밖에서 읽히거나 출력인 것): ' + (', '.join(f'`{x}`' for x in t['output_tags']) or '없음'),
                  '', f"base 에 이미 있는 태그 {base_info['tags']} 개는 다시 선언하지 않는다. 새 내부 태그의 주소는 base 의 주소와 겹치지 않게 한다."]
    lines += ['', '## 읽을 파일', '', '- 사양서: ' + ', '.join(f'`spec/{s}`' for s in specs), '- 부록(엔진이 받는 요소와 명령): `appendix.md`',
              '- 입출력 표: `io.json` (이름·주소·형식을 바꾸지 않는다. `use` 가 `required` 인 입력은 읽고 출력은 정한다)']
    if t['kind'] != '전체':
        lines.append('- 빈칸이 빠진 래더: `base.ldprog.json`')
    lines += ['', '## 규칙', '', '- 사양서와 부록만 근거로 쓴다. 이 폴더 밖 파일은 없다고 생각한다.',
              '- `marker` 필드는 쓰지 않는다. 판정기가 붙인다.',
              '- 만들 파일 하나만 쓴다. 설명 문장은 파일 안에 넣지 않는다(렁 `comment` 는 써도 된다).',
              '- 시뮬레이터나 검사기는 없다. 파일을 낸 뒤 판정기가 컴파일하고, 오류가 나면 오류 문장을 돌려준다(최대 2 회).', '']
    return '\n'.join(lines).encode()


def main():
    ap = argparse.ArgumentParser()
    for k in ('--ladders', '--tagmaps', '--tasks', '--specs', '--out'):
        ap.add_argument(k, required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    tasks = json.loads(Path(a.tasks).read_text())['tasks']
    files = {}
    for t in tasks:
        ladder = json.loads((Path(a.ladders) / t['cell'] / 'correct' / 'program.ldprog.json').read_text())
        tagmap = json.loads((Path(a.tagmaps) / f"{t['cell']}.tagmap.json").read_text())
        d = t['id']
        files[f'{d}/io.json'] = dump(io_table(tagmap, ladder))
        files[f'{d}/appendix.md'] = (Path(a.specs) / APPENDIX).read_bytes()
        for s in SPECS[t['cell']]:
            files[f'{d}/spec/{s}'] = (Path(a.specs) / s).read_bytes()
        base_info = {'tags': 0}
        if t['kind'] != '전체':
            s0, s1 = t['rungs']
            block = ladder['rungs'][s0:s1 + 1]
            rest = ladder['rungs'][:s0] + ladder['rungs'][s1 + 1:]
            br, bw = refs(block)
            rr, rw = refs(rest)
            io_tags = {b['tag'] for b in tagmap['bindings']}
            block_only = (br | bw) - (rr | rw) - io_tags
            base = {k: v for k, v in ladder.items() if k != 'marker'}
            base['tags'] = [x for x in ladder['tags'] if x['symbol'] not in block_only]
            base['rungs'] = rest
            base_info['tags'] = len(base['tags'])
            files[f'{d}/base.ldprog.json'] = dump(base)
        files[f'{d}/TASK.md'] = task_md(t, SPECS[t['cell']], base_info)
    lines = []
    for rel in sorted(files):
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(files[rel])
        lines.append(f'{hashlib.sha256(files[rel]).hexdigest()}  {rel}\n')
    (out / 'PACKAGES.sha256').write_text(''.join(lines))
    print(''.join(lines), end='')
    print('tree', hashlib.sha256(''.join(lines).encode()).hexdigest())


if __name__ == '__main__':
    main()
