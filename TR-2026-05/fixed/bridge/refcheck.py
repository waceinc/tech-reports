"""TR-2026-05 참조 일치 계수(구현 목록 I7, 사전 등록 §3-5 · §8 ②)와 M1 참조 논리 매개변수표.

- 첫 잠금(FaultCode 가 처음 0 이 아닌 스캔) 전/뒤로 차이를 나눈다. 잠금 스캔 자체는 「뒤」(첫 잠금 전 = 틱 < 잠금 틱).
- §8 ② 예외 모양(문서화된 「생산 완료 뒤 1 스캔 빠른 정지」): 첫 잠금 전 차이 스캔 s 가 앞뒤 스캔과 붙지 않은 한 스캔이고,
  s 의 다른 태그 = {B.Conv.run, B.Lamp.green, B.Lamp.yellow}, 래더 B.Conv.run 0 · 참조 1, s+1 에서 세 태그 같음,
  s > (Arrivals 가 20 이 된 틱), |s − (마지막 Arrive 스캔 + 3000)| ≤ 1. 한 실행에서 첫째 하나만 빼고 둘째부터 센다.
- M1 참조 논리 = extctl logic.py Logic(True)(코드 그대로) + 매개변수표(obj.q 덮어쓰기). 바꾼 상수만 표에 넣는다.
    python3 bridge/refcheck.py <실행 폴더>        # trace.jsonl + reference-10ms-differences.json 으로 다시 계산
    python3 bridge/refcheck.py --selftest [--runs <개발 실행 폴더>]
"""
import argparse, importlib.util, json, math, sys
from pathlib import Path
from common import ROOT, trace, read_json, write_json, file_sha, sha, Selftest
SHAPE={'B.Conv.run','B.Lamp.green','B.Lamp.yellow'};NO_FEED=3000;DT=.01
def diff_tags(d):return {k for k in d['expected'] if d['expected'][k]!=d['actual'].get(k)}
def first_lock(rows):
    """첫 잠금: 스캔 탐침 FaultCode 가 처음 0 이 아닌 스캔. 래더가 없는 실행(scans 없음)은 None."""
    for r in rows:
        for s in r.get('scans') or []:
            code=s['probes'].get('FaultCode',0)
            if code:return dict(tick=r['tick'],scan=s['scan'],fault_code=code)
    return None
def arrivals(rows):
    """마지막 Arrive 스캔(Arrivals 가 늘어난 마지막 스캔)과 Arrivals 가 20 이 된 첫 스캔."""
    prev=0;last=None;t20=None
    for r in rows:
        for s in r.get('scans') or []:
            a=s['probes'].get('Arrivals',0)
            if a>prev:last=s['scan']
            if a>=20 and t20 is None:t20=s['scan']
            prev=a
    return last,t20
def split(diffs,rows,no_feed=NO_FEED):
    lock=first_lock(rows);lock_scan=lock['scan'] if lock else math.inf
    before=[d for d in diffs if d['scan']<lock_scan];after=[d for d in diffs if d['scan']>=lock_scan]
    last,t20=arrivals(rows);scans={d['scan'] for d in before};exempt=None;shape_hits=[]
    for d in before:
        s=d['scan'];tags=diff_tags(d)
        ok=(tags==SHAPE and d['actual']['B.Conv.run'] in (0,False) and d['expected']['B.Conv.run'] in (1,True) and s-1 not in scans and s+1 not in scans
            and t20 is not None and s>t20 and last is not None and abs(s-(last+no_feed))<=1)
        if ok:shape_hits.append(s)
        if ok and exempt is None:exempt=dict(tick=d['tick'],scan=s,tags=sorted(tags),last_arrive_scan=last,arrivals20_scan=t20)
    counted=[d for d in before if not exempt or d['scan']!=exempt['scan']]
    by_tag={}
    for d in after:
        for t in diff_tags(d):by_tag[t]=by_tag.get(t,0)+1
    return dict(first_lock=lock,before_lock=len(counted),before_lock_first=[dict(tick=d['tick'],scan=d['scan'],tags=sorted(diff_tags(d))) for d in counted[:5]],
                exception=exempt,exception_shape_scans=shape_hits,after_lock=len(after),after_lock_by_tag=by_tag,total=len(diffs),
                invalid=len(counted)>0)

