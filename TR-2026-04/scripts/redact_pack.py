#!/usr/bin/env python3
"""TR-2026-04 public bundle: path redaction, appendix screening and deterministic packing of the run records.

What it does
  * Replaces each local absolute directory prefix listed in a private config with a fixed placeholder
    (this bundle: "<docs>", "<work>", "<run>", "<repos>", "<models>"). Every other byte is unchanged. Input that
    already contains a placeholder is refused, so restore(redact(x)) == x; this is checked for every file.
  * Screens every candidate file for text of the private appendix (the engine's supported-instruction list, released
    by SHA-256 only) and for the engine marker string; a file that contains either is left out and listed.
  * Packs the judging records of one cell (round tr04-official-1) or the generation records (all units) into a
    deterministic .tar.xz and writes a TSV row per released member and per file left out.
Selection (the same rule for every unit; MANIFEST.md states it in words)
  judging, every unit     verdict.json, static.json, force.json (the judged ladder program.ldprog.json is released
                          separately as a public version, the engine marker line removed)
  judging, every run      metadata.json, summary.json, processes.json, static.json, io_verdict.json, failure.json,
                          plc-stderr.log, vision-stderr.log, reference-10ms-differences.json
  cell A only             trace.jsonl; cells B and pack: trace.jsonl left out (size), "tick_hashes" removed from
                          summary.json ("trace_hash" kept; re-inserting the list gives the original bytes)
  cell-A archive root     summary.json, STATUS.md and g3_server.log of the round folder
  generation, every unit  unit.json, assemble-*.json, compile.json, g3_reply_meta.json, prompt-*.txt, generator.log
                          (if it holds no appendix text), TASK.md, io.json, base.ldprog.json, spec/*.md, out/*;
                          left out: appendix.md, assembled.ldprog.json (holds the engine marker; same bytes as the
                          judged ladder), tool state (.claude-tmp/, cache-break-state-*.json), the isolation probe file
  all archives            file members keep their original modification time (whole seconds): the leak check's
                          late-file rule reads it, and the report's judging times come from the verdict file times;
                          folders get one fixed time
Usage
  redact_pack.py redact CONFIG IN OUT
  redact_pack.py judging CONFIG CELL OUT.tar.xz OUT_files.tsv OUT_not_released.tsv
  redact_pack.py generation CONFIG OUT.tar.xz OUT_files.tsv OUT_not_released.tsv
  redact_pack.py ladders CONFIG OUT.tar.xz OUT_files.tsv
  redact_pack.py sens CONFIG OUT.tar.xz OUT_files.tsv OUT_not_released.tsv   (post-hoc sensitivity round)
  redact_pack.py setaside CONFIG OUT.tsv
  redact_pack.py g2headers CONFIG OUT.tsv     (session headers of the withheld G2 logs)
  redact_pack.py sweep CONFIG PATH...        (string search incl. archive members and PNG text chunks)
  redact_pack.py bundlezip FOLDER OUT.zip   (deterministic zip of the release bundle)
  redact_pack.py --selftest
CONFIG is private (local paths, the appendix location, the marker source). Python 3 standard library only.
"""
import hashlib
import importlib.util
import io
import json
import lzma
import re
import sys
import tarfile
import tempfile
import zipfile
import zlib
from pathlib import Path

sys.dont_write_bytecode = True
SKIP_DIRS = {'cache', 'clang-cache', 'config', 'tmp'}
UNIT_FILES = ['verdict.json', 'static.json', 'force.json']
RUN_FILES = ['metadata.json', 'summary.json', 'processes.json', 'static.json', 'io_verdict.json', 'failure.json',
             'plc-stderr.log', 'vision-stderr.log', 'reference-10ms-differences.json']
ROOT_FILES = ['summary.json', 'STATUS.md', 'g3_server.log']
GEN_KEEP = re.compile(r'^(unit\.json|assemble-\d+\.json|compile\.json|g3_reply_meta\.json|prompt-\d+\.txt|generator\.log|'
                      r'TASK\.md|io\.json|base\.ldprog\.json|spec/[^/]+\.md|out/[^/]+)$')
