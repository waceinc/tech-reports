#!/usr/bin/env python3
"""TR-2026-04 figure (pre-registration section 16), drawn directly from the released records.

  fig1  per task and generator: the combination of the three judges' results, (1) static check, (2) input forcing,
        (3) plant-connected run (PASS / FAIL / not run), counted over the judged units; the units that passed all
        three are split into those kept by the leak rule and those it voided (results/TR-04_누출검사_출력_2026-10-02.txt);
        T06-G3-r1, which has no completion record and no verdict, is drawn as "no verdict".
The pre-registration's other two figures (the event moment of a ladder failing (3) only, and the cause classes) are not
drawn: no ladder failed (3) only. No screen capture of a scenario run exists in the round folder, so no capture figure.
Inputs are bundle files only. Output: SVG with the badge drawn in, figure_values.json, and PNG via
`rsvg-convert -w 1600` when installed. Totals are asserted against results/TR-04_분석_출력_2026-10-02.txt.
Usage: make_figures.py BUNDLE_DIR ROUND_DIR WORK_DIR OUT_DIR
       (ROUND_DIR = extracted tr04-official-1/, WORK_DIR = extracted work/ of the generation archive)
"""
import json, re, shutil, subprocess, sys
from pathlib import Path

sys.dont_write_bytecode = True
INK, INK2, GRID, SURF = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
CATS = [('PPP_kept', '(1) PASS (2) PASS (3) PASS — kept by the leak rule', '#1baf7a'),
        ('PPP_void', '(1) PASS (2) PASS (3) PASS — voided by the leak rule', '#9fdcc3'),
        ('PFP', '(1) PASS (2) FAIL (3) PASS', '#eda100'),
        ('FPN', '(1) FAIL (2) PASS (3) not run', '#eb6834'),
        ('FFN', '(1) FAIL (2) FAIL (3) not run', '#e87ba4'),
        ('FNN', '(1) FAIL (2) not run (3) not run', '#2a78d6'),
        ('NOV', 'no verdict (no completion record)', '#ffffff')]
FONT = "font-family='Helvetica Neue, Helvetica, Arial, sans-serif'"
KFONT = "font-family='Pretendard, Apple SD Gothic Neo, Noto Sans KR, sans-serif'"
BADGE = ('시뮬레이션 · 실물 대조 0', '© WACE · CC BY 4.0')
LOGO = {}
CODE = {'[PASS]': 'P', '[FAIL]': 'F', '[NOT_RUN]': 'N'}


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


def load(bundle, rd, wd):
    tasks = [t['id'] for t in json.loads((bundle / 'tasks' / 'TR-04_과제목록_v1.json').read_text(encoding='utf-8'))['tasks']]
    verdicts = {p.parent.name: json.loads(p.read_text()) for p in sorted(rd.glob('T*-G*-r*/verdict.json'))}
    units = sorted(p.name for p in wd.glob('T*-G*-r*') if p.is_dir())
    leak = (bundle / 'results' / 'TR-04_누출검사_출력_2026-10-02.txt').read_text(encoding='utf-8')
    voided = set(re.findall(r'^\s+(T\d\d-G\d-r\d) 누출 ', leak, re.M))
    cat = {}
    for u in units:
        v = verdicts.get(u)
        if v is None:
            cat[u] = 'NOV'
            continue
        k = ''.join(CODE[v[j]] for j in ('j1', 'j2', 'j3'))
        cat[u] = (('PPP_void' if u in voided else 'PPP_kept') if k == 'PPP' else k)
    return tasks, cat


def check(bundle, cat):
    out = (bundle / 'results' / 'TR-04_분석_출력_2026-10-02.txt').read_text(encoding='utf-8')
    judged = [u for u, c in cat.items() if c != 'NOV']
    ppp = [u for u in judged if cat[u].startswith('PPP')]
    kept = [u for u in ppp if cat[u] == 'PPP_kept']
    assert f'생성 폴더 {len(cat)} · unit.json {len(judged)} · verdict.json {len(judged)}' in out
    assert f'③만 [FAIL] = 0/{len(ppp)} ' in out
    assert (len(cat), len(judged), len(ppp), len(kept)) == (147, 146, 109, 54), (len(cat), len(judged), len(ppp), len(kept))
    for g in ('G1', 'G2', 'G3'):
        n = sum(1 for u in judged if u.split('-')[1] == g)
        p = sum(1 for u in ppp if u.split('-')[1] == g)
        assert f' {g} 판정 {n} · ①② 통과 {p} ' in out