# M1 참조 논리 매개변수표: 래더 상수(스캔 정수) → cell_design 이름(초). 정수 창과 같게 판정하도록 반 스캔 안쪽 여유를 둔다.
ORIGINAL=dict(chute_window=[165,235],chute_full_scans=45,fire_delay_sub=7)
def m1_reference_params(constants,design=None):
    design=design or read_json(ROOT/'cells/3i-parameters.json');c=dict(ORIGINAL,**constants);table={}
    if list(c['chute_window'])!=ORIGINAL['chute_window']:
        lo,hi=c['chute_window'];assert 0<lo<=hi,('chute window',lo,hi)
        table['chute_confirm_delay_s']=(lo+hi)/2*DT;table['chute_confirm_tolerance_s']=((hi-lo)/2+.25)*DT
    if c['chute_full_scans']!=ORIGINAL['chute_full_scans']:table['full_hold_s']=(c['chute_full_scans']-.5)*DT
    n=ORIGINAL['fire_delay_sub']-c['fire_delay_sub']
    if n:table['fall_delay_s']=design['fall_delay_s']+n*DT;table['fire_lag_s']=design['fire_lag_s']-n*DT  # 계수 232(=합) 그대로, 뺄셈만 n 스캔
    for k in table:assert k in design,('cell_design 에 없는 이름',k)
    return dict(schema='tr05-m1-reference-params/1',constants=c,q_overrides=table)
def window_equivalent(lo,hi,delay,tol,clocks=range(0,30000,7)):
    """참조 논리의 실수 비교가 정수 창 [lo, hi] 와 모든 나이에서 같은가(시험용)."""
    return all((not abs((a+g)*DT-a*DT-delay)>tol)==(lo<=g<=hi) for a in clocks for g in range(lo-5,hi+6))