HAN = re.compile(r'[가-힣]')


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Ctx:
    def __init__(self, path):
        c = json.loads(Path(path).read_text(encoding='utf-8'))
        self.c = c
        self.pairs = sorted(((a.encode(), b.encode()) for a, b in c['prefixes']), key=lambda p: -len(p[0]))
        self.marker = json.loads(Path(c['local_json']).read_text(encoding='utf-8'))['engine_marker'].encode()
        body = Path(c['appendix']).read_text(encoding='utf-8').split('---', 2)[2]
        lines = [x.strip() for x in body.splitlines()]
        self.keys = sorted({x for x in lines if len(x) >= 16 and not set(x) <= set('|- :')})
        self.shing = sorted({x[i:i + 30] for x in lines if len(x) >= 30 for i in range(0, len(x) - 29, 10)
                             if len(HAN.findall(x[i:i + 30])) >= 3})
        self.sensitive = c['sensitive']


def norm(b):
    t = b.decode('utf-8', 'replace')
    t2 = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), t)
    t2 = t2.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')
    return t + '\n' + t2


def has_appendix(ctx, data):
    t = norm(data)
    return any(k in t for k in ctx.keys) or any(s in t for s in ctx.shing)


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


def checked(ctx, data, name):
    out = redact(data, ctx.pairs)
    if restore(out, ctx.pairs) != data:
        raise ValueError('round trip failed: %s' % name)
    if b'/Users/' in out:
        raise ValueError('unmapped home path left in %s' % name)
    if ctx.marker in out:
        raise ValueError('engine marker in %s' % name)
    return out, sum(data.count(o) for o, _ in ctx.pairs)


def dumps_like(obj, raw):
    for kw in (dict(indent=1, ensure_ascii=False), dict(indent=2, ensure_ascii=False), dict(indent=2), dict(indent=1)):
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


def _info(name, is_dir, size, mtime):
    ti = tarfile.TarInfo(name)
    ti.type = tarfile.DIRTYPE if is_dir else tarfile.REGTYPE
    ti.mode = 0o755 if is_dir else 0o644
    ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname, ti.size = int(mtime), 0, 0, '', '', size
    return ti


def write_tar(items, out, top, dir_mtime):
    """items: [(member path below top, bytes, mtime)] -> deterministic tar.xz; returns sha256 of the tar."""
    dirs = set()
    for m, _, _ in items:
        p = Path(m).parent
        while str(p) != '.':
            dirs.add(str(p))
            p = p.parent
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.GNU_FORMAT) as tar:
        tar.addfile(_info(top + '/', True, 0, dir_mtime))
        for m, data, mt in sorted([(d, None, dir_mtime) for d in dirs] + list(items), key=lambda x: x[0]):
            if data is None:
                tar.addfile(_info(f'{top}/{m}/', True, 0, mt))
            else:
                tar.addfile(_info(f'{top}/{m}', False, len(data), mt), io.BytesIO(data))
    raw = buf.getvalue()
    Path(out).write_bytes(lzma.compress(raw, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=6))
    return sha(raw), len(items)


def unit_cell(d):
    if d.name.startswith('BASE-'):
        return d.name[5:]
    return json.loads((d / 'verdict.json').read_text())['cell']


def trace_hashes(ctx):
    rows = {}
    for line in Path(ctx.c['trace_hashes']).read_text().splitlines():
        rel, size, h = line.split('\t')
        rows[rel] = (int(size), h)
    return rows


