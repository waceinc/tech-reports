#!/usr/bin/env python3
"""Figure 1 of TR-2026-05 from the public result files.

Usage: python3 figure1.py <results dir> <out.png>
Reads results/results.jsonl and results/runs/*.json (per-run digests). Needs matplotlib.
Left: correct-ladder verdict of sort cell B(3i) `normal` per batch under F, M0, M1.
Right: M0 verdict of the same runs under the eight P8 settings (belt settings: M0; F was [PASS] in all 24).
Each failed cell is labelled with the first-lock FaultCode (and, on the left, the tick).
"""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

res_dir, out = sys.argv[1], sys.argv[2]
rows = [json.loads(l) for l in open(os.path.join(res_dir, "results.jsonl"), encoding="utf-8") if l.strip()]

def digest(run_id):
    with open(os.path.join(res_dir, "runs", run_id + ".json"), encoding="utf-8") as f:
        return json.load(f)

main = [r for r in rows if r["group"] == "main" and r["cell"] == "cell-b" and r["variant"] == "correct" and r["scenario"] == "normal"]
batches = sorted({(r["bin"], r["seed"]) for r in main}, key=lambda b: (b[0], rows.index(next(x for x in main if x["seed"] == b[1]))))
conds = ["F", "M0", "M1"]
settings = ["transition_mu_0.5", "transition_mu_1.5", "wall_friction_0.3", "chute_x_force_off",
            "friction_0.7", "friction_1.3", "belt_0.95", "belt_1.05"]
set_labels = ["arc μ\n×0.5", "arc μ\n×1.5", "wall μ\n0.3", "chute x\nforce off",
              "friction\n×0.7", "friction\n×1.3", "belt\n×0.95", "belt\n×1.05"]

def cell(run_id, with_tick):
    d = digest(run_id)
    if d["status"] == "[PASS]":
        return "PASS", None
    fl = d.get("first_lock")
    if not fl:
        return "FAIL", "FAIL"
    lab = f"FC {fl['fault_code']}"
    if with_tick:
        lab += f"\nt {fl['tick']}"
    return "FAIL", lab

SURF, INK, INK2, PASSF, FAILF = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0", "#d03b3b"
fig = plt.figure(figsize=(12, 6.8), facecolor=SURF)
gs = fig.add_gridspec(1, 2, width_ratios=[3, 8], wspace=0.08, left=0.17, right=0.99, top=0.80, bottom=0.03)
axes = [fig.add_subplot(gs[0]), fig.add_subplot(gs[1])]

def draw(ax, ncols, getter, col_labels, title):
    ax.set_facecolor(SURF)
    ax.set_xlim(0, ncols); ax.set_ylim(len(batches) + 0.6, 0)
    ax.axis("off")
    for i, (b, s) in enumerate(batches):
        y = i + (b - 3) * 0.3
        for j in range(ncols):
            state, lab = getter(s, j)
            box = FancyBboxPatch((j + 0.04, y + 0.04), 0.92, 0.92 * 0.95, boxstyle="round,pad=0,rounding_size=0.06",
                                 facecolor=FAILF if state == "FAIL" else PASSF, edgecolor=SURF, linewidth=2)
            ax.add_patch(box)
            ax.text(j + 0.5, y + 0.5, lab if lab else "PASS", ha="center", va="center", fontsize=7.5,
                    color="#ffffff" if state == "FAIL" else INK2)
    for j, cl in enumerate(col_labels):
        ax.text(j + 0.5, -0.25, cl, ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.text(0, -1.25, title, fontsize=9.5, color=INK, ha="left", va="bottom")

def left(s, j):
    r = next(x for x in main if x["seed"] == s and x["condition"] == conds[j])
    return cell(r["run_id"], True)

p8 = {(r["seed"], r["setting"]): r for r in rows if r["group"] == "p8" and r["cell"] == "cell-b" and r["condition"] == "M0"}
def right(s, j):
    return cell(p8[(s, settings[j])]["run_id"], False)

draw(axes[0], 3, left, ["F", "M0", "M1"], "Correct ladder, `normal`, 5,000 ticks")
draw(axes[1], 8, right, set_labels, "M0 under the eight P8 settings (one change at a time)")
for i, (b, s) in enumerate(batches):
    y = i + (b - 3) * 0.3
    axes[0].text(-0.08, y + 0.5, f"{b} defective, seed {s}", ha="right", va="center", fontsize=8, color=INK2)
fig.text(0.01, 0.965, "Figure 1. Sort cell B(3i): verdicts of the same correct ladder when only the plant model changes",
         fontsize=11, color=INK, ha="left")
fig.text(0.01, 0.905, "Grey = [PASS]; red = [FAIL], labelled with the first-lock FaultCode (3 = chute full, 13 = confirm window) "
         "and its tick.\nRight panel: M0 only (F was [PASS] in all 24 belt runs). Simulation only (tr05-official-2).", fontsize=8.5, color=INK2, ha="left")
fig.savefig(out, dpi=170, facecolor=SURF)
print("wrote", out)