def load_logic(src):
    path=Path(src)/'native/tests/external_control/logic.py';spec=importlib.util.spec_from_file_location('tr05_reference',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod,path
# 사전 등록 개정 1(2026-10-08, sha256 8b68148f…): F · M0 의 참조 논리도 M1 과 같은 반 스캔 안쪽 여유로 창 경계를 비교한다.
# 대상 = 래더의 정수 상수를 실수(초)로 비교하는 항목: 슈트 확인 창 165~235 · 출력 확인 창 198~269 · 슈트 가득 45. 상수 값(스캔)은 그대로다.
LADDER_WINDOWS=dict(chute=(165,235),out=(198,269));LADDER_FULL=45
def base_margin(q):
    """원래 cell_design 값이 래더 정수 상수와 같은 창을 뜻하는지 확인하고, 반 스캔 안쪽 여유 표기로 바꾼 값을 돌려준다."""
    t={}
    for kind,(lo,hi) in LADDER_WINDOWS.items():
        d,tol=q[f'{kind}_confirm_delay_s'],q[f'{kind}_confirm_tolerance_s']
        if not (abs((d-tol)/DT-lo)<1 and abs((d+tol)/DT-hi)<1):raise ValueError(f'{kind} 창 {d}±{tol} 가 래더 {lo}~{hi} 와 1 스캔 넘게 다름')  # 래더의 정수 상수가 기준(출력 창은 설계 1.983~2.683 s 를 198~269 로 적음)
        t[f'{kind}_confirm_delay_s']=(lo+hi)/2*DT;t[f'{kind}_confirm_tolerance_s']=((hi-lo)/2+.25)*DT
    if round(q['full_hold_s']/DT)!=LADDER_FULL:raise ValueError('슈트 가득 상수가 래더와 다름')
    t['full_hold_s']=(LADDER_FULL-.5)*DT
    return t
def reference(src,b,scale=1,params=None,expect_logic_sha=None,margin=True):
    """F · M0 = 원래 상수(개정 1: 반 스캔 안쪽 여유 표기), M1 = 그 위에 매개변수표. 코드 줄이 같음 = logic.py 파일 sha256 이 같음(기대값을 주면 확인).
    margin=False 는 개정 전 동작(자기 시험의 음성 대조 전용)."""
    mod,path=load_logic(src);digest=file_sha(path)
    if expect_logic_sha and digest!=expect_logic_sha:raise RuntimeError(f'logic.py sha256 {digest} ≠ 고정값 {expect_logic_sha}')
    obj=mod.Logic(b)
    if not b:obj.cfg={k:v*scale for k,v in obj.cfg.items()}
    obj.tr05_margin=None
    if b and margin:obj.tr05_margin=base_margin(obj.q);obj.q.update(obj.tr05_margin)
    if params:
        if not b:raise ValueError('M1 참조 매개변수는 셀 B 에만')
        for k,v in params['q_overrides'].items():
            if k not in obj.q:raise KeyError(k)
            obj.q[k]=v
    obj.tr05_logic_sha256=digest;obj.tr05_params_sha256=sha(params) if params else None
    return obj

def from_run(run_dir):
    rows=list(trace(run_dir));diffs=read_json(Path(run_dir)/'reference-10ms-differences.json');return split(diffs,rows)

def replay_reference(run_dir,margin):
    """기록된 센서 이미지를 참조 논리에 넣어 래더 Q(기록)와 처음 다른 스캔과 래더 첫 잠금 스캔을 찾는다(run.py 와 같은 비교)."""
    from run import reconstruct, source_tree
    meta=next(trace(run_dir,('metadata',)));ref=reference(source_tree(meta['app']),True,1,None,margin=margin);lock=None
    for r in trace(run_dir):
        for sc,I in zip(r['scans'],reconstruct(r['I_start'],r)):
            if lock is None and sc['probes'].get('FaultCode'):lock=sc['scan']
            if ref.step(I)!=sc['Q']:return dict(first_diff=sc['scan'],lock=lock)
        if lock and r['tick']>lock+5:break
    return dict(first_diff=None,lock=lock)
def selftest(runs=None,case=None):
    T=Selftest('refcheck')
    def row(tick,arr,code=0):return dict(tick=tick,scans=[dict(scan=tick,probes=dict(Arrivals=arr,FaultCode=code))])
    rows=[row(t,min(20,t//70)) for t in range(1,4600)]  # 20 번째 Arrive 1400 → 정지 4400
    E={'B.Conv.run':True,'B.Lamp.green':True,'B.Lamp.yellow':False,'B.Lamp.red':False};A=dict(E,**{'B.Conv.run':False,'B.Lamp.green':False,'B.Lamp.yellow':True})
    good=[dict(tick=4400,scan=4400,expected=E,actual=A)]
    other=[dict(tick=4400,scan=4400,expected=E,actual=dict(E,**{'B.Lamp.red':True}))]  # 다른 태그 한 스캔 차이
    T.red_green('다른 태그 한 스캔 차이는 예외로 빠지지 않음 / 문서화된 모양은 빠짐',lambda:not split(other,rows)['invalid'],lambda:split(good,rows)['exception'] and not split(good,rows)['invalid'])
    late=[dict(good[0],tick=4410,scan=4410)]
    T.red_green('마지막 Arrive + 3000 ± 1 밖이면 예외 아님',lambda:not split(late,rows)['invalid'],lambda:not split(good,rows)['invalid'])
    two=good+[dict(good[0],tick=4402,scan=4402)]
    T.red_green('예외 모양이 둘이면 둘째부터 셈',lambda:not split(two,rows)['invalid'],lambda:split(two,rows)['before_lock']==1)
    locked=[row(t,5,3 if t>=1710 else 0) for t in range(1,5001)];after=[dict(tick=t,scan=t,expected=dict(E,**{'B.Lamp.yellow':True}),actual=dict(E,**{'B.Lamp.red':True})) for t in range(1710,5001)]
    early=[dict(after[0],tick=1709,scan=1709)]+after
    T.red_green('잠금 전 차이는 무효 / 잠금 뒤 차이는 보고만',lambda:not split(early,locked)['invalid'],lambda:(lambda r:not r['invalid'] and r['after_lock']==3291 and r['before_lock']==0)(split(after,locked)))
    p=m1_reference_params(dict(chute_window=[150,251],chute_full_scans=60,fire_delay_sub=5))
    q=p['q_overrides']
    T.red_green('M1 창 매개변수가 정수 창과 같음(여유 없는 표기는 어긋남)',lambda:window_equivalent(150,251,2.005,.505),lambda:window_equivalent(150,251,q['chute_confirm_delay_s'],q['chute_confirm_tolerance_s']))
    T.check('슈트 가득 · 발사 지연 매개변수(계수 합 0.232 유지)',all(((n*DT>=q['full_hold_s'])==(n>=60)) for n in range(200)) and abs(q['fall_delay_s']+q['fire_lag_s']-.232)<1e-12 and abs(q['fire_lag_s']-.06)<1e-12)
    T.check('원래 상수면 매개변수표가 비어 있음',m1_reference_params({})['q_overrides']=={})
    q=dict(chute_confirm_delay_s=2.0,chute_confirm_tolerance_s=.35,out_confirm_delay_s=2.3333333333333335,out_confirm_tolerance_s=.35,full_hold_s=.45);m=base_margin(q)
    T.red_green('개정 1: 원래 출력 창 2.333±0.35 는 정수 창 198~269 와 어긋남 / 여유 표기는 같음',lambda:window_equivalent(198,269,q['out_confirm_delay_s'],q['out_confirm_tolerance_s']),
                lambda:window_equivalent(198,269,m['out_confirm_delay_s'],m['out_confirm_tolerance_s']) and window_equivalent(165,235,m['chute_confirm_delay_s'],m['chute_confirm_tolerance_s']) and all((n*DT>=m['full_hold_s'])==(n>=45) for n in range(200)))
    if case:
        r0=replay_reference(case,False);r1=replay_reference(case,True)
        T.red_green(f'개정 1: 개발 시드 사례(래더 첫 잠금 {r1["lock"]}) — 여유 없으면 참조가 {r0["first_diff"]} 에 먼저 다름 / 여유 있으면 첫 잠금 전 차이 0',
                    lambda:r0['first_diff'] is None or (r0['lock'] is not None and r0['first_diff']>=r0['lock']),lambda:(r1['first_diff'] is None or r1['first_diff']>=r1['lock']) and r1['lock']==1697)
    if runs:
        runs=Path(runs)
        for s in (1,2,3):
            d=runs/f'gate-fast-1/cell-b-seed{s}/r1'
            if d.exists():r=from_run(d);T.check(f'F 게이트 시드 {s}: 예외 1건(틱 {r["exception"] and r["exception"]["tick"]}), 그 밖 0',r['exception'] and r['exception']['tick']==4461 and r['before_lock']==0)
        d=runs/'dev-b-m0-normal/r1'
        if d.exists():r=from_run(d);T.check(f'시드 1 M0: 첫 잠금 {r["first_lock"]}, 전 {r["before_lock"]} · 뒤 {r["after_lock"]} {r["after_lock_by_tag"]}',r['first_lock']['tick']==1710 and r['before_lock']==0 and r['after_lock']==3291 and set(r['after_lock_by_tag'])=={'B.Lamp.red','B.Lamp.yellow'})
    T.finish()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0]);ap.add_argument('run',nargs='?',type=Path);ap.add_argument('--selftest',action='store_true');ap.add_argument('--runs',type=Path);ap.add_argument('--case',type=Path,help='개정 1 사례 실행 폴더');a=ap.parse_args()
    if a.selftest:selftest(a.runs,a.case)
    r=from_run(a.run);print(json.dumps(r,ensure_ascii=False,indent=1));sys.exit(1 if r['invalid'] else 0)
