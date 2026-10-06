#!/usr/bin/env python3
"""TR-2026-06 Figure 1: end-joint mismatch rate and playback-allowed (V) rate by strategy and group.

Reads the public results.jsonl (decompressed from results/results.jsonl.gz) and fixed/TR-06_입력목록_v2.json of this bundle; base speed, first plan.
  python3 figure1.py <results.jsonl> <input list> <out.png>
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SOLVERS = ["C0", "C1", "C2", "C3", "C2z"]
LABELS = {"C0": "C0\ncurrent", "C1": "C1\ntarget", "C2": "C2\nready pose", "C3": "C3\njoint interp.", "C2z": "C2z\nzero pose"}
COLORS = {"cross": "#2a78d6", "noncross": "#eb6834"}
NAMES = {"cross": "J5 sign crossing (240 moves)", "noncross": "non-crossing (480 moves)"}


def main(results, inputs, out):
    group = {e["k"]: e["group"] for e in json.load(open(inputs, encoding="utf-8"))["inputs"]}
    rows = [json.loads(l) for l in open(results, encoding="utf-8") if l.strip()]
    rows = [r for r in rows if r["speed"] == "base" and r["plan_round"] == 1]
    rate = {}
    for metric in ("mismatch", "V"):
        for s in SOLVERS:
            for g in ("cross", "noncross"):
                sel = [r for r in rows if r["solver"] == s and group[r["k"]] == g]
                hit = sum(r["mismatch"] if metric == "mismatch" else r["verdict"]["V"] == "allow" for r in sel)
                rate[metric, s, g] = (hit, len(sel))
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.4), sharey=True)
    titles = {"mismatch": "End-joint mismatch", "V": "Playback allowed by the full check V"}
    w = 0.36
    for ax, metric in zip(axes, ("mismatch", "V")):
        for i, g in enumerate(("cross", "noncross")):
            xs = [j + (i - 0.5) * (w + 0.02) for j in range(len(SOLVERS))]
            vals = [100 * rate[metric, s, g][0] / rate[metric, s, g][1] for s in SOLVERS]
            ax.bar(xs, vals, width=w, color=COLORS[g], label=NAMES[g], zorder=2)
            for x, v, s in zip(xs, vals, SOLVERS):
                ax.text(x, v + 1.5, f"{rate[metric, s, g][0]}", ha="center", va="bottom", fontsize=7, color="#3d3d3a")
        ax.set_xticks(range(len(SOLVERS)), [LABELS[s] for s in SOLVERS])
        ax.set_title(titles[metric], loc="left", fontsize=10, color="#1a1a19")
        ax.set_ylim(0, 108)
        ax.yaxis.grid(True, color="#e6e5df", linewidth=0.8, zorder=0)
        ax.tick_params(colors="#55554f", length=0)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color("#c3c2b7")
    axes[0].set_ylabel("% of moves (count above bar)")
    axes[0].legend(frameon=False, loc="upper right", fontsize=8)
    fig.text(0.01, 0.005, "WACE TR-2026-06 · simulation, 12 robot-arm models × 60 linear moves, base speed · no physical comparison",
             fontsize=7, color="#72716a")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out, dpi=200)


if __name__ == "__main__":
    main(*sys.argv[1:4])
