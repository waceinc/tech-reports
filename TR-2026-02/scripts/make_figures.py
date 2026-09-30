#!/usr/bin/env python3
"""TR-2026-02 figures (pre-registration section 9), drawn directly from the released data.

  fig1  the same 1 s of A.Sen.right under both conditions: plant value, scan input received by the PLC,
        PLC output per scan, applied output per tick (runs 1 and 3 = lowest-numbered plant-connected pair)
  fig2  P2 representative case (correct ladder, runs 1 and 3): tick of every applied output change
        under both conditions and the difference
  fig3  P3/P4: short-pulse width vs detections out of 10 phases, per input, both conditions

Inputs are bundle files only: the result file, the extracted run archive and figures/wace-wordmark-white.svg.
Output: SVG with the watermark badge drawn in (deterministic, standard library only), figure_values.json with
the values drawn, and PNG via `rsvg-convert -w 1600` when that program is installed.
Checked against the result file before anything is written: every applied-output change drawn (fig1, fig2) and
the detection counts (fig3). In fig1 the per-scan input row and marker b are reconstructed here from the recorded
plant edges (per-scan inputs are not logged); the tick-start input is checked against the trace's I_start.
Usage: make_figures.py BUNDLE_DIR RUN_DIR OUT_DIR
  RUN_DIR = the extracted tr02-official-1/ folder from runs/tr02-official-1.tar.xz
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

INK, INK2, GRID, SURF = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
COL = {'history': '#2a78d6', 'boundary': '#eb6834'}
NAME = {'history': 'in-tick history restoration', 'boundary': 'boundary sampling'}
FONT = "font-family='Helvetica Neue, Helvetica, Arial, sans-serif'"
WIDTHS = [5, 15, 25, 35, 45]


def ticks(run_dir, name):
    rows = [json.loads(l) for l in (run_dir / name / 'trace.jsonl').read_text().splitlines() if l.strip()]
    return [r for r in rows if r.get('type') == 'tick']


def q_changes(rows):
    out, prev = [], rows[0]['Q']
    for r in rows[1:]:
        for tag in sorted(r['Q']):
            if r['Q'][tag] != prev[tag]:
                out.append([r['tick'] - 1, tag, r['Q'][tag]])  # 0-based tick, as in the result file
        prev = r['Q']
    return out


def text(x, y, s, size=13, fill=INK, anchor='start', weight='normal'):
    s = s.replace('&', '&amp;').replace('<', '&lt;')
    return f"<text x='{x:.1f}' y='{y:.1f}' {FONT} font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}'>{s}</text>"


BADGE = ('시뮬레이션 · 실물 대조 0', '© WACE · CC BY 4.0')
KFONT = "font-family='Pretendard, Apple SD Gothic Neo, Noto Sans KR, sans-serif'"
LOGO = {}


def badge(w, h, corner):
    """Watermark badge: charcoal box, WACE wordmark, simulation note and licence (same shape as the series badge)."""
    u = max(14, w // 90)
    vb_w, vb_h = LOGO['vb']
    lh = u * 1.6
    lw = lh * vb_w / vb_h
    pad = u * 0.55
    bw, bh = pad + lw + pad + u * 8.4 + pad, pad * 2 + lh
    x = w - bw - u if corner == 'br' else u
    y = h - bh - u / 2
    g = [f"<g transform='translate({x:.1f},{y:.1f})'>",
         f"<rect width='{bw:.1f}' height='{bh:.1f}' fill='#0E0F12' fill-opacity='0.72'/>",
         f"<g transform='translate({pad:.1f},{pad:.1f}) scale({lh / vb_h:.5f})'><path fill='#ffffff' d='{LOGO['d']}'/></g>",
         f"<text x='{pad + lw + pad:.1f}' y='{bh / 2 - u * 0.12:.1f}' {KFONT} font-size='{u * 0.62:.1f}' fill='#ffffff' fill-opacity='0.94'>{BADGE[0]}</text>",
         f"<text x='{pad + lw + pad:.1f}' y='{bh / 2 + u * 0.62:.1f}' {KFONT} font-size='{u * 0.48:.1f}' fill='#ffffff' fill-opacity='0.72'>{BADGE[1]}</text>",
         '</g>']
    return ''.join(g)


def svg(w, h, body, corner='bl'):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"
            f"<rect width='{w}' height='{h}' fill='{SURF}'/>" + ''.join(body) + badge(w, h, corner) + '</svg>\n')


def step_path(points, x, hi, lo):
    """points = [(t, bool)] sorted by t; a digital step line."""
    t, v = points[0]
    d = [f'M {x(t):.1f} {hi if v else lo}']
    for t, v in points[1:]:
        d.append(f'H {x(t):.1f} V {hi if v else lo}')
    return ' '.join(d)


def fig1(run_dir, ledger):
    pick = {m: min(r['no'] for r in ledger if r['kind'] == 'plant' and r['variant'] == 'correct' and r['mode'] == m)
            for m in ('history', 'boundary')}
    names = {m: next(r['name'] for r in ledger if r['no'] == pick[m]) for m in pick}
    data = {m: ticks(run_dir, names[m]) for m in pick}
    tag = 'A.Sen.right'
    first = next(r for r in data['history'] if any(e['tag'] == tag for e in r['edges']))
    t0 = (first['tick'] - 1) * 50 - 100
    t1 = t0 + 1000
    vals = dict(window_ms=[t0, t1], runs=pick)
    W, H, L, R = 1600, 1040, 300, 60
    x = lambda t: L + (t - t0) / 1000 * (W - L - R)
    body = [text(40, 44, 'Figure 1. The same 1 s of the right end sensor (A.Sen.right) under both connection conditions', 20, weight='bold'),
            text(40, 70, f'Correct ladder, runs {pick["history"]} and {pick["boundary"]} (lowest-numbered plant-connected pair). '
                 'Grey lines = 50 ms plant ticks; dots = 10 ms PLC scans. Simulated PLC and plant, 0 physical comparisons. '
                 'The scan-input row is reconstructed from the recorded plant edges (per-scan inputs are not logged).', 13, INK2)]
    rows_def = [('plant value', 'plant'), ('input seen by the PLC scan', 'scan_in'), ('PLC output fwd (per scan)', 'scan_fwd'),
                ('PLC output rev (per scan)', 'scan_rev'), ('applied fwd (per tick)', 'app_fwd'), ('applied rev (per tick)', 'app_rev')]
    top = 110
    for k, mode in enumerate(('history', 'boundary')):
        rows = [r for r in data[mode] if t0 < r['tick'] * 50 and (r['tick'] - 1) * 50 < t1]
        py = top + k * 455
        body.append(text(40, py + 18, f'{NAME[mode]} (run {pick[mode]})', 16, COL[mode], weight='bold'))
        for tk in range(t0, t1 + 1, 50):
            body.append(f"<line x1='{x(tk):.1f}' x2='{x(tk):.1f}' y1='{py + 32}' y2='{py + 32 + 6 * 64}' stroke='{GRID}'/>")
        init = data[mode][0]['I_start'][tag]
        edges = [((r['tick'] - 1) * 50 + round(e['t_s'] * 1000), e['value']) for r in data[mode] for e in r['edges'] if e['tag'] == tag]
        value_at = lambda t: next((v for a, v in reversed(edges) if a <= t), init)
        series = {'plant': [(t0, value_at(t0))] + [(a, v) for a, v in edges if t0 < a < t1] + [(t1, value_at(t1))]}
        scan_pts = {'scan_in': [], 'scan_fwd': [], 'scan_rev': []}
        seen = fwd_off = None
        for r in rows:
            start = (r['tick'] - 1) * 50
            assert r['I_start'][tag] == value_at(start)
            for i, s in enumerate(r['scans']):
                ts = start + 10 * (i + 1)
                inp = value_at(start) if mode == 'boundary' else value_at(ts)
                scan_pts['scan_in'].append((ts, inp))
                scan_pts['scan_fwd'].append((ts, s['Q']['A.Mot.fwd']))
                scan_pts['scan_rev'].append((ts, s['Q']['A.Mot.rev']))
                if inp and seen is None:
                    seen = ts
                if seen is not None and fwd_off is None and not s['Q']['A.Mot.fwd']:
                    fwd_off = ts
        app = {'app_fwd': [], 'app_rev': []}
        for r in rows:
            app['app_fwd'].append(((r['tick'] - 1) * 50, r['Q']['A.Mot.fwd']))
            app['app_rev'].append(((r['tick'] - 1) * 50, r['Q']['A.Mot.rev']))
        for key in app:
            app[key] = [(max(t, t0), v) for t, v in app[key]] + [(t1, app[key][-1][1])]
        ch = [c for c in q_changes(data[mode]) if t0 <= c[0] * 50 < t1]
        vals[mode] = dict(plant_edges_ms=[[a, v] for a, v in edges if t0 < a < t1], first_scan_seeing_edge_ms=seen,
                          first_scan_fwd_off_ms=fwd_off, applied_changes_in_window=ch)
        for j, (label, key) in enumerate(rows_def):
            ry = py + 40 + j * 64
            hi, lo = ry + 8, ry + 40
            body.append(text(40, ry + 29, label, 13, INK2))
            body.append(f"<line x1='{L}' x2='{W - R}' y1='{lo}' y2='{lo}' stroke='{GRID}'/>")
            if key == 'plant':
                pts = series['plant']
            elif key in scan_pts:
                pts = scan_pts[key]
                for t, v in pts:
                    if t0 <= t <= t1:
                        body.append(f"<circle cx='{x(t):.1f}' cy='{hi if v else lo}' r='3.5' fill='{COL[mode]}' stroke='{SURF}' stroke-width='1.5'/>")
                pts = [(t0, pts[0][1])] + pts + [(t1, pts[-1][1])]
            else:
                pts = app[key]
            dash = " stroke-dasharray='6 4'" if key in scan_pts else ''
            body.append(f"<path d='{step_path(pts, x, hi, lo)}' fill='none' stroke='{COL[mode]}' stroke-width='2'{dash}/>")
        win_edges = [a for a, _ in edges if t0 < a < t1]
        marks = [(win_edges[0] if win_edges else None, 'a', 'plant edge'), (seen, 'b', 'first scan that sees it'),
                 (fwd_off, 'c', 'first scan with fwd off')]
        key = '  ·  '.join(f'{m} = {lab} {t} ms' for t, m, lab in marks if t is not None)
        body.append(text(W - R, py + 18, key, 13, INK2, 'end'))
        for t, m, _ in marks:
            if t is not None and t0 <= t <= t1:
                body.append(f"<line x1='{x(t):.1f}' x2='{x(t):.1f}' y1='{py + 36}' y2='{py + 40 + 6 * 64}' stroke='{INK2}' stroke-dasharray='2 3'/>")
                body.append(text(x(t), py + 34, m, 12, INK, 'middle', 'bold'))
    for tk in range(t0, t1 + 1, 100):
        body.append(text(x(tk), H - 26, f'{tk}', 12, INK2, 'middle'))
    body.append(text((L + W - R) / 2, H - 6, 'time since the start of the run (ms)', 13, INK2, 'middle'))
    return svg(W, H, body), vals


def fig2(run_dir, ledger, res):
    m4 = res['metric4']['correct']
    h_no, b_no = m4['runs']
    names = {r['no']: r['name'] for r in ledger}
    qh, qb = q_changes(ticks(run_dir, names[h_no])), q_changes(ticks(run_dir, names[b_no]))
    assert qh == m4['history_changes'] and qb == m4['boundary_changes']
    W, L, R, rowh = 1600, 420, 120, 44
    H = 150 + rowh * len(qh) + 70
    x = lambda d: L + d / 2 * (W - L - R)
    body = [text(40, 44, 'Figure 2. P2 representative case: every applied output change came exactly one tick later under boundary sampling', 20, weight='bold'),
            text(40, 70, f'Correct ladder, runs {h_no} (in-tick history restoration) and {b_no} (boundary sampling). Ticks counted from 0. '
                 'Bar = boundary tick minus history tick.', 13, INK2)]
    for d in (0, 1, 2):
        body.append(f"<line x1='{x(d):.1f}' x2='{x(d):.1f}' y1='110' y2='{H - 60}' stroke='{GRID}'/>")
        body.append(text(x(d), H - 38, f'{d:+d}' if d else '0', 13, INK2, 'middle'))
    body.append(text((L + W - R) / 2, H - 14, 'tick difference (boundary - history)', 13, INK2, 'middle'))
    body.append(text(40, 104, 'change (order, output, value)', 13, INK2, weight='bold'))
    body.append(text(250, 104, 'history tick -> boundary tick', 13, INK2, weight='bold'))
    rows = []
    for i, (a, b) in enumerate(zip(qh, qb)):
        y = 130 + i * rowh
        d = b[0] - a[0]
        rows.append(dict(index=i + 1, tag=a[1], value=a[2], history_tick=a[0], boundary_tick=b[0], diff=d))
        body.append(text(40, y + 20, f'{i + 1:2d}. {a[1].split(".")[-1]} {"on" if a[2] else "off"}', 14))
        body.append(text(250, y + 20, f'{a[0]} -> {b[0]}', 14))
        body.append(f"<rect x='{x(0):.1f}' y='{y + 6}' width='{x(d) - x(0):.1f}' height='{rowh - 14}' rx='4' fill='{COL['boundary']}'/>")
        body.append(text(x(d) + 8, y + 20, f'+{d}', 13))
    return svg(W, H, body), dict(runs=[h_no, b_no], changes=rows)


def fig3(res):
    m5 = res['metric5']
    tags = [('A.PB.stop_nc', 'stop (NC), no filter'), ('A.PB.estop_nc', 'emergency stop (NC), no filter'),
            ('A.Sen.left', 'left end sensor, 10-scan filter'), ('A.Sen.right', 'right end sensor, 10-scan filter')]
    W, H = 1600, 1000
    body = [text(40, 44, 'Figure 3. Short pulses: detections out of 10 phases vs pulse width (P3, P4)', 20, weight='bold'),
            text(40, 70, 'Correct ladder, pulse synthesised on the PLC input side in tick 100; repetitions 1 and 2 identical. '
                 'Filtered inputs: 0 of 10 under both conditions at every width (lines overlap).', 13, INK2)]
    vals = {}
    for k, (tag, label) in enumerate(tags):
        ox, oy = 40 + (k % 2) * 780, 110 + (k // 2) * 440
        pl, pr, pt, pb = ox + 70, ox + 700, oy + 50, oy + 350
        x = lambda w: pl + (w - 5) / 40 * (pr - pl)
        y = lambda n: pb - n / 10 * (pb - pt)
        body.append(text(ox, oy + 24, f'{tag} - {label}', 15, weight='bold'))
        for n in range(0, 11, 2):
            body.append(f"<line x1='{pl}' x2='{pr}' y1='{y(n):.1f}' y2='{y(n):.1f}' stroke='{GRID}'/>")
            body.append(text(pl - 10, y(n) + 4, str(n), 12, INK2, 'end'))
        for w in WIDTHS:
            body.append(text(x(w), pb + 26, f'{w} ms', 12, INK2, 'middle'))
        body.append(text((pl + pr) / 2, pb + 50, 'pulse width', 13, INK2, 'middle'))
        vals[tag] = {}
        for mode in ('history', 'boundary'):
            c1 = [m5[f'{tag}|{w}|{mode}']['count']['1'] for w in WIDTHS]
            c2 = [m5[f'{tag}|{w}|{mode}']['count']['2'] for w in WIDTHS]
            assert c1 == c2
            vals[tag][mode] = c1
            pts = ' '.join(f'{x(w):.1f},{y(n):.1f}' for w, n in zip(WIDTHS, c1))
            dash = " stroke-dasharray='8 5'" if mode == 'boundary' else ''
            body.append(f"<polyline points='{pts}' fill='none' stroke='{COL[mode]}' stroke-width='2'{dash}/>")
            for w, n in zip(WIDTHS, c1):
                if mode == 'history':
                    body.append(f"<circle cx='{x(w):.1f}' cy='{y(n):.1f}' r='5' fill='{COL[mode]}' stroke='{SURF}' stroke-width='2'/>")
                else:
                    body.append(f"<rect x='{x(w) - 5:.1f}' y='{y(n) - 5:.1f}' width='10' height='10' fill='{COL[mode]}' stroke='{SURF}' stroke-width='2'/>")
                if mode == 'history' or n != vals[tag]['history'][WIDTHS.index(w)]:
                    body.append(text(x(w), y(n) + (-12 if mode == 'history' else 22), str(n), 12, INK, 'middle'))
        if k == 0:
            body.append(text(x(45) + 12, y(vals[tag]['history'][-1]) + 4, 'history', 13, COL['history'], weight='bold'))
            body.append(text(x(45) + 12, y(vals[tag]['boundary'][-1]) + 4, 'boundary', 13, COL['boundary'], weight='bold'))
    body.append(f"<circle cx='60' cy='{H - 30}' r='5' fill='{COL['history']}'/>" + text(74, H - 25, NAME['history'] + ' (solid, circles)', 13, INK2))
    body.append(f"<rect x='455' y='{H - 35}' width='10' height='10' fill='{COL['boundary']}'/>" + text(474, H - 25, NAME['boundary'] + ' (dashed, squares)', 13, INK2))
    return svg(W, H, body, 'br'), vals


def main(bundle, run_dir, out):
    bundle, run_dir, out = Path(bundle), Path(run_dir), Path(out)
    result = bundle / 'results' / 'TR-02_결과_tr02-official-1.json'
    res = json.loads(result.read_text(encoding='utf-8'))
    logo = (bundle / 'figures' / 'wace-wordmark-white.svg').read_text(encoding='utf-8')
    LOGO['vb'] = [float(v) for v in re.search(r"viewBox=\"0 0 ([0-9.]+) ([0-9.]+)\"", logo).groups()]
    LOGO['d'] = re.search(r' d="([^"]+)"', logo).group(1)
    ledger = [json.loads(l) for l in (run_dir / 'ledger.jsonl').read_text().splitlines() if l.strip()]
    s1, v1 = fig1(run_dir, ledger)
    s2, v2 = fig2(run_dir, ledger, res)
    s3, v3 = fig3(res)
    m4 = res['metric4']['correct']
    assert v1['history']['applied_changes_in_window'] == [c for c in m4['history_changes'] if c in v1['history']['applied_changes_in_window']]
    assert v1['boundary']['applied_changes_in_window'] == [c for c in m4['boundary_changes'] if c in v1['boundary']['applied_changes_in_window']]
    out.mkdir(parents=True, exist_ok=True)
    for name, s in (('fig1_right_sensor_1s', s1), ('fig2_p2_output_shift', s2), ('fig3_short_pulse_detection', s3)):
        (out / f'{name}.svg').write_text(s, encoding='utf-8')
        if shutil.which('rsvg-convert'):
            subprocess.run(['rsvg-convert', '-w', '1600', str(out / f'{name}.svg'), '-o', str(out / f'{name}.png')], check=True)
    (out / 'figure_values.json').write_text(json.dumps(dict(fig1=v1, fig2=v2, fig3=v3), indent=1, sort_keys=True) + '\n')
    print('[OK] 3 figures; values asserted against', Path(result).name)


if __name__ == '__main__':
    main(*sys.argv[1:4])
