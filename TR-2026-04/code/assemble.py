"""TR-2026-04 assembly: generator output -> judged program file.

  python3 assemble.py --task <task folder> --kind whole|blank --start <rung index> --marker <engine marker text> --out <program.ldprog.json> --record <record.json>

whole : out/program.ldprog.json as written by the generator.
blank : base.ldprog.json with out/blank.json {"tags": [...], "rungs": [...]} inserted before rung --start;
        new tags appended after the base tags (an entry identical to a base tag is dropped as a duplicate).
Both  : the engine-required `marker` (text given by --marker, kept out of this file) is set right after `schemaVersion` (the generator is told not to write it;
        whether it wrote one, and its value, is recorded). Nothing else is changed. Output is indent=2 UTF-8 JSON.
Exit 0 always; a format problem is recorded as {"format_ok": false} and no program file is written.
"""
import argparse, json
from pathlib import Path

def with_marker(prog, marker):
    out = {}
    for k, v in prog.items():
        if k == 'marker':
            continue
        out[k] = v
        if k == 'schemaVersion':
            out['marker'] = marker
    if 'marker' not in out:
        out['marker'] = marker
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--kind', choices=['whole', 'blank'], required=True)
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--marker', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--record', required=True)
    a = ap.parse_args()
    task = Path(a.task)
    rec = {'kind': a.kind, 'format_ok': False}
    try:
        if a.kind == 'whole':
            prog = json.loads((task / 'out' / 'program.ldprog.json').read_text(encoding='utf-8'))
            if not isinstance(prog, dict):
                raise ValueError('top level is not an object')
        else:
            base = json.loads((task / 'base.ldprog.json').read_text(encoding='utf-8'))
            gen = json.loads((task / 'out' / 'blank.json').read_text(encoding='utf-8'))
            if not isinstance(gen, dict) or not isinstance(gen.get('rungs'), list) or not isinstance(gen.get('tags', []), list):
                raise ValueError('blank.json must be {"tags": [...], "rungs": [...]}')
            prog = dict(base)
            prog['rungs'] = base['rungs'][:a.start] + gen['rungs'] + base['rungs'][a.start:]
            prog['tags'] = base['tags'] + [t for t in gen.get('tags', []) if t not in base['tags']]
            rec['inserted_rungs'] = len(gen['rungs'])
            rec['new_tags'] = len(prog['tags']) - len(base['tags'])
        rec['generator_wrote_marker'] = 'marker' in prog
        rec['generator_marker_value'] = prog.get('marker')
        Path(a.out).write_text(json.dumps(with_marker(prog, a.marker), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        rec['format_ok'] = True
    except Exception as e:  # recorded, judged as a static failure
        rec['error'] = str(e)[:400]
    Path(a.record).write_text(json.dumps(rec, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(rec, ensure_ascii=False))


if __name__ == '__main__':
    main()
