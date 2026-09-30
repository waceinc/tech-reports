#!/usr/bin/env python3
"""TR-2026-03 public bundle: deterministic path redaction and run-record packing.

What it does
  * Replaces each local absolute directory prefix listed in a map file with a fixed placeholder
    (this bundle: three prefixes -> "<repos>/", "<work>/", "<tmp>/"). Every other byte is unchanged.
    It refuses input that already contains a placeholder, so restore(redact(x)) == x; the build checks
    this for every file.
  * Packs the run folders of one cell of round tr03-official-1 into a deterministic .tar.xz and writes a
    TSV row per released member (public and original SHA-256, transform) and per file left out.
  * Selection (the same rule for every run of a cell; see MANIFEST.md):
      released for every run   metadata.json, summary.json, processes.json, tr03-adapter.json, static.json,
                               plc-stderr.log, vision-stderr.log, failure.json (if present)
      cell A only              trace.jsonl and reference-10ms-differences.json (gunzipped, then redacted)
      not released             cells B and pack: trace.jsonl.gz, reference-10ms-differences.json.gz,
                               constants.json, flow.plccell.json; all runs: the empty scratch folders
      summary.json, cells B and pack: the "tick_hashes" list is removed (JSON re-serialised with the
                               original settings; the build checks that re-inserting it gives the original
                               bytes). "trace_hash" (SHA-256 of that list) stays.
      root files (cell A archive only): ledger.jsonl, STATUS.txt, run-header.json, fixed-inputs-*.json,
                               ladders/ladders-sha256.json, ladders/generator-result.json
The map with the original prefixes is NOT released; `redaction_map_public.json` names the placeholders.

Usage
  redact_pack.py redact --map MAP IN OUT
  redact_pack.py pack --map MAP --src ROUND_DIR --cell CELL --out OUT.tar.xz --tsv OUT.tsv [--root-files]
  redact_pack.py --selftest
Python 3 standard library only.
"""
import gzip
import hashlib
import io
import json
import lzma
import sys
import tarfile
from pathlib import Path

MTIME = 1790800018  # 2026-09-30 20:26:58 UTC = end of the official round (2026-10-01 05:26:58 KST)
SKIP_DIRS = {'cache', 'clang-cache', 'config', 'tmp'}
ALL_RUNS = ['metadata.json', 'summary.json', 'processes.json', 'tr03-adapter.json', 'static.json',
            'plc-stderr.log', 'vision-stderr.log', 'failure.json']
CELL_A_GZ = ['trace.jsonl.gz', 'reference-10ms-differences.json.gz']
ROOT_FILES = ['ledger.jsonl', 'STATUS.txt', 'run-header.json', 'ladders/ladders-sha256.json', 'ladders/generator-result.json']


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_map(path):
    pairs = [(a.encode(), b.encode()) for a, b in json.loads(Path(path).read_text())['prefixes']]
    return sorted(pairs, key=lambda p: -len(p[0]))


def redact(data, pairs):
    for _, ph in pairs:
        if ph in data:
            raise ValueError('input already contains placeholder %r' % ph)
    for orig, ph in pairs:
        data = data.replace(orig, ph)
    return data


def restore(data, pairs):
    for orig, ph in pairs:
        data = data.replace(ph, orig)
    return data


def checked(data, pairs):
    out = redact(data, pairs)
    if restore(out, pairs) != data:
        raise ValueError('round trip failed')
    return out, sum(data.count(o) for o, _ in pairs)


def dumps_like(obj, raw):
    """Re-serialise obj with the settings that reproduce raw exactly; raises if none does."""
    for kw in (dict(indent=2, ensure_ascii=False), dict(indent=2), dict(indent=1, ensure_ascii=False)):
        for end in ('\n', ''):
            if (json.dumps(obj, **kw) + end).encode() == raw:
                return kw, end
    raise ValueError('no serialisation reproduces the original summary bytes')


def drop_tick_hashes(raw):
    obj = json.loads(raw)
    kw, end = dumps_like(obj, raw)
    keys = list(obj)
    pub = {k: v for k, v in obj.items() if k != 'tick_hashes'}
    out = (json.dumps(pub, **kw) + end).encode()
    back = json.loads(out)
    rebuilt = {k: (obj['tick_hashes'] if k == 'tick_hashes' else back[k]) for k in keys}
    if (json.dumps(rebuilt, **kw) + end).encode() != raw:
        raise ValueError('re-inserting tick_hashes does not give the original bytes')
    return out


def _info(name, is_dir, size):
    ti = tarfile.TarInfo(name)
    ti.type = tarfile.DIRTYPE if is_dir else tarfile.REGTYPE
    ti.mode = 0o755 if is_dir else 0o644
    ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname, ti.size = MTIME, 0, 0, '', '', size
    return ti


def cell_of(name):
    return 'cell-b-pack' if 'cell-b-pack' in name else 'cell-b' if 'cell-b' in name else 'cell-a'


