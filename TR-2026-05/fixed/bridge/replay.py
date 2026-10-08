"""TR-2026-05 열린 고리 재생(구현 목록 I10, 사전 등록 §6-3 · §7 P7 · §9 표 3) — 새로 씀.

F 연결 실행의 trace.jsonl 에서 틱마다 보낸 step 요청(Q · 자극)을 같은 순서로 다른 플랜트(M0, 래더 없음)에 다시 보낸다.
(run.py 는 set_constants 를 보내지 않으므로 재생할 set_constants 도 없다. 자극은 앱이 돌려준 전체 자극 상태를 그대로 보낸다 — F→F 재생의 틱 해시 일치로 확인.)
잰다: 센서 입력 태그별 상승 · 하강 에지 시각 차이(M − F, ms, F 에지 순서대로 짝, 짝 없는 F 에지 수), 부품별 최종 경로 일치, PART_DROP(셀 A),
셀 B 는 열린 고리 슈트 나이(교정 측정기와 같은 래더 엔진 짝짓기)가 원래 창 165~235 밖인 상자 수와 슈트 센서 하강이 없는 구간 수.
    python3 bridge/replay.py --source <F 실행 폴더> --out <폴더> --app <앱> [--physics mujoco]
    python3 bridge/replay.py --selftest [--app <앱> --runs <개발 기록> --out <폴더>]
"""
import argparse, json, statistics, sys, time
from pathlib import Path
from transport import Vision, canon, local_path
from common import app_path, sha, trace, write_json, Selftest
from run import cell_file, check_mode, source_tree
WINDOW=(165,235)
def edge_times(rows):
    """태그 → {'rise':[ms…], 'fall':[ms…]}(1 ms 분해능, 절대 시각)."""
    out={}
    for r in rows:
        dt=round(r['dt_s']*1000)
        for e in r['edges']:
            if isinstance(e['value'],bool):out.setdefault(e['tag'],{'rise':[],'fall':[]})['rise' if e['value'] else 'fall'].append((r['tick']-1)*dt+round(e['t_s']*1000))
    return out
def pair_table(f,m):
    """F 에지 순서대로 짝: k 번째 F 에지 ↔ k 번째 M 에지. 짝 없는 F 에지는 벗어난 것으로 친다(P7)."""
    table={}
    for tag in sorted(set(f)|set(m)):
        for d in ('rise','fall'):
            a=f.get(tag,{}).get(d,[]);b=m.get(tag,{}).get(d,[]);diff=[y-x for x,y in zip(a,b)]
            table[f'{tag}:{d}']=dict(f_edges=len(a),m_edges=len(b),pairs=len(diff),unpaired_f=max(0,len(a)-len(b)),unpaired_m=max(0,len(b)-len(a)),
                                     mean=statistics.mean(diff) if diff else None,median=statistics.median(diff) if diff else None,max_abs=max(map(abs,diff)) if diff else None,diffs=diff)
    return table
def p7_counts(table,tags=('B.Sen.atStopper','B.Sen.out','B.Sen.isBad'),tol=10):
    n=sum(table.get(f'{t}:rise',{}).get('f_edges',0) for t in tags);x=sum(sum(1 for d in table.get(f'{t}:rise',{}).get('diffs',[]) if abs(d)<=tol) for t in tags)
    return dict(n=n,within=x,chute_rise_diffs=table.get('B.Sen.chute:rise',{}).get('diffs',[]))

