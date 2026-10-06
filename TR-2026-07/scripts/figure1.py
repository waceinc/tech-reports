#!/usr/bin/env python3
"""TR-2026-07 Figure 1 from results/tables.json: empty travel per completed transfer, return rule and rebalance rule,
per authoring (left), and the ratio r_k (right). usage: figure1.py <tables.json> <out.png>"""
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

tables = json.load(open(sys.argv[1], encoding='utf-8'))
per = tables['perAuthoring']
ks = sorted(per, key=int)
ret = [per[k]['return']['emptyTravelMeters'] / per[k]['return']['completed'] for k in ks]
pre = [per[k]['predictive']['emptyTravelMeters'] / per[k]['predictive']['completed'] for k in ks]
ratio = [tables['ratios'][k] for k in ks]
x = [int(k) for k in ks]
fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.2), dpi=150, gridspec_kw={'width_ratios': [3, 2]})
a.plot(x, ret, 'o-', color='#b03a2e', label='return to start position')
a.plot(x, pre, 's-', color='#1f5f9f', label='dispatch where it unloaded (rebalance)')
a.set_xlabel('authoring k (same layout file, new object identifiers)')
a.set_ylabel('empty travel per completed transfer (m)')
a.set_xticks(x)
a.set_ylim(0, max(ret + pre) * 1.15)
a.legend(loc='lower right', fontsize=8)
a.grid(alpha=.3)
b.plot(sorted(ratio), range(1, len(ratio) + 1), 'o-', color='#333333')
b.axvline(0.95, color='#888888', ls='--', lw=1)
b.axvline(1.0, color='#888888', ls=':', lw=1)
b.set_xlabel('r_k = rebalance / return (per transfer)')
b.set_ylabel('authorings at or below (cumulative)')
b.text(0.951, 1, 'P1 line 0.95', fontsize=7, color='#555555')
b.grid(alpha=.3)
fig.suptitle('TR-2026-07 official round: 20 authorings x 150 s, simulation only', fontsize=10)
fig.tight_layout()
fig.savefig(sys.argv[2])