def judging(ctx, cell, out, tsv, lt, src=None, public_ladders=False):
    src = Path(src or ctx.c['results_dir'])
    top, mt = src.name, ctx.c['results_mtime']
    th = trace_hashes(ctx)
    items, rows, left = [], [], []

    def add(rel, raw, transform):
        mtime = (src / rel).stat().st_mtime
        base = drop_tick_hashes(raw) if transform == 'drop_tick_hashes' else raw
        pub, n = checked(ctx, base, rel)
        if has_appendix(ctx, pub):
            left.append((rel, len(raw), sha(raw), 'private: contains appendix text'))
            return
        items.append((rel, pub, mtime))
        label = 'none' if pub == raw else (transform if transform != 'none' else 'redact')
        if transform == 'drop_tick_hashes' and pub != base:
            label = 'drop_tick_hashes+redact'
        rows.append((f'{top}/{rel}', len(pub), sha(pub), sha(raw), label, n))

    if cell == 'cell-a':
        for f in ROOT_FILES:
            add(f, (src / f).read_bytes(), 'none')
    units = sorted(d for d in src.iterdir() if d.is_dir() and (d.name.startswith('BASE-') or d.name[:1] == 'T')
                   and (cell is None or unit_cell(d) == cell))
    conv = None
    if public_ladders:
        spec = importlib.util.spec_from_file_location('conv', ctx.c['convert_script'])
        conv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(conv)
    for d in units:
        for p in sorted(d.iterdir()):
            rel = f'{d.name}/{p.name}'
            if p.is_dir():
                if not p.name.startswith('s3-'):
                    raise ValueError('unexpected folder %s' % p)
                for q in sorted(p.iterdir()):
                    r2 = f'{rel}/{q.name}'
                    if q.is_dir():
                        if q.name not in SKIP_DIRS or any(q.iterdir()):
                            raise ValueError('unexpected folder %s' % q)
                        continue
                    ucell = unit_cell(d)
                    if q.name == 'trace.jsonl':
                        if ucell == 'cell-a':
                            add(r2, q.read_bytes(), 'none')
                        else:
                            size, h = th.get(f'{d.name}/{p.name}/trace.jsonl') or (q.stat().st_size, sha(q.read_bytes()))
                            if size != q.stat().st_size:
                                raise ValueError('trace size changed: %s' % r2)
                            left.append((r2, size, h, 'too large (tick trace)'))
                    elif q.name == 'summary.json':
                        add(r2, q.read_bytes(), 'none' if ucell == 'cell-a' else 'drop_tick_hashes')
                    elif q.name in RUN_FILES:
                        add(r2, q.read_bytes(), 'none')
                    else:
                        raise ValueError('unexpected file %s' % q)
            elif p.name in UNIT_FILES:
                add(rel, p.read_bytes(), 'none')
            elif p.name == 'program.ldprog.json' and conv is not None:
                raw = p.read_bytes()
                pub, n = checked(ctx, conv.convert(raw), rel)
                if has_appendix(ctx, pub) or n:
                    raise ValueError('public ladder not clean: %s' % rel)
                items.append((f'{d.name}/program.public.ldprog.json', pub, p.stat().st_mtime))
                rows.append((f'{top}/{d.name}/program.public.ldprog.json', len(pub), sha(pub), sha(raw), 'marker line removed (pre-registered conversion)', 0))
            elif p.name == 'program.ldprog.json':
                left.append((rel, p.stat().st_size, sha(p.read_bytes()),
                             'holds the engine marker; public version in ladders/ archive'))
            else:
                raise ValueError('unexpected file %s' % p)
    tar_sha, n = write_tar(items, out, top, mt)
    Path(tsv).write_text('path\tbytes_public\tsha256_public\tsha256_original\ttransform\treplaced_prefixes\n' +
                         ''.join('\t'.join(map(str, r)) + '\n' for r in rows))
    Path(lt).write_text('path\tbytes\tsha256\twhy\n' + ''.join(f'{top}/{a}\t{b}\t{c}\t{w}\n' for a, b, c, w in left))
    return n, len(left), tar_sha


