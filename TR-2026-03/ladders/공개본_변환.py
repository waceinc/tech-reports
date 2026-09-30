"""TR 공개본 변환 (대표 K4 결정 2026-09-30, 사전 등록 v0.3 고정 입력).

실행본 래더(marker 포함 — plc-simulator 엔진 파서가 필수로 요구)에서 최상위 `marker` 키 한 줄만 지운다.
나머지 바이트는 그대로 둔다. 변환 뒤 JSON 을 다시 읽어 「원본에서 marker 만 뺀 것」과 값·키 순서가 같은지 확인하고,
다르면 멈춘다.
실행: python3 공개본_변환.py <입력 경로> <출력 경로>
      python3 공개본_변환.py --all <출력 폴더>   # plc-twin-lab af9cc40 의 래더 16 개를 git 객체에서 읽어 변환
"""
import hashlib, json, subprocess, sys
from pathlib import Path

LINE = '  "marker": "CONFIDENTIAL — WACE trade secret",\n'.encode()
REPO = '<repos>/plc-twin-lab'
COMMIT = 'af9cc400428d63bcf3aa139bf9f6c1de66765322'


def convert(raw):
    if raw.count(LINE) != 1:
        raise ValueError('marker 줄이 정확히 1 개가 아니다')
    out = raw.replace(LINE, b'', 1)
    before = json.loads(raw)
    after = json.loads(out)
    if 'marker' not in before or before.get('marker') != 'CONFIDENTIAL — WACE trade secret':
        raise ValueError('최상위 marker 가 아니다')
    expected = {k: v for k, v in before.items() if k != 'marker'}
    if after != expected or list(after) != list(expected):
        raise ValueError('marker 외의 내용이 달라졌다')
    return out


def main():
    if sys.argv[1] == '--all':
        outdir = Path(sys.argv[2])
        outdir.mkdir(parents=True, exist_ok=True)
        paths = subprocess.check_output(['git', '-C', REPO, 'ls-tree', '-r', '--name-only', COMMIT, 'ladders/'], text=True).split()
        for rel in sorted(p for p in paths if p.endswith('/program.ldprog.json')):
            raw = subprocess.check_output(['git', '-C', REPO, 'show', f'{COMMIT}:{rel}'])
            out = convert(raw)
            name = '__'.join(rel.split('/')[1:3]) + '.program.ldprog.json'
            (outdir / name).write_bytes(out)
            print(rel, hashlib.sha256(raw).hexdigest(), hashlib.sha256(out).hexdigest())
        return
    raw = Path(sys.argv[1]).read_bytes()
    out = convert(raw)
    Path(sys.argv[2]).write_bytes(out)
    print(hashlib.sha256(raw).hexdigest(), hashlib.sha256(out).hexdigest())


if __name__ == '__main__':
    main()
