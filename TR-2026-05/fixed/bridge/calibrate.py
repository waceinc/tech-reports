"""TR-2026-05 교정 측정기(구현 목록 I11, 사전 등록 §6-1 M1 재교정 규칙 · §9 표 8) — 새로 씀.

기록(trace.jsonl)의 센서 이미지를 원래 3i 정답 래더 엔진(probe_engine.mjs → engine.mjs)에 입력으로만 넣어 Arrive · 필터된 Chute · Out 을 읽고
(Q 는 버림, 래더 밖에서 필터를 다시 만들지 않음), 아래 규칙으로 새 상수를 낸다. 규칙이 낸 값을 사람이 고치지 않는다.
- 슈트 확인 창: 불량 Arrive ↔ 필터된 Chute 상승(ExpectChute FIFO 순서) 나이. 새 창 = [a_M − m_lo, b_M + m_hi], m_lo = max(0, a_F − 165), m_hi = max(0, 235 − b_F). 짝 < 3 이면 그대로.
- 슈트 가득: 원신호 B.Sen.chute ON 구간 중 「지나간 구간」(상승 · 하강이 실행 안, 하강 순간 그 상자 경사 방향 속도 > 0.05 m/s, 수거로 끝나지 않음)의 최대 스캔 수.
  새 값 = max(45, ⌈45 × M/F⌉), 90 초과면 「재교정 불가」 → 45. F 가 0 이거나 어느 쪽이든 구간 < 3 이면 그대로.
- 발사 지연: 밀린 불량 상자의 첫 판-상자 접촉 x(M first_contact[], F fast_first_contact). Δx = 중앙값(x_M) − 중앙값(x_F) < 0 이면 7 − ⌈|Δx| ÷ 0.012⌉, 아니면 7.
- 바꾸지 않는 상수(양품 창 198~269 · 도착 ON 29 · 출력 가득 100)는 재서 보고만. 교정 시드의 F 연결 실행이 [PASS] 가 아니면 그 시드는 건너뛴다.
    python3 bridge/calibrate.py --pair <시드> <F 연결 실행 폴더> <M 열린 고리 재생 폴더> [...] --out <보고서.json>   # 동결 뒤에만(교정)
    python3 bridge/calibrate.py --selftest [--runs <개발 기록 폴더>]
"""
import argparse, json, math, statistics, subprocess, sys
from pathlib import Path
from common import ROOT, trace, field, MissingField, first_contacts, read_json, write_json, Selftest
from run import reconstruct
COS=math.cos(math.radians(20.0));SENSORS=('B.Sen.atStopper','B.Sen.chute','B.Sen.out','B.Sen.isBad');SENSOR_Z=1.503;V_PASS=.05;ORIG=dict(chute_window=[165,235],chute_full_scans=45,fire_delay_sub=7)
READ=['Arrive','Chute','Out','At','Running','FaultCode','ExpectChuteN','ChuteArrivals','ExpectOutN','OutArrivals','Arrivals']
def extract(run_dir):
    """기록에서 이미지 · 센서 에지(1 ms) · 슈트 쪽 부품(route 1 · 4)의 z · 경사 방향 속도 · 경로 변화 · 끝 상태를 뽑는다."""
    ex=dict(images=[],edges={t:[] for t in SENSORS},chute_parts={},routes=[],last=None,meta=None,summary=None,velocity_source=set());prev={}
    for r in trace(run_dir,None):
        if r['type']=='metadata':ex['meta']=r;continue
        if r['type']=='summary':ex['summary']=r;continue
        t=r['tick'];dt=round(r['dt_s']*1000);ex['images']+=reconstruct(r['I_start'],r)
        for e in r['edges']:
            if e['tag'] in ex['edges']:ex['edges'][e['tag']].append(((t-1)*dt+round(e['t_s']*1000),e['value']))
        st=r['state'];pp=None
        if 'physics' in st:
            try:pp={str(field(p,'id')):p for p in st['physics']['parts']} if 'parts' in st['physics'] else None
            except MissingField:pp=None
        rows=[]
        for p in st['parts']:
            if prev.get(p['id'],p['route'])!=p['route']:ex['routes'].append((t,p['id'],prev[p['id']],p['route']))
            prev[p['id']]=p['route']
            if p['route'] in (1,4):
                v=None
                if pp is not None and p['id'] in pp:
                    try:v=float(field(pp[p['id']],'v_slope'));ex['velocity_source'].add('state.physics.parts')
                    except MissingField:v=None
                if v is None:v=p.get('vz',0.0)/COS;ex['velocity_source'].add('state.parts.vz/cos20')
                rows.append((p['id'],p['route'],p['z'],v))
        ex['chute_parts'][t]=rows;ex['last']=st
    ex['velocity_source']=sorted(ex['velocity_source']);return ex

