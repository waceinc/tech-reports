"""TR-2026-04 generation isolation (macOS sandbox-exec).

Runs one command so that it cannot read the denied folders (reference ladders, repositories,
result folders) and cannot write outside the work folder and the tool state folders.
Network: 'any' (cloud generators) or 'local' (outbound only to localhost, for the local model client).

  python3 isolate.py --workdir W --deny-read D [--deny-read D2 ...] [--allow-write P ...] [--net any|local] -- CMD ...
  python3 isolate.py --selftest --workdir W --deny-read D --probe-file F
      F must be an existing readable file inside a denied folder (positive control).

Exit codes: command's own code; 5 = sandbox unavailable or self-check failed (command not run).
"""
import argparse, os, platform, shutil, subprocess, sys, tempfile


def profile_text(workdir, deny_read, allow_write, net):
    tmp = [os.path.realpath(tempfile.gettempdir()), '/private/tmp', '/private/var/folders', '/dev']
    writable = [os.path.realpath(p) for p in [workdir] + allow_write] + tmp
    lines = ['(version 1)', '(allow default)']
    for d in deny_read:
        d = os.path.realpath(d)
        lines.append('(deny file-read* (subpath "%s"))' % d)
        lines.append('(deny file-write* (subpath "%s"))' % d)
    lines.append('(deny file-write* (require-all %s))' % ' '.join('(require-not (subpath "%s"))' % p for p in writable))
    if net == 'local':
        lines += ['(deny network-outbound)', '(allow network-outbound (remote ip "localhost:*"))',
                  '(allow network-outbound (remote unix-socket))']
    return '\n'.join(lines) + '\n'


def write_profile(args):
    fd, path = tempfile.mkstemp(prefix='tr04-sandbox-', suffix='.sb')
    with os.fdopen(fd, 'w') as f:
        f.write(profile_text(args.workdir, args.deny_read, args.allow_write, args.net))
    return path


def sh(profile, script):
    cmd = ['/bin/sh', '-c', script] if profile is None else ['sandbox-exec', '-f', profile, '/bin/sh', '-c', script]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60).returncode


def checks(profile, workdir, probe_file):
    """Positive/negative controls. Returns list of (name, ok)."""
    inside = os.path.join(workdir, '.tr04-probe-in')
    outside = os.path.join(os.path.dirname(os.path.realpath(workdir)), '.tr04-probe-out-%d' % os.getpid())
    out = [
        ('control: denied file readable without sandbox', sh(None, "head -c 1 '%s' >/dev/null" % probe_file) == 0),
        ('denied file NOT readable in sandbox', sh(profile, "head -c 1 '%s' >/dev/null" % probe_file) != 0),
        ('denied folder NOT listable in sandbox', sh(profile, "ls '%s' >/dev/null" % os.path.dirname(probe_file)) != 0),
        ('work folder writable in sandbox', sh(profile, "echo x > '%s' && cat '%s' >/dev/null" % (inside, inside)) == 0),
        ('outside work folder NOT writable in sandbox', sh(profile, "echo x > '%s'" % outside) != 0),
    ]
    for p in (inside, outside):
        if os.path.exists(p):
            os.replace(p, p + '.done')  # keep, never delete in shared folders
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workdir', required=True)
    ap.add_argument('--deny-read', action='append', default=[], required=True)
    ap.add_argument('--allow-write', action='append', default=[])
    ap.add_argument('--net', choices=['any', 'local'], default='any')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--probe-file')
    ap.add_argument('cmd', nargs=argparse.REMAINDER)
    a = ap.parse_args()
    if platform.system() != 'Darwin' or not shutil.which('sandbox-exec'):
        print('[FAIL] sandbox-exec unavailable — not running')
        return 5
    os.makedirs(a.workdir, exist_ok=True)
    profile = write_profile(a)
    probe = a.probe_file
    if not probe:
        print('[FAIL] --probe-file (a file inside a denied folder) is required for the pre-run check')
        return 5
    results = checks(profile, a.workdir, probe)
    for name, ok in results:
        print('[PASS]' if ok else '[FAIL]', name)
    if not all(ok for _, ok in results):
        return 5
    if a.selftest:
        return 0
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == '--' else a.cmd
    if not cmd:
        print('[FAIL] no command')
        return 5
    return subprocess.run(['sandbox-exec', '-f', profile] + cmd, cwd=a.workdir).returncode


if __name__ == '__main__':
    sys.exit(main())