def plan(src, cell, root_files):
    """Returns (released: [(member path, source file, transform)], left_out: [(path, bytes, sha256, why)])."""
    rel, out = [], []
    ledger = {json.loads(l)['name']: json.loads(l) for l in (src / 'ledger.jsonl').read_text().splitlines() if l.strip()}
    if root_files:
        for f in ROOT_FILES + sorted(p.name for p in src.glob('fixed-inputs-*.json')):
            rel.append((f, src / f, 'redact'))
    for d in sorted(p for p in src.iterdir() if p.is_dir() and p.name[:4].isdigit() and cell_of(p.name) == cell):
        gz = {f['file'] + '.gz': f for f in ledger[d.name].get('files') or []}
        for p in sorted(d.iterdir()):
            if p.is_dir():
                if p.name not in SKIP_DIRS or any(p.iterdir()):
                    raise ValueError('unexpected folder %s' % p)
                continue
            if p.name in ALL_RUNS:
                t = 'drop_tick_hashes+redact' if p.name == 'summary.json' and cell != 'cell-a' else 'redact'
                rel.append((f'{d.name}/{p.name}', p, t))
            elif p.name in CELL_A_GZ and cell == 'cell-a':
                rel.append((f'{d.name}/{p.name[:-3]}', p, 'gunzip+redact'))
            else:
                g = gz.get(p.name)
                why = 'too large (trace)' if p.name.startswith('trace') else 'not a metric of this report' \
                    if p.name.startswith('reference') else 'plant-model file (private)'
                out.append((f'{d.name}/{p.name}', p.stat().st_size, g['gz_sha256'] if g else sha(p.read_bytes()), why))
    return rel, out


def pack(pairs, src, cell, out, tsv, root_files):
    src = Path(src)
    top = src.name
    rel, left = plan(src, cell, root_files)
    rows = ['path\tbytes_public\tsha256_public\tsha256_original\ttransform\treplaced_prefixes']
    dirs = sorted({str(Path(m).parent) for m, _, _ in rel if str(Path(m).parent) != '.'})
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.GNU_FORMAT) as tar:
        tar.addfile(_info(top + '/', True, 0))
        items = sorted([(d, None, 'dir') for d in dirs] + rel, key=lambda x: x[0])
        for m, p, t in items:
            if t == 'dir':
                tar.addfile(_info(f'{top}/{m}/', True, 0))
                continue
            raw = p.read_bytes()
            if t == 'gunzip+redact':
                raw = gzip.decompress(raw)
            base = drop_tick_hashes(raw) if t.startswith('drop_tick_hashes') else raw
            pub, n = checked(base, pairs)
            tar.addfile(_info(f'{top}/{m}', False, len(pub)), io.BytesIO(pub))
            label = ('gunzip' if t.startswith('gunzip') else 'none') if pub == raw else t
            rows.append('\t'.join([f'{top}/{m}', str(len(pub)), sha(pub), sha(raw), label, str(n)]))
    data = buf.getvalue()
    Path(out).write_bytes(lzma.compress(data, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=6))
    rows.append('')
    Path(tsv).write_text('\n'.join(rows))
    lt = Path(str(tsv).replace('.tsv', '_left_out.tsv'))
    lt.write_text('path\tbytes\tsha256\twhy\n' + ''.join(f'{top}/{a}\t{b}\t{c}\t{d}\n' for a, b, c, d in left))
    return len(rel), len(left), sha(data)


def selftest():
    pairs = [(b'/home/someone/src/', b'<repos>/')]
    y, n = checked(b'{"/home/someone/src/a": 1, "k": "/home/someone/src/c"}\n', pairs)
    assert y == b'{"<repos>/a": 1, "k": "<repos>/c"}\n' and n == 2
    try:
        redact(b'already <repos>/ here', pairs)
        raise AssertionError('placeholder in input must be refused')
    except ValueError:
        pass
    raw = (json.dumps({'a': 1, 'tick_hashes': ['x', 'y'], 'trace_hash': 'z'}, indent=2) + '\n').encode()
    assert json.loads(drop_tick_hashes(raw)) == {'a': 1, 'trace_hash': 'z'}
    try:
        drop_tick_hashes(b'{"a":1,"tick_hashes":[]}')
        raise AssertionError('non-reproducible serialisation must be refused')
    except ValueError:
        pass
    print('[PASS] selftest 4/4')


def main(argv):
    if argv[:1] == ['--selftest']:
        return selftest()
    if not argv or '--map' not in argv:
        print(__doc__)
        return None
    cmd, args = argv[0], argv[1:]
    pairs = load_map(args[args.index('--map') + 1])
    if cmd == 'redact':
        rest = [a for i, a in enumerate(args) if a != '--map' and args[i - 1] != '--map']
        pub, n = checked(Path(rest[0]).read_bytes(), pairs)
        Path(rest[1]).write_bytes(pub)
        print(n, sha(Path(rest[0]).read_bytes()), sha(pub))
    elif cmd == 'pack':
        opt = {args[i]: args[i + 1] for i in range(len(args) - 1) if args[i].startswith('--') and args[i] != '--root-files'}
        print(*pack(pairs, opt['--src'], opt['--cell'], opt['--out'], opt['--tsv'], '--root-files' in args))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
