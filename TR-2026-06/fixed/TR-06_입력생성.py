#!/usr/bin/env python3
"""TR-2026-06 확인 입력 생성기 (사전 등록 v0.2 §5-1).

정수식만 쓴다. 난수 · 선별 · 재시도 없음. 같은 인자로 실행하면 같은 바이트를 낸다.

  python3 TR-06_입력생성.py                 # 확인 입력 v2 를 표준 출력으로
  python3 TR-06_입력생성.py --dev           # 개발용 입력(k = 100…109) — 실행기 개발 · 시험에만 쓴다
  python3 TR-06_입력생성.py --out 파일      # 파일로 쓴다
  python3 TR-06_입력생성.py --selftest      # 사전 등록의 산술 주장을 확인한다(종료 코드 0/1)
"""
import argparse
import json
import sys

SCHEMA = "tr06-inputs/v2"
CONFIRM_K = range(0, 60)
DEV_K = range(100, 110)


def confirm_pose(k):
    """§5-1 확인 규칙. 시작 관절 값과 이동량(도, 정수)."""
    b = k // 6
    start = [
        -35 + 14 * ((k + b) % 6),
        -50 + 9 * (b % 5),
        26 + 7 * (k % 5),
        -24 + 8 * (k % 7),
        6 + 9 * (k % 6),
        -30 + 12 * (k % 4),
    ]
    move = [
        -10 if k % 2 else 10,
        6 * (((k + b) % 3) - 1),
        -8,
        16,
        -18,
        -24,
    ]
    return start, move


def preliminary_pose(k):
    """예비 관찰 규칙(robot_program_survey.cpp 26~30행, k = 0…19) — 겹침 확인에만 쓴다."""
    start = [
        -40 + 20 * (k % 5),
        -55 + 10 * (k // 5),
        30 + 8 * (k % 4),
        -20 + 10 * (k % 3),
        8 + 12 * (k % 5),
        -20 + 10 * (k % 4),
    ]
    move = [-12 if k % 2 else 12, 8 * ((k % 3) - 1), -10, 20, -15, -20]
    return start, move


def entry(k):
    start, move = confirm_pose(k)
    target = [a + d for a, d in zip(start, move)]
    crossing = (start[4] > 0) != (target[4] > 0)
    return {
        "k": k,
        "group": "cross" if crossing else "noncross",
        "start_deg": start,
        "target_deg": target,
    }


def document(ks, purpose):
    return {
        "schema": SCHEMA,
        "purpose": purpose,
        "rule": "TR-2026-06 사전 등록 v0.2 §5-1, b = floor(k/6)",
        "program": "직선 이동 한 단계, 기본 설정(직선 125 mm/s · 500 mm/s², 회전 45 deg/s · 180 deg/s², 공구 오프셋 0)",
        "inputs": [entry(k) for k in ks],
    }


def dumps(doc):
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def selftest():
    errors = []
    rows = [entry(k) for k in CONFIRM_K]
    pairs = {(tuple(r["start_deg"]), tuple(r["target_deg"])) for r in rows}
    if len(pairs) != 60:
        errors.append(f"서로 다른 입력 {len(pairs)} != 60")
    cross = [r for r in rows if r["group"] == "cross"]
    if [r["k"] for r in cross] != [k for k in CONFIRM_K if k % 6 in (0, 1)]:
        errors.append("교차 묶음이 k mod 6 ∈ {0, 1} 와 다르다")
    if any(0 in (r["start_deg"][4], r["target_deg"][4]) for r in rows):
        errors.append("J5 = 0 인 값이 있다")
    for j, name in ((0, "J1 시작"), (1, "J2 시작"), (2, "J3 시작"), (3, "J4 시작"), (5, "J6 시작")):
        if {r["start_deg"][j] for r in cross} != {r["start_deg"][j] for r in rows}:
            errors.append(f"교차 묶음에 {name} 값이 모두 들어가지 않는다")
    moves2 = {r["target_deg"][1] - r["start_deg"][1] for r in cross}
    if moves2 != {-6, 0, 6}:
        errors.append(f"교차 묶음의 J2 이동량 {sorted(moves2)}")
    pre = set()
    pre_start = set()
    for k in range(20):
        s, d = preliminary_pose(k)
        pre.add((tuple(s), tuple(a + b for a, b in zip(s, d))))
        pre_start.add(tuple(s))
    if pairs & pre or {p[0] for p in pairs} & pre_start:
        errors.append("예비 입력과 겹친다")
    ranges = [(min(min(r["start_deg"][j], r["target_deg"][j]) for r in rows),
               max(max(r["start_deg"][j], r["target_deg"][j]) for r in rows)) for j in range(6)]
    expected = [(-45, 45), (-56, -8), (18, 54), (-24, 40), (-12, 51), (-54, 6)]
    if ranges != expected:
        errors.append(f"값 범위 {ranges} != {expected}")
    dev = {(tuple(entry(k)["start_deg"]), tuple(entry(k)["target_deg"])) for k in DEV_K}
    if dev & pairs:
        errors.append("개발용 입력이 확인 입력과 겹친다")
    if dumps(document(CONFIRM_K, "confirm")) != dumps(document(CONFIRM_K, "confirm")):
        errors.append("두 번 만든 출력이 다르다")
    for e in errors:
        print("[FAIL]", e)
    if not errors:
        print("[PASS] 확인 입력 60개 · 교차 20 · 예비와 겹침 0 · 개발용과 겹침 0 · 같은 바이트")
    return 0 if not errors else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", action="store_true", help="개발용 입력(k = 100…109)")
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    text = dumps(document(DEV_K, "dev-only") if a.dev else document(CONFIRM_K, "confirm"))
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