def replay(source,out,app,physics='mujoco',max_ticks=None,perturb=None):
    app=app_path(app).resolve();source=Path(source);meta=next(trace(source,('metadata',)));rows=trace(source)
    cell_name='cell-b' if meta['factory_tick_ms']==10 else 'cell-a';out=local_path(out);out.mkdir(parents=True,exist_ok=False)
    cell=cell_file(source_tree(app),cell_name,out,meta.get('belt_factor',1.0),meta.get('physics_values') or None,{'pusher.flow_restriction':True} if meta['scenario']=='flow' else None,meta.get('initial_z_offset',0.0))
    vision=Vision(app,cell,out,physics=physics,report_first_contact=physics=='fast' and '--report-first-contact' in (meta.get('app_flags') or []));rec=[];src_rows=[];same=True;first_diff=None;started=time.monotonic()
    try:
        current=vision.send(dict(cmd='load',cell=str(cell),seed=meta['seed'],defect_rate=meta['defect_rate']))
        mode=check_mode(out,physics,current['state'])
        if mode['status']!='[PASS]':raise RuntimeError(f'mode check failed: {mode}')
        with (out/'trace.jsonl').open('wb') as log:
            m=dict(type='metadata',schema='tr05-replay/1',source=str(source),source_trace_hash=None,physics_mode=physics,seed=meta['seed'],scenario=meta['scenario'],belt_factor=meta.get('belt_factor',1.0),factory_tick_ms=meta['factory_tick_ms'],load_physics=current['state'].get('physics'))
            log.write(canon(m)+b'\n')
            for r in rows:
                if max_ticks and r['tick']>max_ticks:break
                q=dict(r['Q'])
                if perturb and r['tick']==perturb[0]:q[perturb[1]]=not q[perturb[1]]
                resp=vision.send(dict(cmd='step',Q=q,stimuli=r['stimuli']))
                rr=dict(type='tick',tick=resp['tick'],dt_s=r['dt_s'],I_start=current['I'],I=resp['I'],Q=q,stimuli=resp['stimuli'],edges=resp['edges'],events=resp['events'],state=resp['state'],state_hash=sha(resp['state']))
                log.write(canon(rr)+b'\n');current=resp
                if rr['state_hash']!=r['state_hash'] or rr['I']!=r['I'] or rr['edges']!=r['edges']:
                    same=False;first_diff=first_diff or rr['tick']
                rec.append(dict(tick=rr['tick'],dt_s=rr['dt_s'],edges=rr['edges'],events=rr['events'],parts=[dict(id=p['id'],route=p['route'],cls=p['class']) for p in resp['state']['parts']]))
                src_rows.append(dict(tick=r['tick'],dt_s=r['dt_s'],edges=r['edges'],events=r['events'],parts=[dict(id=p['id'],route=p['route'],cls=p['class']) for p in r['state']['parts']]))
    finally:vision.close(True)
    table=pair_table(edge_times(src_rows),edge_times(rec));fr={p['id']:p['route'] for p in src_rows[-1]['parts']};mr={p['id']:p['route'] for p in rec[-1]['parts']}
    drops=lambda rs:[(r['tick'],e['name']) for r in rs for e in r['events'] if e['name']=='PART_DROP']
    summary=dict(type='summary',source=str(source),physics_mode=physics,ticks=len(rec),identical_to_source=same,first_different_tick=first_diff,edge_table=table,p7=p7_counts(table),
                 routes=dict(match=sum(fr[k]==mr.get(k) for k in fr),total=len(fr),F=fr,M=mr),part_drop=dict(F=drops(src_rows),M=drops(rec)),wall_s=time.monotonic()-started)
    if cell_name=='cell-b' and not max_ticks:
        from calibrate import extract, ladder_signals, ages, chute_full_intervals
        ex=extract(out);a=ages(ladder_signals(ex['images']),'chute');full=chute_full_intervals(ex)
        summary['chute']=dict(ages=a['ages'],outside_window=sum(1 for x in a['ages'] if not WINDOW[0]<=x<=WINDOW[1]),unpaired_arrivals=a['unpaired_arrivals'],ladder_first_lock_scan=a['ladder_first_lock_scan'],
                              no_fall_intervals=sum(1 for i in full if i['fall_ms'] is None),intervals=[{k:i[k] for k in ('start_tick','kind','scans','part')} for i in full])
    write_json(out/'summary.json',summary);return summary

def selftest(app=None,runs=None,out=None):
    T=Selftest('replay')
    f={'S':{'rise':[10,100,200],'fall':[50]}};m={'S':{'rise':[12,105],'fall':[60]}}
    t=pair_table(f,m)
    T.red_green('짝짓기: F 에지 순서대로, 짝 없는 F 에지는 따로 셈',lambda:t['S:rise']['unpaired_f']==0,lambda:t['S:rise']['pairs']==2 and t['S:rise']['unpaired_f']==1 and t['S:rise']['max_abs']==5 and t['S:fall']['median']==10)
    p=p7_counts(dict(**{'B.Sen.atStopper:rise':dict(f_edges=3,diffs=[0,10,11])}))
    T.check('P7 계수: 10 ms 이내 2/3(11 ms 는 벗어남)',p['n']==3 and p['within']==2)
    if app and runs and out:
        src=Path(runs)/'base-cell-b-fast';out=Path(out)
        T.red_green('F 기록을 F 플랜트로 재생하면 틱 해시가 원 실행과 같음(Q 한 틱을 바꾸면 달라짐)',lambda:replay(src,out/'ff-perturbed',app,'fast',max_ticks=400,perturb=(300,'B.Conv.run'))['identical_to_source'],
                    lambda:replay(src,out/'ff',app,'fast')['identical_to_source'])
        s=replay(src,out/'fm',app,'mujoco');at=s['edge_table']['B.Sen.atStopper:rise'];ch=s['edge_table']['B.Sen.chute:rise']
        T.check(f'시드 1 → M0: atStopper 상승 최대 {at["max_abs"]} ms(평균 {at["mean"]:.1f}), 슈트 짝 {ch["pairs"]}(평균 {ch["mean"]}), 경로 {s["routes"]["match"]}/{s["routes"]["total"]}',at['max_abs']<=10 and ch['pairs']==5 and s['routes']['match']==20)
    T.finish()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0]);ap.add_argument('--source',type=Path);ap.add_argument('--out',type=Path);ap.add_argument('--app',type=Path);ap.add_argument('--physics',choices=['fast','mujoco'],default='mujoco')
    ap.add_argument('--selftest',action='store_true');ap.add_argument('--runs',type=Path);a=ap.parse_args()
    if a.selftest:selftest(a.app,a.runs,a.out)
    if not (a.source and a.out):ap.error('--source 와 --out 필요')
    s=replay(a.source,a.out,a.app,a.physics);print('[PASS]' if s['ticks'] else '[FAIL]','replay',a.physics,'routes',s['routes']['match'],'/',s['routes']['total'],'identical',s['identical_to_source']);sys.exit(0)
