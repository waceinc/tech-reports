#!/usr/bin/env python3
"""TR-2026-06 공개본 변환 (사전 등록 v0.2 §10 가림 규칙, 결과 형식 v1).

결과를 보기 전에 독립 검산과 함께 해시를 고정한다.
내부 모델 표시를 A~L 로 바꾸고, B~L 은 허용 키(화이트리스트)만 남겨 관절 한계 · 최고 속도 · 형상 규모를 역산할
수 있는 항목을 뺀다. A 는 원본 그대로 둔다(표시만 A). 출력은 키 순서로 정렬해 원본의 행 순서(내부 이름순일 수
있다)가 새지 않게 한다. 형식에 없는 키가 있으면 멈춘다.

  python3 TR-06_공개본변환.py <실행 폴더> <공개본 폴더> --map TR-06_모델대응표_비공개.json
  python3 TR-06_공개본변환.py --selftest
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True

RESULT_KEYS = {
    "model", "k", "solver", "speed", "plan_round", "start_deg", "target_deg", "end_deg", "end_over_001",
    "end_label", "converged", "samples", "ik_fail_samples", "ik_fail_causes", "end_pos_err_mm",
    "end_rot_err_deg", "end_iters", "max_step_deg", "max_step_joint", "max_step_index", "max_step_s",
    "j4_travel_deg", "j6_travel_deg", "min_manipulability", "max_speed_ratio", "findings", "verdict",
    "mismatch", "type", "plan_hash",
}
# B~L 에 그대로 남기는 키. 나머지는 아래 mask_row 가 바꾸거나 뺀다.
RESULT_KEEP_BL = {
    "k", "solver", "speed", "plan_round", "start_deg", "target_deg", "end_over_001", "end_label", "converged",
    "end_pos_err_mm", "end_rot_err_deg", "end_iters", "max_step_joint", "max_step_s", "j4_travel_deg",
    "j6_travel_deg", "findings", "verdict", "mismatch", "type", "plan_hash",
}
E1_KEYS = {"model", "joint", "m", "max_speed_ratio", "block_strict", "block_margin", "start_deg", "distance_deg",
           "duration_s", "accel_deg_s2"}
E1_KEEP_BL = ("joint", "m", "block_strict", "block_margin")
LABEL_KEEP = ("wrist", "elbow", "shoulder", "turn4", "turn6")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_map(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    m = {e["internal"]: e["label"] for e in doc["models"]}
    if sorted(m.values()) != [chr(c) for c in range(ord("A"), ord("L") + 1)]:
        raise SystemExit("대응표의 표시가 A~L 이 아니다")
    return m


def mask_row(row, label, manip_max):
    unknown = set(row) - RESULT_KEYS
    if unknown:
        raise SystemExit(f"results.jsonl 에 형식에 없는 키 {sorted(unknown)} — 변환 중단")
    if label == "A":
        return dict(row, model="A")
    out = {k: row[k] for k in RESULT_KEEP_BL}
    out["model"] = label
    out["ik_fail_any"] = row["ik_fail_samples"] > 0
    out["ik_fail_cause_any"] = {k: v > 0 for k, v in row["ik_fail_causes"].items()}
    out["max_speed_ratio"] = round(row["max_speed_ratio"], 2)
    mx = manip_max.get(row["model"]) or 0.0
    out["min_manipulability"] = round(row["min_manipulability"] / mx, 4) if mx > 0 else None
    return out


def write_jsonl(path, rows, key):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in sorted(rows, key=key):
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def convert(run_dir, out_dir, mapping):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(run_dir, "results.jsonl"), encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    unknown = sorted({r["model"] for r in rows} - set(mapping))
    if unknown:
        raise SystemExit(f"대응표에 없는 모델 {len(unknown)}개")
    manip_max = {}
    for r in rows:
        manip_max[r["model"]] = max(manip_max.get(r["model"], 0.0), r["min_manipulability"])
    out = [mask_row(r, mapping[r["model"]], manip_max) for r in rows]
    write_jsonl(os.path.join(out_dir, "results.jsonl"), out,
                key=lambda r: (r["model"], r["k"], r["solver"], r["speed"], r["plan_round"]))

    with open(os.path.join(run_dir, "labels.json"), encoding="utf-8") as f:
        labels = json.load(f)
    pub = {"schema": labels["schema"], "method": labels.get("method"), "labels": []}
    for e in labels["labels"]:
        pub["labels"].append({"model": mapping[e["model"]], "k": e["k"],
                              "start": {k: e["start"][k] for k in LABEL_KEEP},
                              "target": {k: e["target"][k] for k in LABEL_KEEP}})
    pub["labels"].sort(key=lambda e: (e["model"], e["k"]))
    with open(os.path.join(out_dir, "labels.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(pub, f, ensure_ascii=False, indent=1, sort_keys=True)

    e1p = os.path.join(run_dir, "e1.jsonl")
    if os.path.exists(e1p):
        e1 = []
        with open(e1p, encoding="utf-8") as f:
            for l in f:
                if not l.strip():
                    continue
                r = json.loads(l)
                if set(r) - E1_KEYS:
                    raise SystemExit(f"e1.jsonl 에 형식에 없는 키 {sorted(set(r) - E1_KEYS)} — 변환 중단")
                lab = mapping[r["model"]]
                e1.append(dict(r, model="A") if lab == "A" else dict({k: r[k] for k in E1_KEEP_BL}, model=lab))
        write_jsonl(os.path.join(out_dir, "e1.jsonl"), e1, key=lambda r: (r["model"], r["joint"], r["m"]))

    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as f:
        run = json.load(f)
    run["original_sha256"] = {n: sha256(os.path.join(run_dir, n))
                              for n in ("results.jsonl", "labels.json", "e1.jsonl", "summary.json", "precheck.json")
                              if os.path.exists(os.path.join(run_dir, n))}
    run.pop("labels_sha256", None)
    with open(os.path.join(out_dir, "run.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(run, f, ensure_ascii=False, indent=1, sort_keys=True)
    for n in ("summary.json", "precheck.json"):
        if os.path.exists(os.path.join(run_dir, n)):
            shutil.copyfile(os.path.join(run_dir, n), os.path.join(out_dir, n))
    leak_check(out_dir, mapping)


def leak_check(out_dir, mapping):
    """공개본 어디에도 내부 모델 표시가 남지 않았는지, B~L 행에 허용 키만 있는지 본다."""
    internal = [n.lower() for n in mapping if mapping[n] != "A"]
    for name in os.listdir(out_dir):
        with open(os.path.join(out_dir, name), encoding="utf-8") as f:
            text = f.read().lower()
        for n in internal:
            if n in text:
                raise SystemExit(f"[FAIL] 공개본 {name} 에 내부 모델 표시가 남았다")
    allowed = RESULT_KEEP_BL | {"model", "ik_fail_any", "ik_fail_cause_any", "max_speed_ratio", "min_manipulability"}
    with open(os.path.join(out_dir, "results.jsonl"), encoding="utf-8") as f:
        for l in f:
            r = json.loads(l)
            if r["model"] != "A" and set(r) - allowed:
                raise SystemExit(f"[FAIL] B~L 행에 허용 밖 키 {sorted(set(r) - allowed)}")


def selftest():
    ok = True

    def expect(cond, msg):
        nonlocal ok
        if not cond:
            print("[FAIL] 자체 시험 —", msg)
            ok = False

    with tempfile.TemporaryDirectory() as tmp:
        run, out = os.path.join(tmp, "run"), os.path.join(tmp, "pub")
        os.makedirs(run)
        names = ["zz-abb-model"] + [f"aa-model-{i:02d}" for i in range(11)]
        mapping = {n: chr(ord("A") + i) for i, n in enumerate(names)}
        base = {"solver": "C0", "speed": "base", "plan_round": 1, "start_deg": [0] * 6, "target_deg": [0] * 6,
                "end_deg": [0, 0, 0, 0, 0, 170.0], "end_over_001": [False] * 5 + [True],
                "end_label": {"wrist": "+", "elbow": "+", "shoulder": "+", "turn4": 0, "turn6": 0},
                "converged": True, "samples": 87, "ik_fail_samples": 0,
                "ik_fail_causes": {"unreachable": 0, "limit": 0, "budget": 0}, "end_pos_err_mm": 0.0,
                "end_rot_err_deg": 0.0, "end_iters": 2, "max_step_deg": 3.5, "max_step_joint": 6,
                "max_step_index": 40, "max_step_s": 0.46, "j4_travel_deg": 0.0, "j6_travel_deg": 170.0,
                "max_speed_ratio": 0.987654, "findings": {}, "verdict": {"V": "block", "T": "allow", "V_cfg": "allow"},
                "mismatch": True, "type": "d", "plan_hash": "h"}
        with open(os.path.join(run, "results.jsonl"), "w") as f:
            for n in names:  # 원본 순서 = 내부 이름 역순
                for k in (1, 0):
                    f.write(json.dumps(dict(base, model=n, k=k, min_manipulability=0.05 * (k + 1))) + "\n")
        lab = {"wrist": "+", "elbow": "+", "shoulder": "+", "turn4": 0, "turn6": 0, "wrist_center_mm": [1, 2, 3]}
        with open(os.path.join(run, "labels.json"), "w") as f:
            json.dump({"schema": "tr06-labels/v1", "labels": [{"model": n, "k": 0, "start": lab, "target": lab}
                                                              for n in names]}, f)
        with open(os.path.join(run, "e1.jsonl"), "w") as f:
            for n in names:
                f.write(json.dumps({"model": n, "joint": 1, "m": 1, "max_speed_ratio": 1.0, "block_strict": False,
                                    "block_margin": False, "start_deg": [0] * 6, "distance_deg": 26.0,
                                    "duration_s": 0.204, "accel_deg_s2": 2500.0}) + "\n")
        with open(os.path.join(run, "run.json"), "w") as f:
            json.dump({"schema": "tr06-run/v1", "labels_sha256": "x"}, f)
        convert(run, out, mapping)
        with open(os.path.join(out, "results.jsonl")) as f:
            rows = [json.loads(l) for l in f]
        expect([r["model"] for r in rows] == sorted(r["model"] for r in rows), "행 정렬")
        a = next(r for r in rows if r["model"] == "A")
        b = [r for r in rows if r["model"] == "B"]
        expect("end_deg" in a and "samples" in a, "A 원본 유지")
        expect(all(k not in b[0] for k in ("end_deg", "max_step_deg", "samples", "max_step_index",
                                            "ik_fail_samples", "ik_fail_causes")), "B 가림")
        expect(b[0]["max_speed_ratio"] == 0.99 and b[0]["ik_fail_any"] is False, "B 변환 값")
        expect(sorted(r["min_manipulability"] for r in b) == [0.5, 1.0], "조작성 비")
        with open(os.path.join(out, "e1.jsonl")) as f:
            e1 = [json.loads(l) for l in f]
        eb = next(r for r in e1 if r["model"] == "B")
        expect(set(eb) == set(E1_KEEP_BL) | {"model"} and "distance_deg" in next(r for r in e1 if r["model"] == "A"),
               "e1 가림")
        with open(os.path.join(out, "labels.json")) as f:
            labs = json.load(f)["labels"]
        expect(all("wrist_center_mm" not in l["start"] for l in labs), "labels 가림")
        with open(os.path.join(out, "run.json")) as f:
            expect("labels_sha256" not in json.load(f), "run.json labels_sha256 제거")
        # 형식에 없는 키는 멈춰야 한다
        with open(os.path.join(run, "results.jsonl"), "a") as f:
            f.write(json.dumps(dict(base, model=names[1], k=5, min_manipulability=0.1, joint_diff=[1] * 6)) + "\n")
        try:
            convert(run, os.path.join(tmp, "pub2"), mapping)
            expect(False, "형식에 없는 키를 통과시킴")
        except SystemExit:
            pass
    print("[PASS] 자체 시험(가짜 결과)" if ok else "[FAIL] 자체 시험")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?")
    ap.add_argument("out_dir", nargs="?")
    ap.add_argument("--map")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.run_dir and a.out_dir and a.map):
        ap.error("실행 폴더 · 공개본 폴더 · --map 이 필요하다")
    convert(a.run_dir, a.out_dir, load_map(a.map))
    print("[PASS] 공개본 변환 · 내부 표시 잔존 0 · B~L 허용 키만")
    return 0


if __name__ == "__main__":
    sys.exit(main())