def fig1(tasks, cat):
    gens = ('G1', 'G2', 'G3')
    W, top, rh = 1600, 190, 30
    H = top + 40 + rh * len(tasks) + 120
    lab_w, gap = 90, 40
    pw = (W - 60 - lab_w - 2 * gap) / 3
    body = [text(40, 44, 'Figure 1. Results of the three judges, per task and generator', 20, weight='bold'),
            text(40, 70, '146 judged units of round tr04-official-1 and T06-G3-r1 (no verdict). (1) static check, (2) input-forcing test, '
                 '(3) plant-connected run; (3) ran on every ladder that passed (1).', 13, INK2)]
    for i, (k, lab, col) in enumerate(CATS):
        x = 40 + (i % 3) * 510
        y = 102 + (i // 3) * 24
        body.append(f"<rect x='{x}' y='{y - 12}' width='14' height='14' fill='{col}' stroke='{INK2}' stroke-width='{1 if k == 'NOV' else 0}'/>")
        body.append(text(x + 22, y, lab, 13, INK2))
    vals = {}
    for gi, g in enumerate(gens):
        x0 = 40 + lab_w + gi * (pw + gap)
        reps = 1 if g == 'G3' else 3
        body.append(text(x0 + pw / 2, top + 10, f'{g} ({reps} repetition{"s" if reps > 1 else ""} per task)', 15, INK, 'middle', 'bold'))
        for k in range(reps + 1):
            xx = x0 + k / reps * pw
            body.append(f"<line x1='{xx:.1f}' x2='{xx:.1f}' y1='{top + 22}' y2='{top + 30 + rh * len(tasks)}' stroke='{GRID}'/>")
            body.append(text(xx, top + 48 + rh * len(tasks), k, 11, INK2, 'middle'))
        for ti, t in enumerate(tasks):
            y = top + 30 + ti * rh
            if gi == 0:
                body.append(text(40 + lab_w - 14, y + rh / 2 + 5, t, 13, INK, 'end'))
            x, seg = x0, {}
            for k, _, col in CATS:
                n = sum(1 for u, c in cat.items() if u.startswith(t + '-' + g + '-') and c == k)
                if not n:
                    continue
                seg[k] = n
                w = n / reps * pw
                body.append(f"<rect x='{x:.1f}' y='{y + 4}' width='{max(w - 2, 1):.1f}' height='{rh - 8}' fill='{col}' "
                            f"stroke='{INK2}' stroke-width='{1 if k == 'NOV' else 0}'/>")
                x += w
            vals[f'{t}|{g}'] = seg
    body.append(text(40 + lab_w, H - 66, 'Bar length = number of units (G1 and G2: 3 per task; G3: 1 per task). No ladder passed (1) and (2) and '
                     'failed (3). Leak rule: pre-registration section 7, blank tasks only.', 12, INK2))
    return svg(W, H, body), vals


def main(bundle, rd, wd, out):
    bundle, rd, wd, out = Path(bundle), Path(rd), Path(wd), Path(out)
    logo = (bundle / 'figures' / 'wace-wordmark-white.svg').read_text(encoding='utf-8')
    LOGO['vb'] = [float(v) for v in re.search(r"viewBox=\"0 0 ([0-9.]+) ([0-9.]+)\"", logo).groups()]
    LOGO['d'] = re.search(r' d="([^"]+)"', logo).group(1)
    tasks, cat = load(bundle, rd, wd)
    check(bundle, cat)
    s1, v1 = fig1(tasks, cat)
    out.mkdir(parents=True, exist_ok=True)
    name = 'fig1_judge_results_by_task'
    (out / f'{name}.svg').write_text(s1, encoding='utf-8')
    if shutil.which('rsvg-convert'):
        subprocess.run(['rsvg-convert', '-w', '1600', str(out / f'{name}.svg'), '-o', str(out / f'{name}.png')], check=True)
    totals = {k: sum(1 for c in cat.values() if c == k) for k, _, _ in CATS}
    (out / 'figure_values.json').write_text(json.dumps(dict(fig1=v1, fig1_totals=totals), ensure_ascii=False, indent=1, sort_keys=True) + '\n')
    print('[OK] 1 figure; totals asserted against the analysis output:', totals)


if __name__ == '__main__':
    main(*sys.argv[1:5])