def ladder_signals(images,program=ROOT/'ladders/cell-b/correct/program.ldprog.json'):
    """원래 정답 래더 엔진에 이미지를 입력으로만 넣고 내부 태그를 읽는다(래더 Q 는 버림)."""
    lines=[json.dumps(dict(read=READ))]+[json.dumps(i) for i in images]
    p=subprocess.run(['node',str(ROOT/'bridge/probe_engine.mjs'),str(program)],input='\n'.join(lines)+'\n',capture_output=True,text=True,cwd=ROOT,check=False)
    if p.returncode:raise RuntimeError('probe_engine: '+p.stderr[-800:])
    out=[json.loads(l) for l in p.stdout.splitlines()[1:]];return [dict(scan=o[0],**dict(zip(READ,o[1:]))) for o in out]

def ages(sig,kind='chute'):
    """FIFO 짝짓기: 불량(양품) Arrive 스캔을 대기열에, 필터된 Chute(Out) 상승마다 맨 앞과 짝. 나이 = 상승 − Arrive(스캔)."""
    N,C,S={'chute':('ExpectChuteN','ChuteArrivals','Chute'),'out':('ExpectOutN','OutArrivals','Out')}[kind];q=[];res=[];unmatched=0;prev=None;lock=None
    for s in sig:
        if lock is None and s['FaultCode']:lock=s['scan']
        if lock is not None:break  # 리드 결정 ③: 래더 첫 잠금까지만 잰다(잠금 뒤 Running 이 꺼져 Arrive 가 나오지 않음). 그 뒤 상자는 미측정으로 보고
        if prev is not None:
            if s['Arrive'] and (s[N]-prev[N])+(s[C]-prev[C])>=1:q.append(s['scan'])
            if s[S] and not prev[S]:
                if q:res.append(s['scan']-q.pop(0))
                else:unmatched+=1
        prev=s
    return dict(ages=res,unpaired_arrivals=len(q),unmatched_rises=unmatched,ladder_first_lock_scan=lock,measured_until_scan=lock or (sig[-1]['scan'] if sig else 0))
def intervals(edges,end_ms):
    on=None;out=[]
    for ms,v in edges:
        if v and on is None:on=ms
        elif not v and on is not None:out.append((on,ms));on=None
    if on is not None:out.append((on,None))
    return out
def scans(a,b):return math.ceil(b/10)-math.ceil(a/10)
def chute_full_intervals(ex):
    """원신호 슈트 센서 ON 구간 분류 — passed · 띠 안 정지 · 실행 끝 · 수거. 상자 = 하강(또는 끝) 틱에 센서 z 에 가장 가까운 슈트 부품."""
    end=len(ex['images'])*10;res=[]
    for a,b in intervals(ex['edges']['B.Sen.chute'],end):
        t=math.ceil((b if b is not None else end)/10);cand=ex['chute_parts'].get(t) or ex['chute_parts'].get(t-1) or []
        box=min(cand,key=lambda c:abs(c[2]-SENSOR_Z)) if cand else None
        collected=box is not None and any(pid==box[0] and new==4 and math.ceil(a/10)<=tt<=t+1 for tt,pid,old,new in ex['routes'])
        if b is None:kind='실행 끝' if box and abs(box[3])>V_PASS else '띠 안 정지'
        elif collected:kind='수거'
        elif box is None or box[3]<=V_PASS:kind='띠 안 정지'
        else:kind='passed'
        res.append(dict(rise_ms=a,fall_ms=b,scans=scans(a,b) if b is not None else None,kind=kind,part=box[0] if box else None,v_slope=box[3] if box else None,start_tick=math.ceil(a/10)))
    return res
def on_widths(ex,tag):return [scans(a,b) for a,b in intervals(ex['edges'][tag],len(ex['images'])*10) if b is not None]
def contact_x(ex,fast):
    st=ex['last'];fc=first_contacts(st,fast);bad={p['id'] for p in st['parts'] if p['class']}
    return [float(field(c,'x',__import__('common').CONTACT_KEYS,'first_contact')) for pid,c in fc.items() if pid in bad]

def rule_window(F,M,orig=ORIG['chute_window']):
    if len(F)<3 or len(M)<3:return dict(value=list(orig),changed=False,reason=f'짝 < 3 (F {len(F)} · M {len(M)})')
    aF,bF,aM,bM=min(F),max(F),min(M),max(M);mlo=max(0,aF-orig[0]);mhi=max(0,orig[1]-bF);new=[aM-mlo,bM+mhi]
    return dict(value=new,changed=new!=list(orig),F=[aF,bF],M=[aM,bM],m_lo=mlo,m_hi=mhi,median_delta=statistics.median(M)-statistics.median(F),width_change=(new[1]-new[0])-(orig[1]-orig[0]),
                outside_original=sum(1 for x in M if not orig[0]<=x<=orig[1]))
