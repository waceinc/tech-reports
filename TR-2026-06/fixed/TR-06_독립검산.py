#!/usr/bin/env python3
"""TR-2026-06 리드 독립 검산 (사전 등록 v0.2 §7 · §9, 결과 형식 v1).

결과를 보기 전에 써서 해시를 고정한다. 실행기의 판정 항목(mismatch · type · verdict · summary)을 믿지 않고
관절 값 · 소견 수 · 라벨에서 다시 계산하며, 소견과 원자료가 서로 맞는지도 대조한다. 실행기 값과 한 건이라도
다르거나 실행 무효 기준에 걸리면 게이트 [FAIL] 로 끝낸다(종료 코드 1).

  python3 TR-06_독립검산.py <실행 폴더> --inputs TR-06_입력목록_v2.json [--json 출력.json]
  python3 TR-06_독립검산.py --selftest

원본과 공개본(run.json 에 original_sha256 이 있음) 모두 읽는다. 공개본 B~L 은 end_deg 가 없어 유형 (a) 와 (d) 를
가를 수 없고, 속도 소견과 풀이 실패 원인의 원자료 대조를 A 에서만 한다.
원리상 막을 수 없는 것: 실행기가 끝 관절 값 · 소견 · 판정 · 라벨을 모두 앞뒤가 맞게 꾸민 경우. 이것은 사전 대조의
비트 일치(precheck.json)와 A 의 재실행이 맡는다.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import sys
import tempfile

sys.dont_write_bytecode = True

TOL_JOINT = 0.01
TOL_POS_MM = 0.01
TOL_ROT_DEG = 0.01
SPEED_MARGIN = 1.0 + 1e-9
EXPECTED_INPUTS_SHA256 = "43da27bf7d0e63d51fedc9341e5555206550f62f73d723f53c832606e0874f8a"
EXPECTED_PRODUCT_COMMIT = "e2dc7a7846a59952fb6c76d63b89137bef5129ab"
SOLVERS = ("C0", "C1", "C2", "C3", "C2z")
ALLOWED = {(s, "base", 1) for s in SOLVERS} | {("C0", "base", 2), ("C0", "half", 1)}
N_MODELS = 12
FINDING_KINDS = {"end_joint_mismatch", "ik_fail", "joint_speed", "joint_accel", "manipulability", "line_deviation"}
LABEL_KEYS = ("wrist", "elbow", "shoulder", "turn4", "turn6")
CFG_KEYS = ("wrist", "elbow", "shoulder")
PRECHECK_KEYS = ("negative", "positive_turn", "positive_wrist")


class Gate:
    def __init__(self):
        self.fails = []
        self.notes = []

    def fail(self, msg):
        self.fails.append(msg)

    def note(self, msg):
        self.notes.append(msg)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def utc(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


# --- 다시 계산하는 판정 -------------------------------------------------------

def group_of(start, target):
    return "cross" if (start[4] > 0) != (target[4] > 0) else "noncross"


def over_flags(row):
    if "end_deg" in row:
        return [abs(e - t) > TOL_JOINT for e, t in zip(row["end_deg"], row["target_deg"])]
    return list(row["end_over_001"])


def ik_failed(row):
    if "ik_fail_samples" in row:
        return row["ik_fail_samples"] > 0
    return bool(row["ik_fail_any"])


def blocks(row, exclude=()):
    return sum(v.get("block", 0) for k, v in row["findings"].items() if k not in exclude)


def verdict_v(row):
    """제품 점검기 그대로 + 풀이 실패 · 미수렴은 차단(§3)."""
    ok = blocks(row) == 0 and not ik_failed(row) and row["converged"]
    return "allow" if ok else "block"


def verdict_t(row):
    ok = (blocks(row, exclude=("end_joint_mismatch",)) == 0 and not ik_failed(row) and row["converged"]
          and row["end_pos_err_mm"] <= TOL_POS_MM and row["end_rot_err_deg"] <= TOL_ROT_DEG)
    return "allow" if ok else "block"


def undetermined(lbl):
    return any(lbl[k] == "?" for k in CFG_KEYS)


def labels_equal(a, b):
    if undetermined(a) or undetermined(b):
        return False
    return all(a[k] == b[k] for k in LABEL_KEYS)


def verdict_vcfg(row, lab):
    return verdict_t(row) if labels_equal(lab["start"], lab["target"]) else "block"


def turn_type_a(row):
    d = [e - t for e, t in zip(row["end_deg"], row["target_deg"])]
    if any(abs(d[j]) > TOL_JOINT for j in (0, 1, 2, 4)):
        return False
    nonzero = False
    for j in (3, 5):
        n = round(d[j] / 360.0)
        if abs(d[j] - 360.0 * n) > TOL_JOINT:
            return False
        nonzero = nonzero or n != 0
    return nonzero


def type_of(row, lab, mismatch):
    if not mismatch:
        return None
    if not row["converged"]:
        return "e"
    end_l, tgt_l = row["end_label"], lab["target"]
    if undetermined(end_l) or undetermined(tgt_l):
        return "x"
    if end_l["elbow"] != tgt_l["elbow"] or end_l["shoulder"] != tgt_l["shoulder"]:
        return "c"
    if end_l["wrist"] != tgt_l["wrist"]:
        return "b"
    if "end_deg" not in row:
        return "a|d"
    return "a" if turn_type_a(row) else "d"


# --- 정수식 판정 -------------------------------------------------------------

def at_least(x, n, num, den):
    return None if n == 0 else den * x >= num * n


def at_most(x, n, num, den):
    return None if n == 0 else den * x <= num * n


def less_than(x, n, num, den):
    return None if n == 0 else den * x < num * n


def word(ok, yes="맞음", no="틀림"):
    return "판정 불가" if ok is None else (yes if ok else no)


# --- 본체 --------------------------------------------------------------------

def check_inputs(inputs_path, gate):
    if sha256(inputs_path) != EXPECTED_INPUTS_SHA256:
        gate.fail("[무효] 입력 목록 sha256 이 고정값과 다르다")
    inputs = read_json(inputs_path)
    if inputs.get("purpose") != "confirm" or sorted(e["k"] for e in inputs["inputs"]) != list(range(60)):
        gate.fail("[무효] 확인 입력(k = 0…59)이 아니다")
    return inputs


def check_run_meta(run_dir, public, gate):
    for name in ("run.json", "labels.json", "results.jsonl", "e1.jsonl", "summary.json", "precheck.json"):
        if not os.path.exists(os.path.join(run_dir, name)):
            gate.fail(f"필수 파일 없음: {name}")
    run = read_json(os.path.join(run_dir, "run.json")) if os.path.exists(os.path.join(run_dir, "run.json")) else {}
    if run.get("inputs_sha256") != EXPECTED_INPUTS_SHA256:
        gate.fail("[무효] run.json 의 inputs_sha256 이 고정값과 다르다")
    if run.get("product_commit") != EXPECTED_PRODUCT_COMMIT:
        gate.fail("[무효] run.json 의 product_commit 이 e2dc7a7 이 아니다")
    if not run.get("runner_commit"):
        gate.fail("run.json 에 runner_commit 이 없다")
    try:
        if not utc(run["labels_written_utc"]) < utc(run["first_plan_utc"]):
            gate.fail("[무효] 라벨을 계획보다 먼저 쓰지 않았다")
    except (KeyError, ValueError):
        gate.fail("[무효] run.json 에 라벨 · 첫 계획 시각이 없거나 읽을 수 없다")
    for flag in ("limits_ok_inputs", "limits_ok_e1"):
        if run.get(flag) is not True:
            gate.fail(f"[무효] run.json 의 {flag} 가 참이 아니다")
    if not public and os.path.exists(os.path.join(run_dir, "labels.json")):
        if sha256(os.path.join(run_dir, "labels.json")) != run.get("labels_sha256"):
            gate.fail("[무효] labels.json sha256 이 run.json 과 다르다")
    pc = os.path.join(run_dir, "precheck.json")
    if os.path.exists(pc):
        pre = read_json(pc)
        for k in PRECHECK_KEYS:
            e = pre.get(k, {})
            if not e or e.get("expect") != e.get("got"):
                gate.fail(f"[무효] 사전 대조 {k}: 기대 {e.get('expect')} · 실제 {e.get('got')}")
        if pre.get("c0_bit_identical") is not True:
            gate.fail("[무효] 사전 대조: C0 다시 푼 값이 제품 계획과 비트 단위로 같지 않다")
    return run


def check_row_raw(key, r, gate):
    """원자료가 있는 행(원본 전부, 공개본 A)에서 소견과 원자료가 맞는지 본다."""
    for f in ("end_pos_err_mm", "end_rot_err_deg", "max_speed_ratio"):
        if not math.isfinite(r[f]):
            gate.fail(f"유한하지 않은 값 {f} {key}")
    if any(not math.isfinite(v) for v in r["end_deg"]):
        gate.fail(f"유한하지 않은 end_deg {key}")
        return
    js = r["findings"].get("joint_speed", {}).get("block", 0) > 0
    if (r["max_speed_ratio"] > SPEED_MARGIN) != js:
        gate.fail(f"속도 비율과 joint_speed 차단이 맞지 않음 {key}")
    if sum(r["ik_fail_causes"].values()) != r["ik_fail_samples"]:
        gate.fail(f"풀이 실패 원인 합 ≠ 풀이 실패 표본 수 {key}")
    ikf = r["findings"].get("ik_fail", {})
    if (r["ik_fail_samples"] > 0) != (ikf.get("warn", 0) + ikf.get("block", 0) > 0):
        gate.fail(f"풀이 실패 표본과 ik_fail 소견이 맞지 않음 {key}")


def check(run_dir, inputs_path, gate):
    inputs = check_inputs(inputs_path, gate)
    by_k = {e["k"]: e for e in inputs["inputs"]}
    run = read_json(os.path.join(run_dir, "run.json")) if os.path.exists(os.path.join(run_dir, "run.json")) else {}
    public = "original_sha256" in run
    check_run_meta(run_dir, public, gate)
    rows = read_jsonl(os.path.join(run_dir, "results.jsonl"))
    labels_doc = read_json(os.path.join(run_dir, "labels.json"))
    labels = {(l["model"], l["k"]): l for l in labels_doc["labels"]}

    models = sorted({r["model"] for r in rows})
    if len(models) != N_MODELS:
        gate.fail(f"[무효] 모델 수 {len(models)} ≠ {N_MODELS}")
    if public and models != [chr(c) for c in range(ord("A"), ord("L") + 1)]:
        gate.fail("공개본 모델 표시가 A~L 이 아니다")

    # 1. 행 구성
    seen = {}
    for r in rows:
        key = (r["model"], r["k"], r["solver"], r["speed"], r["plan_round"])
        if key[2:] not in ALLOWED:
            gate.fail(f"정의 밖의 행 {key}")
        if key in seen:
            gate.fail(f"중복 행 {key}")
        seen[key] = r
    if len(rows) != N_MODELS * 60 * len(ALLOWED):
        gate.fail(f"행 수 {len(rows)} ≠ {N_MODELS * 60 * len(ALLOWED)}")
    for m in models:
        for k in by_k:
            for combo in ALLOWED:
                if (m, k) + combo not in seen:
                    gate.fail(f"빠진 행 {(m, k) + combo}")
            if (m, k) not in labels:
                gate.fail(f"라벨 없음 {(m, k)}")

    # 2. 행마다 다시 계산하고 실행기 값과 대조
    derived = {}
    for key, r in seen.items():
        m, k = r["model"], r["k"]
        inp, lab = by_k.get(k), labels.get((m, k))
        if inp is None or lab is None:
            gate.fail(f"입력 또는 라벨 없음 {key}")
            continue
        if list(r["start_deg"]) != inp["start_deg"] or list(r["target_deg"]) != inp["target_deg"]:
            gate.fail(f"입력 값 불일치 {key}")
        for f in r["findings"]:
            if f not in FINDING_KINDS and not f.startswith("other_"):
                gate.fail(f"형식에 없는 소견 이름 {f} {key}")
        if "end_deg" in r:
            check_row_raw(key, r, gate)
        flags = over_flags(r)
        if flags != list(r["end_over_001"]):
            gate.fail(f"end_over_001 이 end_deg 와 다름 {key}")
        mism = any(flags)
        if mism != (r["findings"].get("end_joint_mismatch", {}).get("block", 0) > 0):
            gate.fail(f"끝 불일치와 end_joint_mismatch 차단이 맞지 않음 {key}")
        d = {"group": group_of(inp["start_deg"], inp["target_deg"]), "mismatch": mism,
             "V": verdict_v(r), "T": verdict_t(r), "V_cfg": verdict_vcfg(r, lab),
             "type": type_of(r, lab, mism), "converged": r["converged"]}
        if d["group"] != inp["group"]:
            gate.fail(f"입력 목록의 묶음 표시가 J5 부호와 다름 k={k}")
        if r["mismatch"] != mism:
            gate.fail(f"mismatch 불일치 {key}: 실행기 {r['mismatch']} · 검산 {mism}")
        for v in ("V", "T", "V_cfg"):
            if r["verdict"][v] != d[v]:
                gate.fail(f"{v} 불일치 {key}: 실행기 {r['verdict'][v]} · 검산 {d[v]}")
        if d["type"] == "a|d":
            if r["type"] not in ("a", "d"):
                gate.fail(f"type 불일치 {key}: 실행기 {r['type']} · 검산 a 또는 d")
        elif r["type"] != d["type"]:
            gate.fail(f"type 불일치 {key}: 실행기 {r['type']} · 검산 {d['type']}")
        derived[key] = d

    # 3. 실행 무효 기준(§9)
    for m in models:
        for k in by_k:
            a, b = seen.get((m, k, "C0", "base", 1)), seen.get((m, k, "C0", "base", 2))
            if a and b:
                strip = lambda x: {kk: vv for kk, vv in x.items() if kk != "plan_round"}
                if strip(a) != strip(b):
                    gate.fail(f"[무효] C0 2회 계획이 같지 않음 {(m, k)}")
    for key, d in derived.items():
        r = seen[key]
        if key[2] in ("C1", "C3"):
            if d["mismatch"]:
                gate.fail(f"[무효] {key[2]} 끝 불일치 — 구성상 0 이어야 함 {key}")
            tl = labels[(key[0], key[1])]["target"]
            if not undetermined(tl) and any(r["end_label"][kk] != tl[kk] for kk in LABEL_KEYS):
                gate.fail(f"[무효] {key[2]} 끝 라벨이 목표 라벨과 다름 {key}")
        if key[2] == "C0" and d["mismatch"] and r["converged"]:
            if not (r["end_pos_err_mm"] <= TOL_POS_MM and r["end_rot_err_deg"] <= TOL_ROT_DEG):
                gate.fail(f"[무효] 수렴한 불일치 건이 끝 자세 기준을 통과하지 못함 {key}")

    # 4. §7 분자/분모 — 기본 속도 · 1회차만
    def sel(solver, group=None, converged_only=False):
        return [(key, d) for key, d in derived.items()
                if key[2] == solver and key[3] == "base" and key[4] == 1
                and (group is None or d["group"] == group) and (not converged_only or d["converged"])]

    def predictions(conv_only):
        c0x, c0n = sel("C0", "cross", conv_only), sel("C0", "noncross", conv_only)
        xc, nc = sum(d["mismatch"] for _, d in c0x), len(c0x)
        xn, nn = sum(d["mismatch"] for _, d in c0n), len(c0n)
        c0m = [d for _, d in sel("C0", None, conv_only) if d["mismatch"]]
        miss, nm = sum(d["T"] == "allow" for d in c0m), len(c0m)
        c1x, c3x = sel("C1", "cross", conv_only), sel("C3", "cross", conv_only)
        p5x = sum(d["V"] == "allow" for _, d in c1x)
        p6x = sum(d["V"] == "allow" for _, d in c3x)
        wrist_diff, all_same, excluded = [], [], 0
        for key, d in sel("C0", None, conv_only):
            lab = labels[(key[0], key[1])]
            if undetermined(lab["start"]) or undetermined(lab["target"]):
                excluded += 1
                continue
            if lab["start"]["wrist"] != lab["target"]["wrist"]:
                wrist_diff.append(d)
            if labels_equal(lab["start"], lab["target"]):
                all_same.append(d)
        p7a, p7b = sum(d["mismatch"] for d in wrist_diff), sum(d["mismatch"] for d in all_same)
        f3 = {}
        for s in ("C1", "C2", "C3"):
            rs = sel(s, "cross", conv_only)
            x, n = sum((not d["mismatch"]) and d["V"] == "allow" for _, d in rs), len(rs)
            f3[s] = {"x": x, "n": n, "verdict": word(None if n == 0 else 2 * x >= n, "성립", "불성립")}
        f1_ok = None if not (nc and nn) else 10 * (xc * nn - xn * nc) < 3 * nc * nn
        f3_words = [v["verdict"] for v in f3.values()]
        f3_v = "성립" if "성립" in f3_words else ("판정 불가" if "판정 불가" in f3_words else "불성립")
        pred = {
            "P1": {"x": xc, "n": nc, "verdict": word(at_least(xc, nc, 4, 5))},
            "P2": {"x": xn, "n": nn, "verdict": word(at_most(xn, nn, 1, 5))},
            "P3": {"x": miss, "n": nm, "verdict": word(at_least(miss, nm, 3, 10))},
            "P5": {"x": p5x, "n": len(c1x), "verdict": word(at_most(p5x, len(c1x), 1, 5))},
            "P6": {"x": p6x, "n": len(c3x), "verdict": word(at_most(p6x, len(c3x), 1, 5))},
            "P7a": {"x": p7a, "n": len(wrist_diff), "verdict": word(at_least(p7a, len(wrist_diff), 19, 20))},
            "P7b": {"x": p7b, "n": len(all_same), "verdict": word(at_most(p7b, len(all_same), 1, 20))},
            "F1": {"x_cross": xc, "n_cross": nc, "x_noncross": xn, "n_noncross": nn,
                   "verdict": word(f1_ok, "성립", "불성립")},
            "F2": {"x": miss, "n": nm, "verdict": word(less_than(miss, nm, 1, 10), "성립", "불성립")},
            "F3": {"by_solver": f3, "verdict": f3_v},
        }
        p7 = [pred["P7a"]["verdict"], pred["P7b"]["verdict"]]
        p7v = "틀림" if "틀림" in p7 else ("판정 불가" if "판정 불가" in p7 else "맞음")
        pred["P7"] = {"verdict": p7v, "excluded_x": excluded}
        return pred

    pred = predictions(False)
    sensitivity = predictions(True)

    # 5. 실행기 summary 와 대조(항목 전체가 같아야 한다)
    sp = os.path.join(run_dir, "summary.json")
    if os.path.exists(sp):
        theirs = read_json(sp).get("predictions", {})
        for name, mine in pred.items():
            if theirs.get(name) != mine:
                gate.fail(f"summary {name}: 실행기 {theirs.get(name)} · 검산 {mine}")
        for name in theirs:
            if name not in pred:
                gate.fail(f"summary 에 정의 밖 항목 {name}")

    # 6. E1
    e1 = None
    e1p = os.path.join(run_dir, "e1.jsonl")
    if os.path.exists(e1p):
        e1rows = read_jsonl(e1p)
        keys = {(r["model"], r["joint"], r["m"]) for r in e1rows}
        if len(e1rows) != N_MODELS * 6 * 40 or len(keys) != len(e1rows) \
                or {r["m"] for r in e1rows} != set(range(1, 41)) or {r["joint"] for r in e1rows} != set(range(1, 7)):
            gate.fail("e1.jsonl 구성이 12 × 6 × 40 이 아니다")
        for r in e1rows:
            if "distance_deg" in r:
                if not math.isfinite(r["max_speed_ratio"]):
                    gate.fail(f"e1 유한하지 않은 비율 {(r['model'], r['joint'], r['m'])}")
                elif (r["max_speed_ratio"] > 1.0) != r["block_strict"] or \
                        (r["max_speed_ratio"] > SPEED_MARGIN) != r["block_margin"]:
                    gate.fail(f"e1 차단 표시가 비율과 다름 {(r['model'], r['joint'], r['m'])}")
        e1 = {"n": len(e1rows), "block_strict": sum(r["block_strict"] for r in e1rows),
              "block_margin": sum(r["block_margin"] for r in e1rows)}

    types = {}
    for key, d in derived.items():
        if key[3] == "base" and key[4] == 1 and d["mismatch"]:
            t = types.setdefault(key[2], {})
            t[str(d["type"])] = t.get(str(d["type"]), 0) + 1
    return {"public": public, "models": models, "predictions": pred,
            "sensitivity_converged_only": sensitivity, "types_by_solver": types, "e1": e1}


def report(result, gate):
    print("TR-2026-06 독립 검산", "(공개본)" if result["public"] else "(원본)")
    for name, p in result["predictions"].items():
        if "x" in p:
            print(f"  {name}: {p['x']}/{p['n']} → {p['verdict']}")
        elif name == "F1":
            print(f"  F1: 교차 {p['x_cross']}/{p['n_cross']} · 비교차 {p['x_noncross']}/{p['n_noncross']} → {p['verdict']}")
        elif name == "F3":
            print("  F3:", {s: f"{v['x']}/{v['n']}" for s, v in p["by_solver"].items()}, "→", p["verdict"])
        else:
            print(f"  {name}: {p['verdict']} (판정 불가 라벨로 뺀 건 {p['excluded_x']})")
    print("  유형:", json.dumps(result["types_by_solver"], ensure_ascii=False, sort_keys=True))
    s = result["sensitivity_converged_only"]
    print("  민감도(수렴 건만): " + " · ".join(f"{n} {s[n]['x']}/{s[n]['n']}" for n in ("P1", "P2", "P3")))
    if result["e1"]:
        print("  E1:", result["e1"])
    for n in gate.notes:
        print("  [참고]", n)
    for f in gate.fails[:50]:
        print("  [FAIL]", f)
    if len(gate.fails) > 50:
        print(f"  … [FAIL] {len(gate.fails) - 50}건 더")
    print("게이트:", "[PASS]" if not gate.fails else f"[FAIL] {len(gate.fails)}건")


# --- 자체 시험(가짜 결과로 규칙만 확인 — 실험 결과가 아니다) ------------------------

def _load(here, name, mod):
    import importlib.util
    spec = importlib.util.spec_from_file_location(mod, os.path.join(here, name))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fake_run(tmp, inputs_path):
    """12모델 가짜 실행: 교차 = 손목 뒤집힘(b), 모델 1 은 회전수(a), 모델 2 는 수치 차이(d),
    모델 3 의 k=2 는 미수렴(e), 모델 4 의 k=3 은 목표 라벨 판정 불가(x)."""
    L = lambda w: {"wrist": w, "elbow": "+", "shoulder": "+", "turn4": 0, "turn6": 0}
    inputs = read_json(inputs_path)
    models = [f"model-{i:02d}" for i in range(N_MODELS)]
    labels, rows, e1 = [], [], []
    for mi, m in enumerate(models):
        for e in inputs["inputs"]:
            k, s, t = e["k"], e["start_deg"], e["target_deg"]
            ws, wt = ("+" if s[4] > 0 else "-"), ("+" if t[4] > 0 else "-")
            tl = L("?") if (mi == 4 and k == 3) else L(wt)
            labels.append({"model": m, "k": k, "start": L(ws), "target": tl})
            for solver, speed, rnd in sorted(ALLOWED):
                end = [float(v) for v in t]
                endl = dict(tl)
                conv, ikf, perr = True, 0, 0.0
                ratio = 0.5
                if solver in ("C0", "C2", "C2z"):
                    if ws != wt:
                        end[3] += 180.0
                        end[4] = -end[4]
                        end[5] += 180.0
                        endl = L(ws)
                    elif mi == 1 and k % 6 == 2:
                        end[5] += 360.0
                    elif mi == 2 and k % 6 == 3:
                        end[0] += 0.5
                    elif mi == 3 and k == 2:
                        end[0] += 3.0
                        conv, ikf, perr = False, 2, 5.0
                    elif mi == 4 and k == 3:
                        end[0] += 0.5
                if solver in ("C1", "C3") and ws != wt:
                    ratio = 1.5
                flags = [abs(a - b) > TOL_JOINT for a, b in zip(end, t)]
                find = {"end_joint_mismatch": {"warn": 0, "block": sum(flags)},
                        "ik_fail": {"warn": 0, "block": 1 if ikf else 0},
                        "joint_speed": {"warn": 0, "block": 1 if ratio > SPEED_MARGIN else 0}}
                row = {"model": m, "k": k, "solver": solver, "speed": speed, "plan_round": rnd,
                       "start_deg": s, "target_deg": t, "end_deg": end, "end_over_001": flags,
                       "end_label": endl, "converged": conv, "samples": 100, "ik_fail_samples": ikf,
                       "ik_fail_causes": {"unreachable": ikf, "limit": 0, "budget": 0},
                       "end_pos_err_mm": perr, "end_rot_err_deg": 0.0, "end_iters": 3,
                       "max_step_deg": 1.0, "max_step_joint": 6, "max_step_index": 5, "max_step_s": 0.05,
                       "j4_travel_deg": 16.0, "j6_travel_deg": 24.0, "min_manipulability": 0.1 + 0.001 * k,
                       "max_speed_ratio": ratio, "findings": find, "plan_hash": hashlib.sha256(f"{m}|{k}|{solver}|{speed}".encode()).hexdigest()}
                lab = labels[-1]
                row["verdict"] = {"V": verdict_v(row), "T": verdict_t(row), "V_cfg": verdict_vcfg(row, lab)}
                row["mismatch"] = any(flags)
                row["type"] = type_of(row, lab, any(flags))
                rows.append(row)
        for j in range(1, 7):
            for mm in range(1, 41):
                r = 1.0000000000001563 if mm % 2 == 0 else 0.99
                e1.append({"model": m, "joint": j, "m": mm, "max_speed_ratio": r, "block_strict": r > 1.0,
                           "block_margin": r > SPEED_MARGIN, "start_deg": [0, -35, 55, 0, 35, 0],
                           "distance_deg": 10.0 + mm, "duration_s": 0.2, "accel_deg_s2": 1000.0})
    with open(os.path.join(tmp, "results.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(tmp, "e1.jsonl"), "w") as f:
        for r in e1:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(tmp, "labels.json"), "w") as f:
        json.dump({"schema": "tr06-labels/v1", "method": "가짜", "labels": labels}, f)
    with open(os.path.join(tmp, "precheck.json"), "w") as f:
        json.dump({"negative": {"expect": "none", "got": "none"}, "positive_turn": {"expect": "a", "got": "a"},
                   "positive_wrist": {"expect": "b", "got": "b"}, "c0_bit_identical": True}, f)
    with open(os.path.join(tmp, "run.json"), "w") as f:
        json.dump({"schema": "tr06-run/v1", "product_commit": EXPECTED_PRODUCT_COMMIT, "runner_commit": "x" * 40,
                   "inputs_sha256": EXPECTED_INPUTS_SHA256,
                   "labels_sha256": sha256(os.path.join(tmp, "labels.json")),
                   "labels_written_utc": "2026-01-01T00:00:00Z", "first_plan_utc": "2026-01-01T00:00:01+00:00",
                   "limits_ok_inputs": True, "limits_ok_e1": True}, f)
    res = check(tmp, inputs_path, Gate())  # 실행기 summary 를 흉내 낸다
    with open(os.path.join(tmp, "summary.json"), "w") as f:
        json.dump({"schema": "tr06-summary/v1", "predictions": res["predictions"]}, f, ensure_ascii=False)
    return models


def selftest():
    here = os.path.dirname(os.path.abspath(__file__))
    gen = _load(here, "TR-06_입력생성.py", "gen")
    conv = _load(here, "TR-06_공개본변환.py", "conv")
    ok = True

    def expect(cond, msg):
        nonlocal ok
        if not cond:
            print("[FAIL] 자체 시험 —", msg)
            ok = False

    with tempfile.TemporaryDirectory() as tmp:
        ip = os.path.join(tmp, "inputs.json")
        with open(ip, "w", encoding="utf-8", newline="\n") as f:
            f.write(gen.dumps(gen.document(gen.CONFIRM_K, "confirm")))

        def fresh(name):
            d = os.path.join(tmp, name)
            os.makedirs(d)
            return d, fake_run(d, ip)

        run, models = fresh("clean")
        g = Gate()
        res = check(run, ip, g)
        p = res["predictions"]
        want = {"P1": (240, 240, "맞음"), "P2": (22, 480, "맞음"), "P3": (261, 262, "맞음"),
                "P5": (0, 240, "맞음"), "P6": (0, 240, "맞음"), "P7a": (240, 240, "맞음"), "P7b": (21, 479, "맞음")}
        for name, (x, n, v) in want.items():
            expect((p[name]["x"], p[name]["n"], p[name]["verdict"]) == (x, n, v), f"{name} {p[name]}")
        expect(p["P7"] == {"verdict": "맞음", "excluded_x": 1}, f"P7 {p['P7']}")
        expect(p["F1"]["verdict"] == "불성립" and p["F2"]["verdict"] == "불성립" and p["F3"]["verdict"] == "불성립",
               "F 판정")
        expect(res["types_by_solver"].get("C0") == {"a": 10, "b": 240, "d": 10, "e": 1, "x": 1},
               f"유형 {res['types_by_solver'].get('C0')}")
        expect(res["sensitivity_converged_only"]["P2"]["x"] == 21, "민감도")
        expect(res["e1"] == {"n": 2880, "block_strict": 1440, "block_margin": 0}, f"E1 {res['e1']}")
        expect(not g.fails, f"깨끗한 가짜 결과에서 게이트 실패 {g.fails[:3]}")

        # 공개본 변환 → 검산
        mp = {m: chr(ord("A") + i) for i, m in enumerate(models)}
        pub = os.path.join(tmp, "pub")
        conv.convert(run, pub, mp)
        g = Gate()
        rp = check(pub, ip, g)
        expect(not g.fails, f"공개본 검산 실패 {g.fails[:3]}")
        expect(rp["predictions"] == res["predictions"], "공개본과 원본의 §7 값이 다르다")
        expect(rp["public"] and "a|d" in rp["types_by_solver"]["C0"], f"공개본 유형 {rp['types_by_solver']}")

        # 위조 · 무효 경우 — 각각 잡아야 한다
        def tamper(name, fn, needle):
            d, _ = fresh(name)
            fn(d)
            g = Gate()
            try:
                check(d, ip, g)
            except (KeyError, ValueError, TypeError) as e:
                g.fail(f"예외 {e}")
            expect(any(needle in x for x in g.fails), f"{name} 을 잡지 못함 {g.fails[:2]}")

        def edit_rows(d, fn):
            p_ = os.path.join(d, "results.jsonl")
            rs = read_jsonl(p_)
            fn(rs)
            with open(p_, "w") as f:
                for r in rs:
                    f.write(json.dumps(r) + "\n")

        def edit_json(d, name, fn):
            p_ = os.path.join(d, name)
            s = read_json(p_)
            fn(s)
            with open(p_, "w") as f:
                json.dump(s, f, ensure_ascii=False)

        def drop_finding(d):
            def f(rs):
                r = next(r for r in rs if r["mismatch"] and r["solver"] == "C0")
                r["findings"]["end_joint_mismatch"]["block"] = 0
                r["verdict"]["V"] = "allow"
            edit_rows(d, f)
        tamper("소견 삭제 + V 위조", drop_finding, "end_joint_mismatch 차단이 맞지 않음")

        def ik_warn(d):
            def f(rs):
                r = next(r for r in rs if r["ik_fail_samples"] > 0)
                r["findings"]["ik_fail"] = {"warn": 1, "block": 0}
                r["verdict"]["V"] = "allow"
            edit_rows(d, f)
        tamper("풀이 실패를 경고로", ik_warn, "V 불일치")

        def nan_end(d):
            def f(rs):
                next(r for r in rs if r["mismatch"])["end_deg"][0] = float("nan")
            edit_rows(d, f)
        tamper("NaN", nan_end, "유한하지 않은")

        tamper("정의 밖 행", lambda d: edit_rows(d, lambda rs: rs.append(dict(rs[0], solver="C1", speed="half"))),
               "정의 밖의 행")
        tamper("모델 11개", lambda d: edit_rows(
            d, lambda rs: rs.__setitem__(slice(None), [r for r in rs if r["model"] != "model-11"])), "모델 수")
        tamper("입력 해시", lambda d: edit_json(d, "run.json", lambda s: s.update(inputs_sha256="deadbeef")),
               "inputs_sha256")
        tamper("summary 없음", lambda d: os.remove(os.path.join(d, "summary.json")), "필수 파일 없음")
        tamper("summary 위조", lambda d: edit_json(
            d, "summary.json", lambda s: s["predictions"]["P3"].update(x=s["predictions"]["P3"]["x"] + 1)),
            "summary P3")
        tamper("사전 대조 실패", lambda d: edit_json(
            d, "precheck.json", lambda s: s["positive_wrist"].update(got="none")), "사전 대조")

        def c1_mismatch(d):
            def f(rs):
                r = next(r for r in rs if r["solver"] == "C1")
                r["end_deg"][0] += 1.0
                r["end_over_001"][0] = True
                r["mismatch"] = True
                r["findings"]["end_joint_mismatch"]["block"] = 1
                r["verdict"]["V"] = "block"
            edit_rows(d, f)
        tamper("C1 끝 불일치", c1_mismatch, "구성상 0")

        dev = os.path.join(tmp, "dev.json")
        with open(dev, "w", encoding="utf-8", newline="\n") as f:
            f.write(gen.dumps(gen.document(gen.DEV_K, "dev-only")))
        g = Gate()
        try:
            check(run, dev, g)
        except Exception as e:  # 개발용 입력은 어떤 식으로든 실패해야 한다
            g.fail(str(e))
        expect(any("고정값" in x or "확인 입력" in x for x in g.fails), "개발용 입력을 잡지 못함")

    # 경계값 정수식
    expect(at_least(192, 240, 4, 5) is True and at_least(191, 240, 4, 5) is False, "P1 경계")
    expect(at_most(96, 480, 1, 5) is True and at_most(97, 480, 1, 5) is False, "P2 경계")
    expect(at_least(3, 10, 3, 10) is True and at_least(2, 10, 3, 10) is False, "P3 경계")
    expect(at_least(19, 20, 19, 20) is True and at_most(1, 20, 1, 20) is True and at_most(2, 20, 1, 20) is False,
           "P7 경계")
    expect(less_than(9, 100, 1, 10) is True and less_than(10, 100, 1, 10) is False, "F2 경계")
    f1 = lambda xc, xn: 10 * (xc * 480 - xn * 240) < 3 * 240 * 480  # 30 %p 미만이면 성립
    expect(f1(71, 0) and not f1(72, 0) and f1(73, 3) and not f1(73, 2), "F1 경계")
    r = {"end_deg": [0, 0, 0, 360.0, 0, -720.0], "target_deg": [0] * 6}
    r2 = {"end_deg": [0, 0, 0, 0, 0, 5.0], "target_deg": [0] * 6}
    expect(turn_type_a(r) and not turn_type_a(r2), "유형 (a) 판정식")
    print("[PASS] 자체 시험(가짜 결과 — 실험 결과 아님)" if ok else "[FAIL] 자체 시험")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?")
    ap.add_argument("--inputs")
    ap.add_argument("--json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.run_dir or not a.inputs:
        ap.error("실행 폴더와 --inputs 가 필요하다")
    gate = Gate()
    result = check(a.run_dir, a.inputs, gate)
    report(result, gate)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"result": result, "fails": gate.fails, "notes": gate.notes}, f, ensure_ascii=False, indent=1)
    return 0 if not gate.fails else 1


if __name__ == "__main__":
    sys.exit(main())
