#!/usr/bin/env python3
"""TR-2026-03 figures (pre-registration section 10), drawn directly from the released data.

  fig1  stage distribution per cell and functional group (set with flow 0.45; stage-4 split read literally, from
        results/TR-03_재분류_위험사건_v2_tr03-official-1.json; stages 1-3 and held asserted against the result file)
  fig2  representative revealed variant cell-a-0004 (lowest number among stage 4): the shorted rung drawn from the
        public ladder, and the applied outputs of the baseline run and the variant run from the released traces
  fig3  representative inactive variant cell-a-0005 (lowest number among stage 1): the condition's input value at every
        scan of both cell-A scenarios, rebuilt from the baseline traces with the released `reconstruct`
Inputs are bundle files only. Output: SVG with the badge drawn in, figure_values.json, and PNG via
`rsvg-convert -w 1600` when installed. Values are asserted against the result file before anything is written.
Usage: make_figures.py BUNDLE_DIR ROUND_DIR OUT_DIR   (ROUND_DIR = extracted tr03-official-1/)
"""
import json, re, shutil, subprocess, sys
from pathlib import Path

sys.dont_write_bytecode = True
INK, INK2, GRID, SURF = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
STAGE = [('1', '1 inactive', '#2a78d6'), ('2', '2 active, outputs unchanged', '#eb6834'),
         ('3', '3 outputs changed; compared outcome and verdict unchanged', '#1baf7a'), ('4a', '4a revealed: hazard event or defective part at good exit', '#eda100'),
         ('4b', '4b revealed: verdict only', '#e87ba4'), ('보류', 'held (run error)', '#ffffff')]
GROUP_EN = {'안전': 'safety', '밀기 순서': 'push sequence', '출력': 'output', '알람': 'alarm', '복귀': 'recovery',
            '포장 핸드셰이크': 'pack handshake'}
CELL_EN = {'cell-a': 'Cell A', 'cell-b': 'Cell B', 'cell-b-pack': 'Pack cell'}
FONT = "font-family='Helvetica Neue, Helvetica, Arial, sans-serif'"
KFONT = "font-family='Pretendard, Apple SD Gothic Neo, Noto Sans KR, sans-serif'"
BADGE = ('시뮬레이션 · 실물 대조 0', '© WACE · CC BY 4.0')
LOGO = {}


def text(x, y, s, size=13, fill=INK, anchor='start', weight='normal', font=FONT):
    s = str(s).replace('&', '&amp;').replace('<', '&lt;')
    return f"<text x='{x:.1f}' y='{y:.1f}' {font} font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}'>{s}</text>"


def badge(w, h):
    u = max(14, w // 90)
    vb_w, vb_h = LOGO['vb']
    lh = u * 1.6
    lw = lh * vb_w / vb_h
    pad = u * 0.55
    bw, bh = pad + lw + pad + u * 8.4 + pad, pad * 2 + lh
    x, y = w - bw - u, h - bh - u / 2
    return (f"<g transform='translate({x:.1f},{y:.1f})'><rect width='{bw:.1f}' height='{bh:.1f}' fill='#0E0F12' fill-opacity='0.72'/>"
            f"<g transform='translate({pad:.1f},{pad:.1f}) scale({lh / vb_h:.5f})'><path fill='#ffffff' d='{LOGO['d']}'/></g>"
            f"<text x='{pad + lw + pad:.1f}' y='{bh / 2 - u * 0.12:.1f}' {KFONT} font-size='{u * 0.62:.1f}' fill='#ffffff' fill-opacity='0.94'>{BADGE[0]}</text>"
            f"<text x='{pad + lw + pad:.1f}' y='{bh / 2 + u * 0.62:.1f}' {KFONT} font-size='{u * 0.48:.1f}' fill='#ffffff' fill-opacity='0.72'>{BADGE[1]}</text></g>")


def svg(w, h, body):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"
            f"<rect width='{w}' height='{h}' fill='{SURF}'/>" + ''.join(body) + badge(w, h) + '</svg>\n')


def jl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