def rule_full(F,M,base=ORIG['chute_full_scans'],cap=90):
    if len(F)<3 or len(M)<3 or not max(F,default=0):return dict(value=base,changed=False,reason=f'지나간 구간 < 3 또는 F 0 (F {len(F)} · M {len(M)})')
    v=max(base,math.ceil(base*max(M)/max(F)))
    if v>cap:return dict(value=base,changed=False,reason=f'재교정 불가 — {v} > 상한 {cap}',computed=v,F=max(F),M=max(M))
    return dict(value=v,changed=v!=base,F=max(F),M=max(M))
def rule_fire(xF,xM,base=ORIG['fire_delay_sub']):
    if not xF or not xM:return dict(value=base,changed=False,reason=f'첫 접촉 기록 없음(F {len(xF)} · M {len(xM)})')
    dx=statistics.median(xM)-statistics.median(xF);v=base-math.ceil(abs(dx)/(1.2*.01)) if dx<0 else base
    return dict(value=v,changed=v!=base,dx=dx,median_F=statistics.median(xF),median_M=statistics.median(xM),n_F=len(xF),n_M=len(xM))

def measure(run_dir,fast):
    ex=extract(run_dir);sig=ladder_signals(ex['images']);ch=ages(sig,'chute');ot=ages(sig,'out');full=chute_full_intervals(ex)
    try:cx=contact_x(ex,fast);cerr=None
    except MissingField as e:cx=[];cerr=str(e)
    nbad=sum(1 for p in (ex['last'] or {}).get('parts',[]) if p['class']);ngood=len((ex['last'] or {}).get('parts',[]))-nbad
    ch['unmeasured_after_lock']=max(0,nbad-len(ch['ages'])-ch['unpaired_arrivals']) if ch['ladder_first_lock_scan'] else 0
    ot['unmeasured_after_lock']=max(0,ngood-len(ot['ages'])-ot['unpaired_arrivals']) if ot['ladder_first_lock_scan'] else 0
    return dict(run=str(run_dir),chute=ch,out=ot,chute_on=full,passed=[i['scans'] for i in full if i['kind']=='passed'],excluded=[dict(kind=i['kind'],start_tick=i['start_tick'],part=i['part']) for i in full if i['kind']!='passed'],
                at_on_max=max(on_widths(ex,'B.Sen.atStopper'),default=0),out_on_max=max(on_widths(ex,'B.Sen.out'),default=0),contact_x=cx,contact_error=cerr,velocity_source=ex['velocity_source'],summary_status=(ex['summary'] or {}).get('status'))
def calibrate(pairs):
    used=[];skipped=[];F=dict(ch=[],out=[],full=[],x=[],at=[],o=[]);M=dict(ch=[],out=[],full=[],x=[],at=[],o=[])
    for seed,fdir,mdir in pairs:
        f=measure(Path(fdir),True)
        if f['summary_status']!='[PASS]':skipped.append(dict(seed=seed,F=f['summary_status']));continue
        m=measure(Path(mdir),False);used.append(dict(seed=seed,F=f,M=m))
        for D,x in ((F,f),(M,m)):D['ch']+=x['chute']['ages'];D['out']+=x['out']['ages'];D['full']+=x['passed'];D['x']+=x['contact_x'];D['at'].append(x['at_on_max']);D['o'].append(x['out_on_max'])
    new=dict(chute_window=rule_window(F['ch'],M['ch']),chute_full_scans=rule_full(F['full'],M['full']),fire_delay_sub=rule_fire(F['x'],M['x']))
    report_only=dict(out_window=dict(limit=[198,269],F=[min(F['out'],default=None),max(F['out'],default=None)],M=[min(M['out'],default=None),max(M['out'],default=None)],near_limit=max(M['out'],default=0)>=269-3),
                     arrival_on=dict(limit=29,F=max(F['at'],default=None),M=max(M['at'],default=None),near_limit=max(M['at'],default=0)>=29-3),output_full=dict(limit=100,F=max(F['o'],default=None),M=max(M['o'],default=None)))
    return dict(schema='tr05-calibration/1',constants={k:v['value'] for k,v in new.items()},rules=new,report_only=report_only,used=used,skipped=skipped)