def generation(ctx, out, tsv, lt):
    src = Path(ctx.c['work_dir'])
    top = src.name
    bundle_hashes = {}
    items, rows, left = [], [], []
    for p in sorted((src / '_tasks').iterdir()):
        raw = p.read_bytes()
        pub, n = checked(ctx, raw, p.name)
        items.append((f'_tasks/{p.name}', pub, p.stat().st_mtime))
        rows.append((f'{top}/_tasks/{p.name}', len(pub), sha(pub), sha(raw), 'none' if pub == raw else 'redact', n))
    for d in sorted(x for x in src.iterdir() if x.is_dir() and re.match(r'^T\d\d-G\d-r\d$', x.name)):
        for p in sorted(x for x in d.rglob('*') if x.is_file()):
            rel = p.relative_to(d).as_posix()
            mrel = f'{d.name}/{rel}'
            raw = p.read_bytes()
            if rel == 'appendix.md':
                left.append((mrel, len(raw), sha(raw), 'private: the appendix (released by SHA-256 only)'))
                continue
            if rel == 'assembled.ldprog.json':
                left.append((mrel, len(raw), sha(raw), 'holds the engine marker; judged ladder, public version in ladders/ archive'))
                continue
            if rel.startswith('.claude-tmp/') or rel.startswith('cache-break-state-'):
                left.append((mrel, len(raw), sha(raw), 'tool state of the generator CLI (not a record of the study)'))
                continue
            if rel == '.tr04-probe-in.done':
                left.append((mrel, len(raw), sha(raw), 'isolation self-check probe file (content: run marker only)'))
                continue
            if not GEN_KEEP.match(rel):
                raise ValueError('unexpected file %s' % p)
            if has_appendix(ctx, raw):
                left.append((mrel, len(raw), sha(raw), 'private: contains appendix text'))
                continue
            pub, n = checked(ctx, raw, mrel)
            items.append((mrel, pub, p.stat().st_mtime))
            rows.append((f'{top}/{mrel}', len(pub), sha(pub), sha(raw), 'none' if pub == raw else 'redact', n))
    tar_sha, n = write_tar(items, out, top, ctx.c['results_mtime'])
    Path(tsv).write_text('path\tbytes_public\tsha256_public\tsha256_original\ttransform\treplaced_prefixes\n' +
                         ''.join('\t'.join(map(str, r)) + '\n' for r in rows))
    Path(lt).write_text('path\tbytes\tsha256\twhy\n' + ''.join(f'{top}/{a}\t{b}\t{c}\t{w}\n' for a, b, c, w in left))
    return n, len(left), tar_sha


def ladders(ctx, out, tsv):
    spec = importlib.util.spec_from_file_location('conv', ctx.c['convert_script'])
    conv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conv)
    src = Path(ctx.c['results_dir'])
    items, rows = [], []
    for p in sorted(src.glob('*/program.ldprog.json')):
        raw = p.read_bytes()
        pub = conv.convert(raw)
        if ctx.marker in pub or has_appendix(ctx, pub):
            raise ValueError('public ladder still holds marker or appendix text: %s' % p)
        pub2, n = checked(ctx, pub, p.parent.name)
        if n:
            raise ValueError('ladder holds a local path: %s' % p)
        name = f'{p.parent.name}.program.ldprog.json'
        items.append((name, pub2, ctx.c['results_mtime']))
        rows.append((f'ladders/{name}', len(pub2), sha(pub2), sha(raw), 'marker line removed (pre-registered conversion)'))
    tar_sha, n = write_tar(items, out, 'ladders', ctx.c['results_mtime'])
    Path(tsv).write_text('path\tbytes_public\tsha256_public\tsha256_original\ttransform\n' +
                         ''.join('\t'.join(map(str, r)) + '\n' for r in rows))
    return n, tar_sha


SETASIDE = {'_invalid': 'invalid: generator tool failed to start (temporary-folder block), all attempts under 1 s, no output; generated again',
            '_not_run': 'outside the plan: G3 repetition 2 started by the runner after the G3 switch-over stalled; not judged, in no sample',
            '_interrupted': 'unfinished at a pause; moved aside on resume and produced again from the start'}


RELEASED_SETASIDE = {'T07-G3-r2': 'released as runs/tr04-run-1_set_aside_T07-G3-r2_unit.json (byte-identical; cited by the report)'}


def setaside(ctx, out):
    src = Path(ctx.c['work_dir'])
    rows = []
    for k, why in SETASIDE.items():
        for batch in sorted((src / k).iterdir()):
            for u in sorted(x for x in batch.iterdir() if x.is_dir()):
                uj = u / 'unit.json'
                h = sha(uj.read_bytes()) if uj.exists() else '-'
                rel = RELEASED_SETASIDE.get(u.name, 'not released')
                rows.append(f'{k}/{batch.name}/{u.name}\t{u.name}\t{"yes" if uj.exists() else "no"}\t{h}\t{rel}\t{why}\n')
    Path(out).write_text('folder\tunit\tunit.json\tunit_json_sha256_original\tunit_json_released\treason\n' + ''.join(rows))
    return len(rows)


