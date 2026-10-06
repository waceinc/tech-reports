#!/usr/bin/env python3
"""TR-2026-06 Section 5 tables from the public result files (not pre-registered; written after the results).

  python3 tables.py <public results folder> <input list> <out tables.json>
"""
import collections
import json
import statistics
import sys

SOLVERS = ("C0", "C1", "C2", "C3", "C2z")
GROUPS = ("cross", "noncross")


def undetermined(lab):
    return any(lab[side][key] == "?" for side in ("start", "target") for key in ("wrist", "elbow", "shoulder"))


def main(folder, inputs_path, out_path):
    group = {e["k"]: e["group"] for e in json.load(open(inputs_path, encoding="utf-8"))["inputs"]}
    rows = [json.loads(l) for l in open(f"{folder}/results.jsonl", encoding="utf-8") if l.strip()]
    labels = {(l["model"], l["k"]): l for l in json.load(open(f"{folder}/labels.json", encoding="utf-8"))["labels"]}
    base = lambda s: [r for r in rows if r["solver"] == s and r["speed"] == "base" and r["plan_round"] == 1]
    g = lambda r: group[r["k"]]
    ikf = lambda r: r["ik_fail_samples"] > 0 if "ik_fail_samples" in r else r["ik_fail_any"]
    causes = lambda r: ({k: v > 0 for k, v in r["ik_fail_causes"].items()} if "ik_fail_causes" in r else r["ik_fail_cause_any"])
    t = {}
    # 5.1
    t["5.1"] = {s: {"mismatch": {gg: sum(r["mismatch"] for r in base(s) if g(r) == gg) for gg in GROUPS},
                    "V_allowed": {gg: sum(r["verdict"]["V"] == "allow" for r in base(s) if g(r) == gg) for gg in GROUPS},
                    "n": {gg: sum(1 for r in base(s) if g(r) == gg) for gg in GROUPS},
                    "converged": sum(r["converged"] for r in base(s))} for s in SOLVERS}
    t["5.1_crossing_blocked"] = {s: {"blocked": sum(r["verdict"]["V"] == "block" for r in base(s) if g(r) == "cross"),
                                     "with_joint_speed": sum(r["verdict"]["V"] == "block" and r["findings"]["joint_speed"]["block"] > 0 for r in base(s) if g(r) == "cross"),
                                     "with_ik_failure": sum(r["verdict"]["V"] == "block" and ikf(r) for r in base(s) if g(r) == "cross")} for s in ("C0", "C1", "C3")}
    allowed = {s: sorted([r["model"], r["k"]] for r in base(s) if g(r) == "cross" and r["verdict"]["V"] == "allow") for s in ("C0", "C1", "C3")}
    t["5.1_same_allowed"] = {"same": allowed["C0"] == allowed["C1"] == allowed["C3"],
                             "by_model": dict(collections.Counter(m for m, _ in allowed["C0"]))}
    c0 = base("C0")
    # 5.2 (public files: B-L give "a|d")
    t["5.2_types_public"] = dict(collections.Counter(str(r["type"]) for r in c0 if r["mismatch"]))
    # 5.3
    why = collections.Counter()
    for r in c0:
        if r["mismatch"] and r["verdict"]["T"] == "block":
            if not r["converged"]:
                why["not_converged"] += 1
                why["not_converged_outside_end_pose"] += not (r["end_pos_err_mm"] <= 0.01 and r["end_rot_err_deg"] <= 0.01)
                why["not_converged_with_joint_speed"] += r["findings"]["joint_speed"]["block"] > 0
            else:
                other = sorted(k for k, v in r["findings"].items() if v["block"] > 0 and k != "end_joint_mismatch")
                why["+".join(other)] += 1
    t["5.3_T_block_reasons"] = dict(why)
    half = [r for r in rows if r["solver"] == "C0" and r["speed"] == "half"]
    t["E4_half_speed"] = {"mismatch": sum(r["mismatch"] for r in half), "n": len(half),
                          "miss": sum(r["mismatch"] and r["verdict"]["T"] == "allow" for r in half)}
    # 5.4
    agree = {}
    for (m, k), lab in labels.items():
        a = agree.setdefault(m, collections.Counter())
        if undetermined(lab):
            a["any_label_undetermined"] += 1
            continue
        a[("cross" if group[k] == "cross" else "noncross") + ("_wrist_differ" if lab["start"]["wrist"] != lab["target"]["wrist"] else "_wrist_equal")] += 1
    t["5.4_group_agreement"] = {m: dict(v) for m, v in sorted(agree.items())}
    # 5.5
    pm = {}
    for r in c0:
        d = pm.setdefault(r["model"], {"cross": [0, 0], "noncross": [0, 0], "miss": [0, 0], "types": collections.Counter()})
        d[g(r)][1] += 1
        d[g(r)][0] += r["mismatch"]
        if r["mismatch"]:
            d["miss"][1] += 1
            d["miss"][0] += r["verdict"]["T"] == "allow"
            d["types"][str(r["type"])] += 1
    t["5.5_per_model_C0"] = {m: dict(v, types=dict(v["types"])) for m, v in sorted(pm.items())}
    exc = [[r["model"], r["k"]] for r in c0 if not undetermined(labels[(r["model"], r["k"])])
           and labels[(r["model"], r["k"])]["start"]["wrist"] != labels[(r["model"], r["k"])]["target"]["wrist"] and not r["mismatch"]]
    t["P7a_exceptions_by_model"] = dict(collections.Counter(m for m, _ in exc))
    # 5.6 E5
    t["E5"] = {s: {gg: dict(collections.Counter("/".join(r["verdict"][k] for k in ("V", "T", "V_cfg")) for r in base(s) if g(r) == gg))
                   for gg in GROUPS} for s in SOLVERS}
    e18 = [r for r in c0 if r["verdict"]["V"] == "allow" and r["verdict"]["V_cfg"] == "block"]
    t["E5_C0_vcfg_only_blocks"] = {"n": len(e18), "undetermined": sum(undetermined(labels[(r["model"], r["k"])]) for r in e18)}
    t["E5_C0_misses_vcfg_allowed"] = [[r["model"], r["k"], r["type"]] for r in c0
                                     if r["verdict"]["V"] == "block" and r["verdict"]["T"] == "allow" and r["verdict"]["V_cfg"] == "allow"]
    # 5.7 E6
    e6 = {}
    for s in ("C0", "C1", "C3"):
        cr = [r for r in base(s) if g(r) == "cross"]
        e6[s] = {"s_lt_0.1": sum(r["max_step_s"] < .1 for r in cr), "s_0.1_to_0.9": sum(.1 <= r["max_step_s"] <= .9 for r in cr),
                 "s_gt_0.9": sum(r["max_step_s"] > .9 for r in cr), "median_speed_ratio": statistics.median(r["max_speed_ratio"] for r in cr),
                 "model_A_max_step_deg": [min(r["max_step_deg"] for r in cr if r["model"] == "A"), max(r["max_step_deg"] for r in cr if r["model"] == "A")]}
    t["E6"] = e6
    # E2
    e2 = {}
    for s in SOLVERS:
        c = collections.Counter()
        per = collections.Counter()
        for r in base(s):
            if ikf(r):
                c["moves"] += 1
                per[r["model"]] += 1
                for k, v in causes(r).items():
                    c[k] += bool(v)
        e2[s] = dict(c, by_model=dict(sorted(per.items())))
    t["E2"] = e2
    json.dump(t, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