def selftest(runs=None):
    T=Selftest('calibrate')
    T.red_green('슈트 창 감싸기: 짝 < 3 이면 그대로 / F [170,230] · M [180,300] → [175,305]',lambda:rule_window([170,230],[180,300])['changed'],lambda:rule_window([170,200,230],[180,250,300])['value']==[175,305])
    T.red_green('슈트 가득: ⌈45×M/F⌉, 상한 90 초과는 재교정 불가(45)',lambda:rule_full([20,18,19],[70,60,50])['value']!=45,lambda:rule_full([20,18,19],[30,25,22])['value']==68 and rule_full([20,18,19],[70,60,50])['reason'].startswith('재교정 불가'))
    T.red_green('발사 지연: Δx −0.03 m → 7−3=4, Δx ≥ 0 은 그대로',lambda:rule_fire([0.0],[0.01])['changed'],lambda:rule_fire([0.0,0.0],[-0.03,-0.03])['value']==4 and rule_fire([0.0],[0.01])['value']==7)
    ex=dict(images=[0]*300,edges={'B.Sen.chute':[(100,True),(400,False),(1000,True),(1300,False),(2000,True)]},chute_parts={40:[('p1',1,1.5,.8)],130:[('p2',1,1.5,0.0)],300:[('p3',1,1.5,0.0)]},routes=[])
    k=[i['kind'] for i in chute_full_intervals(ex)]
    T.check(f'지나간 구간 분류(합성): {k}',k==['passed','띠 안 정지','띠 안 정지'])
    def sg(n,lock_at=None):
        out=[];arr=[];cn=0
        for i in range(1,n+1):
            a=i%100==10;c=i%100==60 and i>100
            cn+=a;out.append(dict(scan=i,Arrive=a,Chute=c,Out=False,FaultCode=3 if lock_at and i>=lock_at else 0,ExpectChuteN=cn,ChuteArrivals=0,ExpectOutN=0,OutArrivals=0))
        return out
    T.red_green('첫 잠금까지만 잼: 잠금 뒤 상승은 짝짓지 않음',lambda:len(ages(sg(1000,450))['ages'])==len(ages(sg(1000))['ages']),lambda:ages(sg(1000,450))['measured_until_scan']==450 and len(ages(sg(1000,450))['ages'])<len(ages(sg(1000))['ages']))
    if runs:
        runs=Path(runs);d=runs/'gate-fast-1/cell-b-seed1/r1'
        if d.exists():
            ex=extract(d);sig=ladder_signals(ex['images']);rec=[r['scans'][0]['probes']['Arrivals'] for r in trace(d)]
            T.red_green('래더 엔진 재생의 Arrivals 가 F 연결 실행의 탐침 기록과 스캔마다 같음(atStopper 를 6 스캔 바꾸면 어긋남)',
                lambda:(lambda im:[s['Arrivals'] for s in ladder_signals(im)]==rec)([dict(i,**{'B.Sen.atStopper':not i['B.Sen.atStopper']}) if 700<=n<706 else i for n,i in enumerate(ex['images'])]),
                lambda:[s['Arrivals'] for s in sig]==rec)
            a=ages(sig);T.check(f'F 시드 1: 불량 짝 {len(a["ages"])}, 나이 {min(a["ages"],default=None)}~{max(a["ages"],default=None)}(값은 쓰지 않음), 짝 없는 Arrive {a["unpaired_arrivals"]}',len(a['ages'])==5 and a['ladder_first_lock_scan'] is None)
            full=chute_full_intervals(ex);T.check(f'F 시드 1: 슈트 ON 구간 {len(full)} 모두 passed',all(i['kind']=='passed' for i in full) and len(full)==5)
            try:contact_x(ex,True);T.check('F 첫 이동 기록 있음',True)
            except MissingField as e:T.check(f'F 첫 이동 기록 없음 → 명확한 오류: {e}',True)
        d=runs/'dev-b-m0-normal/r1'
        if d.exists():
            ex=extract(d);full=chute_full_intervals(ex);exc=[i for i in full if i['kind']!='passed']
            T.check(f'시드 1 M0: 띠 안 정지 구간이 통계에서 빠지고 수 · 시작 틱 보고 — 제외 {[(i["kind"],i["start_tick"],i["part"]) for i in exc]} · 지나간 {sum(i["kind"]=="passed" for i in full)} · 속도 출처 {ex["velocity_source"]}',
                    any(i['kind']=='띠 안 정지' for i in exc))
    T.finish()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0]);ap.add_argument('--pair',nargs=3,action='append',metavar=('SEED','F_DIR','M_DIR'));ap.add_argument('--out',type=Path);ap.add_argument('--selftest',action='store_true');ap.add_argument('--runs',type=Path);a=ap.parse_args()
    if a.selftest:selftest(a.runs)
    if not (a.pair and a.out):ap.error('--pair 와 --out 필요')
    r=calibrate([(int(s),f,m) for s,f,m in a.pair]);write_json(a.out,r);print('[PASS] calibration',r['constants'],'skipped',r['skipped'])