def g2headers(ctx, out):
    """Session headers of the G2 (Codex CLI) generator logs, which are not released because they contain appendix text."""
    src = Path(ctx.c['work_dir'])
    keys = ['model', 'provider', 'approval', 'sandbox', 'reasoning effort']
    rows = []
    for d in sorted(x for x in src.iterdir() if x.is_dir() and re.match(r'^T\d\d-G2-r\d$', x.name)):
        raw = (d / 'generator.log').read_bytes()
        t = raw.decode('utf-8', 'replace')
        heads = re.findall(r'^OpenAI Codex (v[0-9.]+)\n-+\n((?:[a-z ]+: .*\n)+)-+\n', t, re.M)
        for i, (ver, block) in enumerate(heads):
            kv = dict(line.split(': ', 1) for line in block.strip().splitlines())
            rows.append('\t'.join([d.name, str(i), ver] + [kv.get(k, '') for k in keys] + [sha(raw)]) + '\n')
    Path(out).write_text('unit\tsession\tcodex_cli\t' + '\t'.join(k.replace(' ', '_') for k in keys) + '\tgenerator_log_sha256\n' + ''.join(rows))
    return len(rows)


def sens(ctx, out, tsv, lt):
    """Post-hoc sensitivity round (not the main metric): judging records of tr04-sens-late-1 with public ladders, plus the
    new assembly and compile records of the copied unit folders and, for the answers that did not compile, the assembled ladder
    as a public version (every other file of those copies equals the generation archive)."""
    with tempfile.TemporaryDirectory() as td:
        tmp_out = Path(td) / 'judging.tar.xz'
        judging(ctx, None, tmp_out, tsv, lt, src=ctx.c['sens_results_dir'], public_ladders=True)
        with tarfile.open(tmp_out, 'r:xz') as t:
            items = [(m.name.split('/', 1)[1], t.extractfile(m).read(), m.mtime) for m in t.getmembers() if m.isfile()]
    spec = importlib.util.spec_from_file_location('conv', ctx.c['convert_script'])
    conv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conv)
    w = Path(ctx.c['sens_work_dir'])
    rows, left = [], []
    for d in sorted(x for x in w.iterdir() if x.is_dir()):
        for p in sorted(x for x in d.iterdir() if x.is_file()):
            raw = p.read_bytes()
            if p.name == 'assembled.ldprog.json' and not (Path(ctx.c['sens_results_dir']) / d.name).exists():
                # did not compile, so no judged ladder exists: release the assembled ladder as a public version
                pub, n = checked(ctx, conv.convert(raw), p.name)
                if has_appendix(ctx, pub):
                    raise ValueError('appendix text in %s' % p)
                items.append((f'work/{d.name}/assembled.public.ldprog.json', pub, p.stat().st_mtime))
                rows.append((f'tr04-sens-late-1/work/{d.name}/assembled.public.ldprog.json', len(pub), sha(pub), sha(raw),
                             'marker line removed (pre-registered conversion)', n))
                continue
            if not (p.name.startswith('assemble-sens-') or p.name == 'compile.json'):
                continue
            if has_appendix(ctx, raw):
                raise ValueError('appendix text in %s' % p)
            pub, n = checked(ctx, raw, p.name)
            items.append((f'work/{d.name}/{p.name}', pub, p.stat().st_mtime))
            rows.append((f'tr04-sens-late-1/work/{d.name}/{p.name}', len(pub), sha(pub), sha(raw), 'none' if pub == raw else 'redact', n))
    tar_sha, n = write_tar(items, out, 'tr04-sens-late-1', ctx.c['results_mtime'])
    with open(tsv, 'a') as f:
        f.write(''.join('\t'.join(map(str, r)) + '\n' for r in rows))
    return n, tar_sha


def bundlezip(folder, out, stamp=(2026, 10, 2, 12, 45, 0)):
    """Deterministic zip of the bundle folder (sorted names, fixed time, deflate level 9, no extra fields)."""
    folder = Path(folder)
    files = sorted(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name != '.DS_Store')
    with zipfile.ZipFile(out, 'w') as z:
        for p in files:
            zi = zipfile.ZipInfo(f'{folder.name}/{p.relative_to(folder).as_posix()}', date_time=stamp)
            zi.compress_type, zi.create_system, zi.external_attr = zipfile.ZIP_DEFLATED, 3, 0o644 << 16
            z.writestr(zi, p.read_bytes(), compresslevel=9)
    return len(files)


