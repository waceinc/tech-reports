"""TR-2026-03 실행 1 건 어댑터 — plc-twin-lab bridge/run.py 를 고치지 않고 불러와, 래더 파일 경로만 바꿔 끼운다.

run() 은 래더를 ladders/<셀>/<변종>/program.ldprog.json 에서만 읽는다. 변종 래더는 레포 ladders/ 에 쓰지 않으므로
- PLC 자식(engine.mjs) 명령의 래더 경로를 --ladder 로 바꾸고,
- metadata.json 의 파일 sha256 목록에도 --ladder 파일을 적는다(원본 경로 대신).
run() 의 variant 인자는 'correct' 로 준다 — 태그 선언·태그표 대조는 변종도 원본과 같다(칸만 가로선으로 바뀜).
같은 이유로 run() 의 참조 로직 비교 기록(reference-10ms-differences.json)이 변종에서도 만들어진다. 판정은 하지 않는다.
--ladder 옆에 monitor-map.json 이 있어야 한다(engine.mjs 가 program.ldprog.json 이름 옆에서 읽는다).
실행 예: python3 TR-03_변종실행_어댑터.py --cell cell-b --ladder <경로>/program.ldprog.json --scenario flow-sweep --flow 0.60
         --seed 1 --ticks 1000 --output experiments/S2/runs/<회차>/<이름> --variant-id cell-b-0003
"""
import argparse, hashlib, json, sys
from pathlib import Path

BRIDGE = Path('<repos>/plc-twin-lab/bridge')
sys.path.insert(0, str(BRIDGE))
import run as R  # noqa: E402

SELF_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cell', choices=['cell-a', 'cell-b', 'cell-b-pack'], required=True)
    ap.add_argument('--ladder', type=Path, required=True)
    ap.add_argument('--scenario', required=True)
    ap.add_argument('--seed', type=int, required=True)
    ap.add_argument('--ticks', type=int, required=True)
    ap.add_argument('--flow', type=float)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--variant-id')
    a = ap.parse_args()
    ladder = a.ladder.resolve()
    if ladder.name != 'program.ldprog.json' or not (ladder.parent / 'monitor-map.json').is_file():
        raise ValueError('래더는 <폴더>/program.ldprog.json 이고 옆에 monitor-map.json 이 있어야 한다')
    ladder_sha = hashlib.sha256(ladder.read_bytes()).hexdigest()

    base_child, base_meta = R.Child, R.metadata

    class LadderChild(base_child):
        def __init__(self, args, out, name):
            if name == 'plc':
                if len(args) != 3 or not args[1].endswith('bridge/engine.mjs'):
                    raise RuntimeError(f'예상 밖 PLC 명령 {args}')
                args = [args[0], args[1], str(ladder)]
            super().__init__(args, out, name)

    R.Child = LadderChild
    R.metadata = lambda extctl, program, cell: base_meta(extctl, ladder, cell)
    result = R.run(a.cell, 'correct', a.output, ticks=a.ticks, seed=a.seed, scenario=a.scenario, flow_factor=a.flow)
    side = dict(adapter_sha256=SELF_SHA, cell=a.cell, variant_id=a.variant_id, ladder=str(ladder), ladder_sha256=ladder_sha,
                scenario=a.scenario, seed=a.seed, ticks=a.ticks, flow_factor=a.flow,
                trace_hash=result['trace_hash'], status=result['status'])
    (R.local_path(a.output) / 'tr03-adapter.json').write_text(json.dumps(side, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
