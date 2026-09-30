"""TR-2026-02 연결 조건 어댑터 (사전 등록 v0.3 고정 입력).

plc-twin-lab bridge/run.py 를 고치지 않고 불러와, 입력 복원 함수 reconstruct 하나만 바꿔 끼운다.
- history  : 현행 브리지 그대로 — 각 10 ms 스캔 시각의 입력을 edges 로 복원한다.
- boundary : 원래 복원을 먼저 돌려 검사(스키마·에지 시각·최종 I 복원)를 그대로 거친 뒤, 틱 시작 시각 T 의 입력을
             그 틱의 스캔 전부에 넣는다. 틱 끝 값을 앞당겨 쓰는 비인과 변형은 쓰지 않는다.
- 짧은 펄스 : 절대 시각 [t0, t0+w) 동안 한 입력 태그의 값을 공장 값의 반대로 바꿔 PLC 에 준다(공장 모형은 모른다).
             스캔 시각 b 의 값은 t0 <= b < t0+w 이면 반전. boundary 는 그 틱 시작 시각 T 로 판정한다.
             t0 = 주입 틱 시작 + 위상 + 1 ms (에지 시각은 틱 안 1 ms 이상이어야 하므로 +1).
출력(ms)은 두 조건 모두 브리지 그대로 — 마지막 스캔 Q 를 다음 틱에 적용한다.
실행 예: python3 TR-02_연결조건_어댑터.py --mode boundary --variant correct --ticks 1000 --output <plc-twin-lab 안 경로>
         --pulse A.PB.stop_nc:100:5:15  (태그:주입 틱:위상 ms:폭 ms)
"""
import argparse, hashlib, json, sys
from pathlib import Path

BRIDGE = Path('<repos>/plc-twin-lab/bridge')
sys.path.insert(0, str(BRIDGE))
import run as R  # noqa: E402

SELF_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
ORIGINAL = R.reconstruct


def make_reconstruct(mode, pulse):
    def reconstruct(previous, response):
        samples = ORIGINAL(previous, response)          # 원래 검사를 모두 거친다
        dt_ms = round(response['dt_s'] * 1000)
        end_ms = round(response['time_s'] * 1000)
        start_ms = end_ms - dt_ms
        times = [start_ms + b for b in range(10, dt_ms + 1, 10)]
        if mode == 'boundary':
            samples = [dict(previous) for _ in samples]
            times = [start_ms for _ in samples]
        if pulse:
            tag, t0, w = pulse['tag'], pulse['t0_ms'], pulse['width_ms']
            for image, t in zip(samples, times):
                if t0 <= t < t0 + w:
                    image[tag] = not image[tag]
        return samples
    return reconstruct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['history', 'boundary'], required=True)
    ap.add_argument('--variant', choices=['correct', 'late-reverse', 'swapped-sensors'], required=True)
    ap.add_argument('--ticks', type=int, required=True)
    ap.add_argument('--pulse')
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    pulse = None
    if a.pulse:
        tag, tick, phase, width = a.pulse.split(':')
        tick, phase, width = int(tick), int(phase), int(width)
        if tag not in ('A.PB.stop_nc', 'A.PB.estop_nc', 'A.Sen.left', 'A.Sen.right') or not 0 <= phase <= 45 or not 1 <= width <= 49:
            raise ValueError('pulse')
        pulse = dict(tag=tag, tick=tick, phase_ms=phase, width_ms=width, t0_ms=tick * 50 + phase + 1)
    R.reconstruct = make_reconstruct(a.mode, pulse)
    result = R.run('cell-a', a.variant, a.output, ticks=a.ticks)
    side = dict(adapter_sha256=SELF_SHA, mode=a.mode, variant=a.variant, ticks=a.ticks, pulse=pulse,
                trace_hash=result['trace_hash'], status=result['status'])
    (R.local_path(a.output) / 'tr02-adapter.json').write_text(json.dumps(side, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