def _members(path):
    p = Path(path)
    if p.suffix == '.xz':
        with tarfile.open(p, 'r:xz') as t:
            for m in t.getmembers():
                if m.isfile():
                    yield f'{p.name}!{m.name}', t.extractfile(m).read()
    elif p.suffix == '.zip':
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                data = z.read(n)
                yield f'{p.name}!{n}', data
                if n.endswith('.tar.xz'):
                    with tarfile.open(fileobj=io.BytesIO(data), mode='r:xz') as t:
                        for m in t.getmembers():
                            if m.isfile():
                                yield f'{p.name}!{n}!{m.name}', t.extractfile(m).read()
    elif p.suffix == '.png':
        data = p.read_bytes()
        yield str(p), data
        i, meta = 8, []
        while i < len(data):
            ln = int.from_bytes(data[i:i + 4], 'big')
            typ = data[i + 4:i + 8]
            chunk = data[i + 8:i + 8 + ln]
            if typ in (b'tEXt', b'iTXt', b'eXIf'):
                meta.append(chunk)
            if typ == b'zTXt':
                k, _, rest = chunk.partition(b'\0')
                meta.append(k + b' ' + zlib.decompress(rest[1:]))
            i += 12 + ln
        yield f'{p}!png-text', b'\n'.join(meta)
    else:
        yield str(p), p.read_bytes()


def sweep(ctx, paths, extra=()):
    """Returns [(where, pattern)] for every sensitive string, marker or appendix text found."""
    pats = [s.encode() for s in ctx.sensitive] + [ctx.marker] + [e.encode() for e in extra]
    found = []
    files = []
    for a in paths:
        a = Path(a)
        files += sorted(x for x in a.rglob('*') if x.is_file()) if a.is_dir() else [a]
    for f in files:
        for where, data in _members(f):
            for pt in pats:
                if pt in data:
                    found.append((where, pt.decode()))
            if has_appendix(ctx, data):
                found.append((where, '<appendix text>'))
    return found


def selftest():
    class C:
        pass
    ctx = C()
    ctx.pairs = [(b'/home/someone/w', b'<work>')]
    ctx.marker = b'MARKER-XYZ'
    out, n = checked(ctx, b'{"p": "/home/someone/w/T01/x"}', 't')
    assert out == b'{"p": "<work>/T01/x"}' and n == 1
    for bad in (b'already <work> here', b'MARKER-XYZ', b'/Users/x'):
        try:
            checked(ctx, bad, 't')
            raise AssertionError('must refuse %r' % bad)
        except ValueError:
            pass
    raw = (json.dumps({'a': 1, 'tick_hashes': ['x'], 'trace_hash': 'z'}, indent=1, ensure_ascii=False) + '\n').encode()
    assert json.loads(drop_tick_hashes(raw)) == {'a': 1, 'trace_hash': 'z'}
    ctx.keys, ctx.shing = ['line of the private appendix text'], []
    assert has_appendix(ctx, b'{"x": "line of the private appendix text"}')
    assert has_appendix(ctx, json.dumps({'x': 'line of the private appendix text'}).encode())
    assert not has_appendix(ctx, b'nothing')
    print('[PASS] selftest 7/7')


def main(argv):
    if argv[:1] == ['--selftest']:
        return selftest()
    if argv[:1] == ['bundlezip']:
        return print(bundlezip(argv[1], argv[2]))
    if len(argv) < 2:
        raise SystemExit(__doc__)
    cmd, ctx = argv[0], Ctx(argv[1])
    a = argv[2:]
    if cmd == 'redact':
        raw = Path(a[0]).read_bytes()
        pub, n = checked(ctx, raw, a[0])
        Path(a[1]).write_bytes(pub)
        print(n, sha(raw), sha(pub))
    elif cmd == 'judging':
        print(*judging(ctx, a[0], a[1], a[2], a[3]))
    elif cmd == 'generation':
        print(*generation(ctx, a[0], a[1], a[2]))
    elif cmd == 'ladders':
        print(*ladders(ctx, a[0], a[1]))
    elif cmd == 'sens':
        print(*sens(ctx, a[0], a[1], a[2]))
    elif cmd == 'g2headers':
        print(g2headers(ctx, a[0]))
    elif cmd == 'setaside':
        print(setaside(ctx, a[0]))
    elif cmd == 'sweep':
        found = sweep(ctx, a)
        for w, pt in found:
            print(f'[HIT] {pt}\t{w}')
        print(f'{len(found)} hits')
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
