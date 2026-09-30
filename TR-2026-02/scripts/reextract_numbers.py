#!/usr/bin/env python3
"""TR-2026-02: re-extract every number in the report text from the release bundle (pre-release gate 1).

For each number the script computes the value from a released file (result JSON, ledger, run records,
check records, bundle files), compares it with the expected value, and confirms that the sentence
carrying it is present in the report body (Sections 1-10; Appendix A is excluded). Numbers that cannot
come from the bundle are printed separately with their source. Exit code 0 only if every row matches.

Usage: reextract_numbers.py BUNDLE_DIR RUN_DIR REPORT_MD [--table OUT.md] [--selftest]
  BUNDLE_DIR = the release bundle; RUN_DIR = tr02-official-1/ extracted from runs/tr02-official-1.tar.xz
  --selftest  = negative control: perturbs three expected values and one report text; requires exactly those four failures.
Python 3 standard library only. Source abbreviations as in the report's Appendix A.
"""
import datetime, glob, hashlib, json, os, re, sys
from collections import Counter

args = [a for a in sys.argv[1:] if not a.startswith('--')]
BUNDLE, RUN, REPORT = (os.path.join(a, '') if i < 2 else a for i, a in enumerate(args[:3]))
TABLE = sys.argv[sys.argv.index('--table') + 1] if '--table' in sys.argv else None
SELFTEST = '--selftest' in sys.argv
body = open(REPORT, encoding='utf-8').read().split('## Appendix A')[0]
RES = BUNDLE + 'results/TR-02_결과_tr02-official-1.json'
R = json.load(open(RES, encoding='utf-8'))
L = [json.loads(l) for l in open(RUN + 'ledger.jsonl', encoding='utf-8')]
M = json.load(open(glob.glob(RUN + '0001-*')[0] + '/metadata.json', encoding='utf-8'))
K = open(BUNDLE + 'results/TR-02_분석_결정성·대조확인_tr02-official-1.md', encoding='utf-8').read()
I = open(BUNDLE + 'results/TR-02_리드독립검산_tr02-official-1.md', encoding='utf-8').read()
sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
m2 = R['metric2']; m4 = R['metric4']; m5 = R['metric5']
S = {}
for d in glob.glob(RUN + '0*'):
    S[int(os.path.basename(d)[:4])] = json.load(open(d + '/summary.json', encoding='utf-8'))
lk = {l['no']: l for l in L}
short = [n for n in S if n > 12]
r2 = [n for n in short if S[n]['probes']['Rounds'] == 2 and S[n]['probes']['Running']]
r1 = [n for n in short if S[n]['probes']['Rounds'] == 1 and not S[n]['probes']['Running']]
det = set()
for k, v in m5.items():
    tag, w, mode = k.split('|')
    for rep, ph in v['detected'].items():
        for p in ph:
            det.add((tag, int(w), mode, int(rep), p))


def key(n):
    l = lk[n]; t, tick, ph, w = l['pulse'].split(':'); return (t, int(w), l['mode'], l['rep'], int(ph))