def fig1(res, lit):
    m2 = lit['full']['distribution']
    rows = [(c, g) for c in ('cell-a', 'cell-b', 'cell-b-pack') for g in GROUP_EN if g in m2[c]]
    W, H, top, rh = 1600, 150 + 52 * len(rows) + 130, 150, 52
    pl, pr = 330, 1540
    body = [text(40, 44, 'Figure 1. Stage of each sampled variant, by cell and functional group', 20, weight='bold'),
            text(40, 70, '500 variants, one series condition shorted each; stage from the pre-registered 4-stage rule; '
                 'all scenarios including flow 0.45; stage 4 split by the pre-registered wording (hazard events, defective parts at the good exit).', 13, INK2)]
    for i, (k, lab, col) in enumerate(STAGE):
        x = 40 + (i % 3) * 470
        y = 100 + (i // 3) * 24
        body.append(f"<rect x='{x}' y='{y - 12}' width='14' height='14' fill='{col}' stroke='{INK2}' stroke-width='{1 if k == '보류' else 0}'/>")
        body.append(text(x + 22, y, lab, 13, INK2))
    vals, maxn = {}, max(sum(m2[c][g][k] for k, _, _ in STAGE) for c, g in rows)
    for j, (c, g) in enumerate(rows):
        y = top + 20 + j * rh
        n = sum(m2[c][g][k] for k, _, _ in STAGE)
        body.append(text(pl - 14, y + 22, f'{CELL_EN[c]} · {GROUP_EN[g]} (n={n})', 14, INK, 'end'))
        x, seg = pl, {}
        for k, _, col in STAGE:
            v = m2[c][g][k]
            seg[k] = v
            if not v:
                continue
            w = v / maxn * (pr - pl)
            body.append(f"<rect x='{x:.1f}' y='{y + 4}' width='{max(w - 2, 1):.1f}' height='{rh - 14}' fill='{col}' "
                        f"stroke='{INK2}' stroke-width='{1 if k == '보류' else 0}'/>")
            if w >= 22:
                body.append(text(x + w / 2 - 1, y + 25, v, 12, INK, 'middle'))
            x += w
        vals[f'{c}|{g}'] = seg
    body.append(text(pl, H - 70, 'Bar length = number of sampled variants. Cell A: all 25 target conditions; cells B and pack: '
                     'stratified sample (36 and 55 per group; output group complete).', 12, INK2))
    return svg(W, H, body), vals


def rung_cells(ladder, rung):
    return json.loads(Path(ladder).read_text(encoding='utf-8'))['rungs'][rung]


def fig2(bundle, rd, res, ledger):
    v = res['variants']['cell-a-0004']
    rung = rung_cells(bundle / 'ladders' / 'cell-a__correct.program.ldprog.json', v['rung'])
    base = next(r for r in ledger if r['kind'] == 'baseline' and r['cell'] == 'cell-a' and r['key'] == 'normal' and r['rep'] == 1)
    var = next(r for r in ledger if r['variant_id'] == 'cell-a-0004' and r['key'] == 'normal')
    W, H = 1600, 640
    body = [text(40, 44, 'Figure 2. Revealed: cell-a-0004 — contact M_비상기억 (NO) shorted in rung 11 (group: safety)', 20, weight='bold', font=KFONT),
            text(40, 70, f"Left: the rung as written in the public ladder, shorted contact marked. Right: applied outputs, "
                 f"normal scenario, baseline run {base['no']} vs variant run {var['no']}.", 13, INK2)]
    ox, oy, cw = 60, 170, 150
    body.append(text(ox, oy - 40, f"rung {v['rung']} · comment: {rung['comment']}", 14, INK, weight='bold', font=KFONT))
    body.append(f"<line x1='{ox}' y1='{oy - 20}' x2='{ox}' y2='{oy + 60}' stroke='{INK}' stroke-width='3'/>")
    for i, cell in enumerate(rung['grid'][0]):
        x0 = ox + i * cw
        shorted = [0, i] in v['cells']
        body.append(f"<line x1='{x0}' y1='{oy + 20}' x2='{x0 + cw}' y2='{oy + 20}' stroke='{INK}' stroke-width='2'/>")
        if cell['k'] == 'contact':
            if shorted:
                body.append(f"<rect x='{x0 + 40}' y='{oy - 6}' width='70' height='52' fill='none' stroke='#eda100' stroke-width='3' stroke-dasharray='6 4'/>")
                body.append(text(x0 + 75, oy + 80, 'shorted', 13, INK, 'middle', 'bold'))
            else:
                body.append(f"<rect x='{x0 + 60}' y='{oy + 2}' width='30' height='36' fill='{SURF}'/>"
                            f"<line x1='{x0 + 62}' y1='{oy + 2}' x2='{x0 + 62}' y2='{oy + 38}' stroke='{INK}' stroke-width='2'/>"
                            f"<line x1='{x0 + 88}' y1='{oy + 2}' x2='{x0 + 88}' y2='{oy + 38}' stroke='{INK}' stroke-width='2'/>")
        else:
            body.append(f"<circle cx='{x0 + 75}' cy='{oy + 20}' r='18' fill='{SURF}' stroke='{INK}' stroke-width='2'/>")
        body.append(text(x0 + 75, oy - 14, cell['tag'], 12, INK, 'middle', font=KFONT))
        body.append(text(x0 + 75, oy + 60, f"{cell['k']} {cell['mode']}", 11, INK2, 'middle'))
    sums = {}
    for tag, r in (('baseline', base), ('variant', var)):
        s = json.loads((rd / r['name'] / 'summary.json').read_text())
        sums[tag] = dict(run=r['no'], status=s['status'], round_trips=s['probes']['Rounds'], plant_events=s['event_count'],
                         judgments=s['judgment_count'])
    ty = 330
    for i, (tag, s) in enumerate(sums.items()):
        body.append(text(60, ty + i * 26, f"{tag} run {s['run']}: verdict {s['status']} · round trips {s['round_trips']} of 3 · "
                         f"plant events {s['plant_events']} · per-tick judgments {s['judgments']}", 13))
    body.append(text(60, ty + 60, 'Same plant events and final part state; only the verdict differs -> stage 4b.', 13, INK2))
    px0, px1, rows = 800, 1540, {}
    for tag, r in (('baseline', base), ('variant', var)):
        rows[tag] = [t for t in jl(rd / r['name'] / 'trace.jsonl') if t.get('type') == 'tick']
    first = next(i + 1 for i, (a, b) in enumerate(zip(rows['baseline'], rows['variant'])) if a['Q'] != b['Q'])
    assert first == res['run_levels']['cell-a-0004']['normal']['q_first_diff_tick']
    tmax = 300
    x = lambda t: px0 + (t - 1) / (tmax - 1) * (px1 - px0)
    body.append(text(px0, 130, f'applied outputs, runner ticks 1-{tmax} (50 ms each)', 14, weight='bold'))
    lanes, values = [('baseline', 'A.Mot.fwd'), ('baseline', 'A.Mot.rev'), ('variant', 'A.Mot.fwd'), ('variant', 'A.Mot.rev')], {}
    for j, (tag, q) in enumerate(lanes):
        y0 = 170 + j * 70
        hi, lo = y0, y0 + 36
        pts = [(t['tick'], t['Q'][q]) for t in rows[tag][:tmax]]
        d = f'M {x(pts[0][0]):.1f} {hi if pts[0][1] else lo}' + ''.join(
            f' H {x(t):.1f} V {hi if b else lo}' for t, b in pts[1:])
        body.append(f"<line x1='{px0}' x2='{px1}' y1='{lo}' y2='{lo}' stroke='{GRID}'/>")
        body.append(f"<path d='{d} H {px1}' fill='none' stroke='{'#2a78d6' if tag == 'baseline' else '#eb6834'}' stroke-width='2'/>")
        body.append(text(px0 - 10, y0 + 24, f'{tag} {q}', 12, INK2, 'end'))
        values[f'{tag}|{q}'] = [t for t, b in pts if b][:1] + [sum(b for _, b in pts)]
    body.append(f"<line x1='{x(first):.1f}' x2='{x(first):.1f}' y1='150' y2='470' stroke='{INK}' stroke-dasharray='4 4'/>")
    body.append(text(x(first) + 6, 490, f'first differing tick {first}', 12))
    body.append(text(px0, 560, 'Variant: no forward or reverse drive in the first 300 ticks (the cell never started).', 13, INK2))
    return svg(W, H, body), dict(summaries=sums, first_diff_tick=first, first_on_tick_and_on_count=values)


def fig3(bundle, rd, res, ledger):
    sys.path.insert(0, str(bundle / 'runner_thin_layer' / 'bridge'))
    from run import reconstruct
    v = res['variants']['cell-a-0005']
    W, H = 1600, 700
    body = [text(40, 44, 'Figure 3. Inactive: cell-a-0005 — contact A.PB.estop_nc (NO) in rung 11 (group: safety)', 20, weight='bold'),
            text(40, 70, 'Input value seen at every PLC scan of the baseline runs, rebuilt from the recorded plant edges. '
                 'The NO contact blocks only when the value is 0.', 13, INK2)]
    vals = {}
    lanes = [('normal', 'A.PB.estop_nc'), ('cycle-stop', 'A.PB.estop_nc'), ('cycle-stop', 'A.PB.stop_nc')]
    for j, (key, tag) in enumerate(lanes):
        r = next(r for r in ledger if r['kind'] == 'baseline' and r['cell'] == 'cell-a' and r['key'] == key and r['rep'] == 1)
        seq = []
        for t in jl(rd / r['name'] / 'trace.jsonl'):
            if t.get('type') == 'tick':
                seq += [img[tag] for img in reconstruct(t['I_start'], dict(dt_s=t['dt_s'], edges=t['edges'], I=t['I']))]
        zeros = sum(1 for b in seq if b is False)
        if tag == v['tag']:
            assert zeros == v['active_scans'][key]
        vals[f'{key}|{tag}'] = dict(run=r['no'], scans=len(seq), value0_scans=zeros)
        y0, px0, px1 = 140 + j * 150, 330, 1540
        x = lambda i: px0 + i / 6000 * (px1 - px0)
        d, prev = f'M {px0} {y0 if seq[0] else y0 + 50}', seq[0]
        for i, b in enumerate(seq[1:], 1):
            if b != prev:
                d += f' H {x(i):.1f} V {y0 if b else y0 + 50}'
                prev = b
        d += f' H {x(len(seq)):.1f}'
        body.append(f"<line x1='{px0}' x2='{px1}' y1='{y0 + 50}' y2='{y0 + 50}' stroke='{GRID}'/>")
        body.append(f"<path d='{d}' fill='none' stroke='{'#2a78d6' if tag == v['tag'] else '#8a8883'}' stroke-width='2'/>")
        body.append(text(px0 - 14, y0 + 20, f'{tag}', 14, INK, 'end', 'bold'))
        body.append(text(px0 - 14, y0 + 40, f"{key}, run {r['no']}", 12, INK2, 'end'))
        body.append(text(px0 - 14, y0 + 58, f'value 0 in {zeros} of {len(seq)} scans', 12, INK2, 'end'))
        body.append(text(px1 + 14, y0 + 4, '1', 11, INK2, 'start') + text(px1 + 14, y0 + 54, '0', 11, INK2, 'start'))
    for k in range(0, 6001, 1000):
        body.append(f"<line x1='{x(k):.1f}' x2='{x(k):.1f}' y1='545' y2='551' stroke='{INK2}'/>" + text(x(k), 568, k, 11, INK2, 'middle'))
    body.append(text(330, 598, 'scan number (10 ms each); the grey lane is the stop input, which the cycle-stop scenario does press, '
                     'shown for contrast', 12, INK2))
    return svg(W, H, body), vals


def main(bundle, rd, out):
    bundle, rd, out = Path(bundle), Path(rd), Path(out)
    res = json.loads((bundle / 'results' / 'TR-03_결과_tr03-official-1.json').read_text(encoding='utf-8'))
    logo = (bundle / 'figures' / 'wace-wordmark-white.svg').read_text(encoding='utf-8')
    LOGO['vb'] = [float(v) for v in re.search(r"viewBox=\"0 0 ([0-9.]+) ([0-9.]+)\"", logo).groups()]
    LOGO['d'] = re.search(r' d="([^"]+)"', logo).group(1)
    ledger = jl(rd / 'ledger.jsonl')
    reps = res['sets']['full']['representatives']
    assert reps['드러남'] == 'cell-a-0004' and reps['1'] == 'cell-a-0005'
    lit = json.loads((bundle / 'results' / 'TR-03_재분류_위험사건_v2_tr03-official-1.json').read_text(encoding='utf-8'))
    assert all(lit['full']['distribution'][c]['전체'][s] == res['sets']['full']['metric2'][c]['전체'][s] for c in lit['full']['distribution'] for s in ('1', '2', '3', '보류'))
    s1, v1 = fig1(res, lit)
    s2, v2 = fig2(bundle, rd, res, ledger)
    s3, v3 = fig3(bundle, rd, res, ledger)
    out.mkdir(parents=True, exist_ok=True)
    for name, s in (('fig1_stage_distribution', s1), ('fig2_revealed_cell-a-0004', s2), ('fig3_inactive_cell-a-0005', s3)):
        (out / f'{name}.svg').write_text(s, encoding='utf-8')
        if shutil.which('rsvg-convert'):
            subprocess.run(['rsvg-convert', '-w', '1600', str(out / f'{name}.svg'), '-o', str(out / f'{name}.png')], check=True)
    (out / 'figure_values.json').write_text(json.dumps(dict(fig1=v1, fig2=v2, fig3=v3), ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    print('[OK] 3 figures; values asserted against the result file')


if __name__ == '__main__':
    main(*sys.argv[1:4])
