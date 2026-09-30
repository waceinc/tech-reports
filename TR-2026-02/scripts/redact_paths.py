#!/usr/bin/env python3
"""TR-2026-02 public bundle: deterministic path redaction and run-record packing.

What it does
  * Replaces each local absolute directory prefix listed in a map file with a fixed placeholder
    (for this bundle: one prefix -> "<repos>/"). Every other byte is left unchanged.
  * Refuses to redact a file that already contains a placeholder, so the substitution is
    exactly reversible: restore(redact(x)) == x. The build checks this for every file.
  * Packs a run folder into a deterministic .tar.xz (sorted members, fixed mtime/owner/mode,
    empty scratch directories skipped) and writes a TSV with the public and original SHA-256
    of every member.

The map file with the original prefix is NOT part of the bundle. `redaction_map_public.json` names
the placeholder only. The original hashes of redacted files therefore cannot be reproduced from the
bundle alone; the report and MANIFEST.md give them as correspondences with values recorded elsewhere.

Usage
  redact_paths.py redact  --map MAP IN OUT
  redact_paths.py restore --map MAP IN OUT
  redact_paths.py pack-runs --map MAP --src RUN_DIR --out RUNS.tar.xz --tsv FILES.tsv
  redact_paths.py public-map --map MAP OUT.json
  redact_paths.py --selftest
Python 3 standard library only.
"""
import hashlib
import io
import json
import lzma
import sys
import tarfile
from pathlib import Path

MTIME = 1790730985  # 2026-09-30 01:16:25 UTC = end of the official round (10:16:25 KST)
SKIP_DIRS = {'cache', 'clang-cache', 'config', 'tmp'}  # empty scratch directories of each run


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_map(path):
    pairs = [(a.encode(), b.encode()) for a, b in json.loads(Path(path).read_text())['prefixes']]
    return sorted(pairs, key=lambda p: -len(p[0]))  # longest prefix first


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
    """Redact and prove the round trip; returns (public bytes, replaced count)."""
    out = redact(data, pairs)
    if restore(out, pairs) != data:
        raise ValueError('round trip failed')
    n = sum(data.count(o) for o, _ in pairs)
    return out, n


def pack_runs(pairs, src, out, tsv):
    src = Path(src)
    root = src.name
    files, dirs = [], set()
    for p in sorted(src.rglob('*')):
        rel = p.relative_to(src)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.is_file():
            files.append(rel)
            for i in range(1, len(rel.parts)):
                dirs.add(Path(*rel.parts[:i]))
    rows = ['path\tbytes_public\tsha256_public\tsha256_original\tchanged\treplaced_prefixes']
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.GNU_FORMAT) as tar:
        members = sorted([(d, True) for d in dirs] + [(f, False) for f in files], key=lambda x: str(x[0]))
        tar.addfile(_info(root + '/', True, 0))
        for rel, is_dir in members:
            name = root + '/' + rel.as_posix()
            if is_dir:
                tar.addfile(_info(name + '/', True, 0))
                continue
            raw = (src / rel).read_bytes()
            pub, n = checked(raw, pairs)
            tar.addfile(_info(name, False, len(pub)), io.BytesIO(pub))
            rows.append('\t'.join([name, str(len(pub)), sha(pub), sha(raw), 'yes' if pub != raw else 'no', str(n)]))
    data = buf.getvalue()
    Path(out).write_bytes(lzma.compress(data, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=6))
    Path(tsv).write_text('\n'.join(rows) + '\n')
    return len(files), sha(data)


def _info(name, is_dir, size):
    ti = tarfile.TarInfo(name)
    ti.type = tarfile.DIRTYPE if is_dir else tarfile.REGTYPE
    ti.mode = 0o755 if is_dir else 0o644
    ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname, ti.size = MTIME, 0, 0, '', '', size
    return ti


def public_map(pairs, out):
    items = [dict(placeholder=ph.decode(), replaces='one local absolute directory prefix') for _, ph in pairs]
    Path(out).write_text(json.dumps(dict(prefixes=items), indent=1, sort_keys=True) + '\n')


def selftest():
    pairs = [(b'/home/someone/src/', b'<repos>/')]
    x = b'{"/home/someone/src/a/b.json": "1", "k": "/home/someone/src/c"}\n'
    y, n = checked(x, pairs)
    assert y == b'{"<repos>/a/b.json": "1", "k": "<repos>/c"}\n' and n == 2
    try:
        redact(b'already <repos>/ here', pairs)
    except ValueError:
        pass
    else:
        raise AssertionError('placeholder in input must be refused')
    assert checked(b'no path', pairs) == (b'no path', 0)
    print('[PASS] selftest 3/3')


def main(argv):
    if not argv or argv[0] in ('-h', '--help') or ('--map' not in argv and argv[0] != '--selftest'):
        print(__doc__)
        return None
    if argv[:1] == ['--selftest']:
        return selftest()
    cmd, args = argv[0], argv[1:]
    pairs = load_map(args[args.index('--map') + 1])
    rest = [a for i, a in enumerate(args) if a != '--map' and (i == 0 or args[i - 1] != '--map')]
    if cmd == 'redact':
        pub, n = checked(Path(rest[0]).read_bytes(), pairs)
        Path(rest[1]).write_bytes(pub)
        print(n, sha(Path(rest[0]).read_bytes()), sha(pub))
    elif cmd == 'restore':
        Path(rest[1]).write_bytes(restore(Path(rest[0]).read_bytes(), pairs))
    elif cmd == 'pack-runs':
        opt = {rest[i]: rest[i + 1] for i in range(0, len(rest), 2)}
        n, tar_sha = pack_runs(pairs, opt['--src'], opt['--out'], opt['--tsv'])
        print(n, 'files; uncompressed tar sha256', tar_sha)
    elif cmd == 'public-map':
        public_map(pairs, rest[0])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