r1_is_det = set(key(n) for n in r1) == det and len(r1) == len(det)
bl = [n for n in short if lk[n]['kind'] == 'baseline']
kinds = Counter(l['kind'] for l in L)
tbl = lambda tag, mode: [m5[f'{tag}|{w}|{mode}']['count'] for w in (5, 15, 25, 35, 45)]
def cnt(tag, mode, rep): return [c[rep] for c in tbl(tag, mode)]
C = []  # (id, text in body, source, value, expected)
def c(i, text, src, val, exp): C.append((i, text, src, val, exp))
c('N1','PLC scan 10 ms','M plc_scan_ms',M['plc_scan_ms'],10)
c('N2','plant tick 50 ms','M factory_tick_ms',M['factory_tick_ms'],50)
c('N3','5 scans per tick','M 50/10',M['factory_tick_ms']//M['plc_scan_ms'],5)
c('N4','0 physical runs','M physical_comparison',M['physical_comparison'],0)
c('N5','816 runs','R validity.ledger_rows',R['validity']['ledger_rows'],816)
c('N6','816 distinct run numbers','R validity.distinct_no',R['validity']['distinct_no'],816)
c('N7','408 combinations each ran twice','R validity.combos',R['validity']['combos'],408)
c('N8','0 invalid combinations','R validity.invalid_combos',R['validity']['invalid_combos'],0)
c('N9','in all 408 the two trace hashes were identical','R validity.rep_hash_mismatch (len)',len(R['validity']['rep_hash_mismatch']),0)
c('N10','No run returned a non-zero exit code','R validity.rc_nonzero (len)',len(R['validity']['rc_nonzero']),0)
c('N11','every run passed the child-process check','R validity.processes_not_pass (len)',len(R['validity']['processes_not_pass']),0)
c('N12','no run recorded an adapter hash different','R validity.adapter_sha_mismatch (len) / adapter_file_sha_ok',(len(R['validity']['adapter_sha_mismatch']),R['validity']['adapter_file_sha_ok']),(0,True))
c('N13','raised 0 exceptions','R metric2.*.reconstruct_exceptions (sum)',sum(v['reconstruct_exceptions'] for v in m2.values()),0)
c('N14','12 runs','L kind=plant',kinds['plant'],12)
c('N15','= 800 runs','L kind=pulse',kinds['pulse'],800)
c('N16','2 repetitions = 4 runs','L kind=baseline',kinds['baseline'],4)
c('N17','scenario of 1,000 ticks','L ticks (plant)',sorted({l['ticks'] for l in L if l['kind']=='plant'}),[1000])
c('N18','Each run is 200 ticks','L ticks (pulse/baseline)',sorted({l['ticks'] for l in L if l['kind']!='plant'}),[200])
c('N19','false alarm on the correct ladder 0/1','R metric1.false_alarm',R['metric1']['false_alarm'],[0,1])
c('N20','missed negative 0/2','R metric1.missed_negative',R['metric1']['missed_negative'],[0,2])
c('N21','| correct | 1 · [PASS] | 3 · [PASS] |','R metric1.detail.correct',R['metric1']['detail']['correct'],{'history':[1,'[PASS]'],'boundary':[3,'[PASS]']})
c('N22','| late-reverse | 5 · [FAIL] | 7 · [FAIL] |','R metric1.detail.late-reverse',R['metric1']['detail']['late-reverse'],{'history':[5,'[FAIL]'],'boundary':[7,'[FAIL]']})
c('N23','| swapped-sensors | 9 · [FAIL] | 11 · [FAIL] |','R metric1.detail.swapped-sensors',R['metric1']['detail']['swapped-sensors'],{'history':[9,'[FAIL]'],'boundary':[11,'[FAIL]']})
c('N24','The correct ladder produced no plant event','R metric3.correct',R['metric3']['correct'],{})
for lad in ('late-reverse','swapped-sensors'):
    e=R['metric3'][lad]['PART_DROP']
    c('N25-'+lad,'one `PART_DROP` under each condition (count difference 0)','R metric3.%s.PART_DROP count_history/boundary/diff'%lad,(e['count_history'],e['count_boundary'],e['count_diff']),(1,1,0))
    c('N26-'+lad,'runner tick 37 under restoration and tick 38 under boundary sampling (+1)','R metric3.%s.PART_DROP first_tick_*'%lad,(e['first_tick_history'],e['first_tick_boundary'],e['first_tick_diff']),(37,38,1))
for lad,n in (('correct',12),('late-reverse',3),('swapped-sensors',1)):
    v=m4[lad]
    c('N27-'+lad,'12 (correct), 3 (late-reverse), 1 (swapped-sensors)','R metric4.%s.changes_history/boundary'%lad,(v['changes_history'],v['changes_boundary']),(n,n))
    c('N28-'+lad,'+1 for 12 of 12, 3 of 3 and 1 of 1','R metric4.%s.tick_diff_hist, same_tag_value_order'%lad,(v['tick_diff_hist'],v['same_tag_value_order']),({'1':n},True))
c('N29','applied at tick 7 under restoration and tick 8','R metric4.correct.history_changes[0]/boundary_changes[0]',(m4['correct']['history_changes'][0],m4['correct']['boundary_changes'][0]),([7,'A.Mot.fwd',True],[8,'A.Mot.fwd',True]))
c('N30','the last reverse-off at tick 247 and 248','R metric4.correct.*_changes[-1]',(m4['correct']['history_changes'][-1],m4['correct']['boundary_changes'][-1]),([247,'A.Mot.rev',False],[248,'A.Mot.rev',False]))
c('N31','5 left-sensor and 6 right-sensor edges','R metric2.correct/*.per_tag.A.Sen.{left,right}',sorted({(m2[k]['per_tag']['A.Sen.left']['factory_edges'],m2[k]['per_tag']['A.Sen.left']['plc_transitions'],m2[k]['per_tag']['A.Sen.right']['factory_edges'],m2[k]['per_tag']['A.Sen.right']['plc_transitions']) for k in ('correct/history','correct/boundary')}),[(5,5,6,6)])
c('N32','The stop and emergency-stop inputs had no plant edges in this scenario','R metric2.*.per_tag.A.PB.{stop,estop}_nc.factory_edges (all)',sorted({m2[k]['per_tag'][t]['factory_edges'] for k in m2 for t in ('A.PB.stop_nc','A.PB.estop_nc')}),[0])
c('N33','On the two end sensors no edge pair was missed under either condition','R metric2.*.per_tag.(non-start).missed_pairs (all)',sorted({v['per_tag'][t]['missed_pairs'] for v in m2.values() for t in v['per_tag'] if t!='A.PB.start'}),[0])
c('N34','6 plant edges, of which 2 appeared as scan-input transitions and 2 edge pairs were missed','R metric2.*.per_tag.A.PB.start (all 8 runs)',sorted({(v['per_tag']['A.PB.start']['factory_edges'],v['per_tag']['A.PB.start']['plc_transitions'],v['per_tag']['A.PB.start']['missed_pairs']) for v in m2.values()}),[(6,2,2)])
c('N35','passed for every run and tag (0 mismatches)','R metric2.*.reconstructed_value_mismatches, per_tag.identity_ok',(sum(v['reconstructed_value_mismatches'] for v in m2.values()),all(t['identity_ok'] for v in m2.values() for t in v['per_tag'].values())),(0,True))
for tag in ('A.PB.stop_nc','A.PB.estop_nc'):
    for mode,exp in (('history',[5,10,10,10,10]),('boundary',[1,3,5,7,9])):
        row='| `%s` | %s | %s |'%(tag,mode,' | '.join(map(str,exp)))
        c('N36-%s-%s'%(tag,mode),row,'R metric5.%s|w|%s.count rep1,rep2'%(tag,mode),(cnt(tag,mode,'1'),cnt(tag,mode,'2')),(exp,exp))
for tag in ('A.Sen.left','A.Sen.right'):
    for mode in ('history','boundary'):
        row='| `%s` | %s | 0 | 0 | 0 | 0 | 0 |'%(tag,mode)
        c('N37-%s-%s'%(tag,mode),row,'R metric5.%s|w|%s.count rep1,rep2'%(tag,mode),(cnt(tag,mode,'1'),cnt(tag,mode,'2')),([0]*5,[0]*5))
c('N38','a 15 ms pulse in 3 of 10 phases, against 10 of 10','R metric5.A.PB.stop_nc|15|*.count',(m5['A.PB.stop_nc|15|boundary']['count']['1'],m5['A.PB.stop_nc|15|history']['count']['1']),(3,10))
c('N39','baselines were identical across repetitions','R baseline_reps_equal',R['baseline_reps_equal'],{'boundary':True,'history':True})
ep=R['edge_phase_ms']
c('N40','left sensor changed 22 ms after the tick start 2 times and 32 ms after it 3 times, and the right sensor 3 times at each','R edge_phase_ms.correct/*.A.Sen.*',sorted({json.dumps([ep[k]['A.Sen.left'],ep[k]['A.Sen.right']],sort_keys=True) for k in ('correct/history','correct/boundary')}),[json.dumps([{'22':2,'32':3},{'22':3,'32':3}],sort_keys=True)])
c('N41','the start button changed at 1, 2 and 3 ms, 2 times each','R edge_phase_ms.*.A.PB.start (all)',sorted({json.dumps(ep[k]['A.PB.start'],sort_keys=True) for k in ep}),[json.dumps({'1':2,'2':2,'3':2},sort_keys=True)])
c('N42','the right sensor changed once at 5 ms and once at 32 ms','R edge_phase_ms.{late-reverse,swapped-sensors}/*.A.Sen.right',sorted({json.dumps(ep[k]['A.Sen.right'],sort_keys=True) for k in ep if not k.startswith('correct')}),[json.dumps({'5':1,'32':1},sort_keys=True)])
c('N43','gives a tick difference of 0','K P2 대조 {0} / 실제 {1}',('차이 {0}' in K, '는 {1}' in K),(True,True))
c('N44','a 12 ms / 17 ms edge pair','K 지표 2 대조 12 ms·17 ms → 놓친 에지 쌍 1',('12 ms·17 ms' in K,'놓친 에지 쌍 1' in K),(True,True))
c('N45','marks phase 45 under boundary sampling and phases 5, 15, 25, 35 and 45','K 지표 5 대조 + R metric5.A.PB.stop_nc|5|*.detected',(m5['A.PB.stop_nc|5|boundary']['detected']['1'],m5['A.PB.stop_nc|5|history']['detected']['1']),([45],[5,15,25,35,45]))
c('N46','run twice and produced byte-identical result files','K 결정성 + sha of result json',sha(RES) in K,True)
c('N47','All 804 short-pulse and baseline runs have the summary verdict [FAIL]','R other_status_tally',sum(R['other_status_tally'].values()),804)
c('N48','The 4 pulse-free baselines and 520 pulse runs had completed 2 round trips','S probes (Rounds==2, Running) over runs 13-816',(len([n for n in r2 if n in bl]),len([n for n in r2 if n not in bl])),(4,520))
c('N49','the other 280 pulse runs','S probes (Rounds==1, not Running); equals R metric5 detected set run-by-run',(len(r1),r1_is_det),(280,True))
c('N50','No plant event occurred in any of the 804 runs','S event_count over runs 13-816',sum(S[n]['event_count'] for n in short),0)
c('N51','3 completed round trips in a 1,000-tick normal run','S probes.Rounds runs 1,3 (+ criteria-3k F1.3)',(S[1]['probes']['Rounds'],S[3]['probes']['Rounds']),(3,3))
c('N52','816 (12 plant-connected, 800 short-pulse, 4 baseline)','L count by kind',(len(L),kinds['plant'],kinds['pulse'],kinds['baseline']),(816,12,800,4))
c('N53','0 of 408','R validity.invalid_combos / combos',(R['validity']['invalid_combos'],R['validity']['combos']),(0,408))
c('N54','10:10:27–10:16:25 KST','L ended min/max',(min(l['ended'] for l in L)[11:],max(l['ended'] for l in L)[11:]),('10:10:27','10:16:25'))
c('N55','sum to 346.3 s','L sum(seconds)',round(sum(l['seconds'] for l in L),1),346.3)
c('N56','`ledger.jsonl` (816 rows','L line count',len(L),816)

# bundle-only checks (Section 8, v0.3)
TSV = [dict(zip(h.split('\t'), r.split('\t'))) for h in [open(BUNDLE + 'runs/tr02-official-1_files.tsv', encoding='utf-8').readline().strip()]
       for r in open(BUNDLE + 'runs/tr02-official-1_files.tsv', encoding='utf-8').read().splitlines()[1:]]
chg = Counter((os.path.basename(r['path']), r['changed'], r['replaced_prefixes']) for r in TSV)
c('B1', '7,346 files', 'B files.tsv rows', len(TSV), 7346)
c('B2', 'the 816 `metadata.json` files and the first line (run metadata) of the 816 `trace.jsonl` files, each with 10 path replacements',
  'B files.tsv changed=yes by name', sorted(k for k in chg if k[1] == 'yes'), [('metadata.json', 'yes', '10'), ('trace.jsonl', 'yes', '10')])
c('B3', 'the other 5,714 files are byte-identical', 'B files.tsv changed=no', sum(v for k, v in chg.items() if k[1] == 'no'), 5714)
PM = json.load(open(BUNDLE + 'scripts/redaction_map_public.json'))['prefixes']
c('B4', 'one local absolute directory prefix is replaced by the placeholder `<repos>/`', 'B redaction_map_public.json (placeholder only, no hash or length)',
  [(p['placeholder'], sorted(p)) for p in PM], [('<repos>/', ['placeholder', 'replaces'])])
pub = {r['path'].split('/', 1)[1]: r['sha256_public'] for r in TSV}
ok = all(hashlib.sha256(json.dumps([json.loads(x)['hash'] for x in open(RUN + nm, encoding='utf-8') if json.loads(x).get('type') == 'tick'],
         sort_keys=True, separators=(',', ':')).encode()).hexdigest() == lk[int(nm[:4])]['trace_hash'] for nm in pub if nm.endswith('trace.jsonl'))
c('B5', 'every trace hash in the ledger can be recomputed from the public traces', 'RUN */trace.jsonl tick hashes vs L trace_hash (816)', ok, True)
c('B6', 'runs 1 and 3', 'L lowest-numbered plant-connected correct pair', [min(l['no'] for l in L if l['kind'] == 'plant' and l['variant'] == 'correct' and l['mode'] == m) for m in ('history', 'boundary')], [1, 3])
fig = json.load(open(BUNDLE + 'figures/figure_values.json', encoding='utf-8'))
c('B7', 'The representative runs follow the pre-registration', 'B figure_values fig1/fig2 runs', (fig['fig1']['runs'], fig['fig2']['runs']), ({'history': 1, 'boundary': 3}, [1, 3]))
c('B8', 'the three listed in the pre-registration', 'B figures/*.png', len(glob.glob(BUNDLE + 'figures/*.png')), 3)
LINE = re.search(r"LINE = '(.*)\\n'\.encode\(\)", open(BUNDLE + 'ladders/공개본_변환.py', encoding='utf-8').read()).group(1)
c('V12', '`  "marker": "CONFIDENTIAL — WACE trade secret",`', 'B ladders/공개본_변환.py LINE, in body', LINE in body, True)
HASH = [('prereg', 'preregistration/TR-2026-02_사전등록_v0.3.md', '5e610e77633369fe5dd001af80451e58a09fe24699a3585065c13712eab217c4'),
        ('public correct', 'ladders/cell-a__correct.program.ldprog.json', 'c63691f6cdb5918bd05c421bb5a920b77ae3dd36592b95a99b3b5b6d743aea39'),
        ('public late-reverse', 'ladders/cell-a__late-reverse.program.ldprog.json', 'd19d4920d3590961840e30a02daf8173d8a3ca8c5dc6cadac90f66fd9574770c'),
        ('public swapped', 'ladders/cell-a__swapped-sensors.program.ldprog.json', 'ed7588886884fb4741d972f5b88b44f975f053221056fc8107d5f30c6986e1d3'),
        ('converter public', 'ladders/공개본_변환.py', 'c295e305d33277c9fd6265cf78d43122528b6a298f99b64416ea3481de94d660'),
        ('adapter public', 'adapter/TR-02_연결조건_어댑터.py', 'd837802aa993ec0f8b3aa141da6524c37b94bc17f278f7a2d2ef591bb5a882c2'),
        ('ledger', 'runs/ledger.jsonl', '80de3ea71eb82f76388a47f03122830e97eee0b0adcfd0d4a1ae7d5496ea79e6'),
        ('result json', 'results/TR-02_결과_tr02-official-1.json', 'f1838a4229247d12ea182a414cc30629e32dd4990cc26e3ac615668473bc6da3')]
for lbl, p, e in HASH:
    c('H-' + lbl, e, 'sha256 of bundle file', sha(BUNDLE + p), e)
for v, e in (('correct', '5058bd0b97644e66c0310a540a0403931bf6bd8195445576430d6dd1cabf8ef1'), ('late-reverse', '76018c387dddc09aa5411da241897c1ba20a4629844c301ccd3200140f1b7aa1'),
             ('swapped-sensors', '7fd10917b31949e24528fbc5398501cdd9852cda18537af07671c0d308e8c6e5')):
    p = open(BUNDLE + 'ladders/cell-a__%s.program.ldprog.json' % v, 'rb').read().split(b'\n'); p.insert(3, LINE.encode())
    c('H-run ' + v, e, 'sha256(public version + line 4)', hashlib.sha256(b'\n'.join(p)).hexdigest(), e)
c('H-adapter original', 'f5241b5f5d5286ff6366bdff33da8ec599e343d67ba6fd1ebaf129f1a7d10c40', 'R adapter_sha256 + every run tr02-adapter.json',
  (R['adapter_sha256'], R['validity']['adapter_sha_mismatch']), ('f5241b5f5d5286ff6366bdff33da8ec599e343d67ba6fd1ebaf129f1a7d10c40', []))
c('H-analysis', '`b1ca7dcd…`', 'R analysis_sha256', R['analysis_sha256'][:8], 'b1ca7dcd')
c('H-analysis public', '`a27ad316…`', 'sha256 scripts/TR-02_분석.py', sha(BUNDLE + 'scripts/TR-02_분석.py')[:8], 'a27ad316')
c('H-render', '`82a43131…`', 'R render_sha256 / bundle file', (R['render_sha256'][:8], sha(BUNDLE + 'scripts/TR02_분석_표.py')[:8]), ('82a43131', '82a43131'))
c('H-check', '(`0c20628e…`, byte-identical)', 'sha256 scripts/TR-02_리드독립검산.py', sha(BUNDLE + 'scripts/TR-02_리드독립검산.py')[:8], '0c20628e')
O = open(BUNDLE + 'results/recompute_metrics_1_2_output.txt', encoding='utf-8').read()
c('X1', 'reproduces the verdict of all 816 runs', 'B recompute output: verdicts recomputed / differing', ('816 run verdicts recomputed, 0 differ' in O, '[PASS] all equal' in O), (True, True))
c('X2', '8 of 8 entries equal the result file', 'B recompute output: metric 2', 'metric 2: 8/8 entries equal' in O, True)
c('X3', 'metric 1 equals the result file (false alarm 0/1, missed negatives 0/2)', 'B recompute output: metric 1', 'false alarm 0/1, missed negative 0/2 -> same as result file' in O, True)
bf = M['bridge_files']
c('H-runner original', '`4bbcfaf8…`', 'M bridge_files bridge/run.py', bf['bridge/run.py'][:8], '4bbcfaf8')
c('H-runner public', '`e0462ac1…`', 'sha256 runner_thin_layer/bridge/run.py', sha(BUNDLE + 'runner_thin_layer/bridge/run.py')[:8], 'e0462ac1')
c('H-thin identical', 'the last four are byte-identical and their hashes equal those in every run', 'sha256 of 3 bridge files vs M bridge_files; criteria vs M files',
  [sha(BUNDLE + 'runner_thin_layer/bridge/' + f) == bf['bridge/' + f] for f in ('transport.py', 'scenarios_3j.py', 'scenarios_3i.py')] + [sha(BUNDLE + 'runner_thin_layer/experiments/S2/criteria-3k.md') in M['files'].values()], [True] * 4)
c('H-criteria', '`295af9c0…`', 'sha256 criteria-3k.md', sha(BUNDLE + 'runner_thin_layer/experiments/S2/criteria-3k.md')[:8], '295af9c0')
c('H-official run public', '`9f93df96…`', 'sha256 scripts/TR-02_공식실행.py', sha(BUNDLE + 'scripts/TR-02_공식실행.py')[:8], '9f93df96')
m515 = [m5['A.PB.stop_nc|15|%s' % m]['count'] for m in ('boundary', 'history')]
c('X4', 'a 15 ms pulse was missed in 7 of 10 phases under boundary sampling and in 0 of 10 under restoration', 'R metric5.A.PB.stop_nc|15|*.count (10 - detected, both reps)',
  [[10 - v for v in sorted(x.values())] for x in m515], [[7, 7], [0, 0]])
TK = [json.loads(x) for n in sorted(lk) for x in open(RUN + lk[n]['name'] + '/trace.jsonl', encoding='utf-8') if '"type":"tick"' in x]
c('X5', 'all 172,800 recorded judgment lists are empty', 'RUN tick rows: count, total judgments', (len(TK), sum(len(r['judgments']) for r in TK)), (172800, 0))
del TK
aux = [(json.load(open(RUN + lk[n]['name'] + '/static.json'))['static'], len(json.load(open(RUN + lk[n]['name'] + '/reference-10ms-differences.json'))),
        os.path.getsize(RUN + lk[n]['name'] + '/plc-stderr.log')) for n in sorted(lk)]
c('X6', '[PASS] in all 816 runs, with its warnings', 'RUN */static.json static', Counter(a[0] for a in aux), Counter({'[PASS]': 816}))
c('X7', 'recorded only for the correct ladder; empty in all 816 runs', 'RUN */reference-10ms-differences.json length', Counter(a[1] for a in aux), Counter({0: 816}))
c('X8', '`plc-stderr.log` (empty in all 816 runs)', 'RUN */plc-stderr.log size', Counter(a[2] for a in aux), Counter({0: 816}))
c('N57', 'all four pre-registered predictions held', 'R predictions.P1..P4.verdict', [R['predictions'][p]['verdict'] for p in ('P1', 'P2', 'P3', 'P4')], ['[맞음]'] * 4)
lr = m4['late-reverse']
c('V1', 'forward drive went on at tick 7, and forward off and reverse on came together at tick 57', 'R metric4.late-reverse.history_changes', lr['history_changes'], [[7, 'A.Mot.fwd', True], [57, 'A.Mot.fwd', False], [57, 'A.Mot.rev', True]])
c('V2', '(restoration; 8 and 58 under boundary sampling)', 'R metric4.late-reverse.boundary_changes ticks', [x[0] for x in lr['boundary_changes']], [8, 58, 58])
c('V3', 'forward went off at tick 27 and reverse on at tick 32', 'R metric4.correct.history_changes[1:3]', m4['correct']['history_changes'][1:3], [[27, 'A.Mot.fwd', False], [32, 'A.Mot.rev', True]])
c('V4', 'metric 2 covers 8 runs', 'R metric2 keys / run fields', (len(m2), sorted(v['run'] for v in m2.values())), (8, [1, 3, 5, 7, 9, 11, 13, 15]))
c('V5', 'ended at 10:10:27 after 0.9 s', 'L run 1 ended, seconds', (lk[1]['ended'][11:], lk[1]['seconds']), ('10:10:27', 0.9))
COMMIT = datetime.datetime(2026, 9, 30, 8, 52, 18)  # G: public repository commit b743b0f, 2026-09-29T23:52:18Z
st = datetime.datetime.strptime(lk[1]['ended'], '%Y-%m-%d %H:%M:%S') - datetime.timedelta(seconds=lk[1]['seconds'])
c('V6', 'so it started at about 10:10:26 KST, about 78 minutes after the commit', 'L run 1 ended - seconds; G commit 08:52:18', (st.strftime('%H:%M:%S.%f')[:10], int((st - COMMIT).total_seconds() // 60)), ('10:10:26.1', 78))
c('V8', 'recomputed with a separately written script', 'I 280/520/4 lines + P1~P4 일치', ('→ 280 실행' in I, '→ 520 실행' in I, '→ 4 실행' in I, 'P1~P4 분석 결과와 일치' in I), (True, True, True, True))

NOT_FROM_BUNDLE = [
    ('first written at about 10:20 KST', "file-system creation time of the analysis script on the author's machine (10:20:30; table script 10:21:31)"),
    ('2026-09-30 08:52:18 KST (commit b743b0f)', 'G: public repository commit time (used above as a constant for V6)'),
    ('widths, phases, pulse tick 100, window 100-140, 2 repetitions, 2 retries, 109 manifest files, 0.6 m/s, 10-scan filter, 25-scan pause, 150-scan delay, 3 round trips', 'PR design constants'),
    ('T+110, T+20…T+50, + 90 ms, T+100, +2 ticks; T+120–T+140, T+150, (T+100, T+150]', "Section 4 notes (estimates) and the pre-registration's quoted derivation"),
]
if SELFTEST:
    for j, row in enumerate(C):
        if row[0] in ('N19', 'N36-A.PB.stop_nc-boundary', 'B3'):
            C[j] = row[:4] + ('perturbed',)
        if row[0] == 'X4':
            C[j] = ('X4', row[1] + ' (text not in report)') + row[2:]
rows, bad, missing = [], 0, 0
for i, text, src, val, exp in C:
    ok = (val == exp); intext = text in body
    bad += (not ok); missing += (not intext)
    rows.append((i, text, src, val, exp, ok, intext))
esc = lambda x: str(x).replace('|', '\\|')
out = ['# Number re-extraction: ' + os.path.basename(REPORT), '', f'- rows {len(C)} · value mismatches **{bad}** · text not found **{missing}**', '',
       '| # | text in report | source | value from bundle | expected | value | text |', '| --- | --- | --- | --- | --- | --- | --- |']
out += [f'| {i} | {esc(t)} | {esc(s)} | {esc(v)} | {esc(e)} | {"[PASS]" if o else "[FAIL]"} | {"[PASS]" if n else "[FAIL]"} |' for i, t, s, v, e, o, n in rows]
out += ['', '## Not re-extractable from the bundle', '', '| text | source |', '| --- | --- |'] + [f'| {esc(a)} | {esc(b)} |' for a, b in NOT_FROM_BUNDLE]
if TABLE:
    open(TABLE, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print(f'rows {len(C)} · value mismatches {bad} · text not found {missing}')
print('not re-extractable from the bundle:')
for a, b in NOT_FROM_BUNDLE:
    print('  -', a, '<-', b)
for r in rows:
    if not (r[5] and r[6]):
        print('[FAIL]', r[0], r[1][:60], r[3], r[4], 'text' if not r[6] else '')
if SELFTEST:
    ok = bad == 3 and missing == 1
    print('[PASS] negative control: 3 perturbed values and 1 missing text caught' if ok else '[FAIL] negative control')
    sys.exit(0 if ok else 1)
sys.exit(0 if bad == 0 and missing == 0 else 1)
