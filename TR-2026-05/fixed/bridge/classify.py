"""TR-2026-05 원인 분류 · E1 대응(구현 목록 I13, 사전 등록 §7 원인 분류 · §8 E1 · §9 표 1 · 6) — 새로 씀.

같은 (래더, 입력)의 F · M 실행을 실행별 축약(digest — 공개본의 실행별 축약 파일과 같은 형식)으로 바꿔 비교한다.
- 처음 갈라진 사건: 첫 잠금(틱 · FaultCode) · 물리 사건(이름 · 규칙 · 부품, 순서대로) · 다리 판정 · 부품 최종 경로 가운데 가장 이른 것.
  사건 · 경로는 「무엇이 일어났는가」로 비교한다(같은 사건의 틱 차이는 갈라짐이 아님 — 두 모형의 시각은 원래 다르다).
- 분류: (다) 완료 항목만 = M 첫 잠금 FaultCode 가 0 이거나 F 와 같음 ∧ M 물리 사건 · 다리 판정 없음 ∧ Arrivals = 20 ∧ 경로가 완료 조건을 못 채움.
  그 밖은 처음 갈라진 사건이 잠금 → (가), 물리 사건 · 다리 판정 → (나), 그 밖 → (라). (다)는 부품별 원인(출력 줄 휨 · on_floor · stacked · 기타).
- E1 사전 대응(§8 표): 처음 갈라진 사건 → §3-2 행 · 「같은가」 값.
    python3 bridge/classify.py <F 실행 폴더> <M 실행 폴더>
    python3 bridge/classify.py --selftest [--runs <개발 기록>]
"""
import argparse, json, math, sys
from pathlib import Path
from common import trace, read_json, field, MissingField, physics_parts
NEUTRAL={'PART_PACKED','REJECT_COLLECTED','PACK_PLACED','CONTAINER_EXCHANGED','PART_COLLECTED'}
SAME={'r1':'접촉 계산으로 바꿈','r3':'접촉 계산으로 바꿈','r5':'다름','r6':'같은 효과를 내도록 옮김','r8':'허용 오차를 더함','r10':'근사','r11':'사건 같음, 결과 다름','r12':'사건 조건 같음','r15':'같음(+보조)','r16':'다름','r17':'다름'}
RULE_ROW={'CENTER-SNAP':'r10','FLY-SIDE':'r11','PUSH-RETURN':'r11','FLY-01':'r11','FLY-02':'r11','FLOW-QUEUE':'r12','CHUTE-01':'r6','CHUTE-HOLD':'r6'}
def window_of_13(run_dir,lock_scan,windows=((165,235),(198,269))):
    """FaultCode 13 이 슈트 창인지 out 창인지: 원래 래더 엔진 재생으로 잠금 스캔의 필터 상승과 대기열 나이를 본다."""
    from calibrate import extract
    import subprocess
    from common import ROOT
    ex=extract(run_dir);read=['FaultCode','Chute','Out','ExpectChuteN','ExpectOutN','ExpectChuteAge','ExpectOutAge']
    lines=[json.dumps(dict(read=read))]+[json.dumps(i) for i in ex['images'][:lock_scan]]
    p=subprocess.run(['node',str(ROOT/'bridge/probe_engine.mjs'),str(ROOT/'ladders/cell-b/correct/program.ldprog.json')],input='\n'.join(lines)+'\n',capture_output=True,text=True,cwd=ROOT)
    s=[dict(zip(['scan']+read,json.loads(l))) for l in p.stdout.splitlines()[1:]]
    if len(s)<2:return 'unknown'
    a,b=s[-2],s[-1]
    if b['Chute'] and not a['Chute']:return 'chute'
    if b['Out'] and not a['Out']:return 'out'
    if b['ExpectChuteN'] and b['ExpectChuteAge']>windows[0][1]:return 'chute'
    if b['ExpectOutN'] and b['ExpectOutAge']>windows[1][1]:return 'out'
    return 'unknown'
def digest(run_dir,lock_detail=True):
    """실행 폴더 → 실행별 축약(판정 · 범주 · 사건 코드 묶음 · 경로 · 첫 잠금 · 부품 보고). 절대 경로 없음."""
    run_dir=Path(run_dir);s=read_json(run_dir/'summary.json');meta=read_json(run_dir/'metadata.json');events=[];judg=[];route_tick={};prev={};last=None;chute_on_at_lock=None
    lock=None;arr_prev=0;last_arrive=None;arr20=None;lock_I=None
    if s.get('category')!='valid':return dict(schema='tr05-run-digest/1',category=s.get('category'),status=s.get('status'),cell=s.get('cell'),variant=s.get('variant'),scenario=s.get('scenario'),seed=s.get('seed'),physics=s.get('physics_mode'),run=read_json(run_dir/'run.json') if (run_dir/'run.json').exists() else None)
    for r in trace(run_dir):
        for sc in r.get('scans') or []:  # 첫 잠금 · 마지막 Arrive · Arrivals 20 (참조 일치 예외 모양의 원자료)
            if lock is None and sc['probes'].get('FaultCode'):lock=dict(tick=r['tick'],scan=sc['scan'],fault_code=sc['probes']['FaultCode']);lock_I=bool(r['I'].get('B.Sen.chute'))
            a=sc['probes'].get('Arrivals',0)
            if a>arr_prev:last_arrive=sc['scan']
            if a>=20 and arr20 is None:arr20=sc['scan']
            arr_prev=a
        for e in r['events']:
            if e['name'] not in NEUTRAL:events.append([r['tick'],e['name'],e.get('rule'),e.get('part_id')])
        for j in r.get('judgments',[]):judg.append([r['tick'],j['name']])
        for p in r['state']['parts']:
            if prev.get(p['id'])!=p['route']:route_tick[p['id']]=r['tick'];prev[p['id']]=p['route']
        last=r['state']
    parts=[]
    for p in (last or {}).get('parts',[]):
        d=dict(id=p['id'],cls=int(p['class']),route=p['route'],route_tick=route_tick.get(p['id']),x=p['x'])
        try:
            pp=physics_parts(last).get(p['id']);d.update(on_floor=bool(field(pp,'on_floor')),stacked=bool(field(pp,'stacked')),x=float(field(pp,'x')))
        except (MissingField,TypeError,AttributeError):pass
        parts.append(d)
    chute_on_at_lock=lock_I;window=None;ref=None
    if (run_dir/'reference-10ms-differences.json').exists() and s.get('variant','correct')=='correct':
        diffs=read_json(run_dir/'reference-10ms-differences.json');ls=lock['scan'] if lock else float('inf');after={}
        for d in diffs:
            if d['scan']>=ls:
                for t in d['expected']:
                    if d['expected'][t]!=d['actual'].get(t):after[t]=after.get(t,0)+1
        ref=dict(before=[[d['scan'],sorted(t for t in d['expected'] if d['expected'][t]!=d['actual'].get(t)),d['actual'].get('B.Conv.run'),d['expected'].get('B.Conv.run')] for d in diffs if d['scan']<ls],after_by_tag=after,last_arrive_scan=last_arrive,arrivals20_scan=arr20)
    if lock and lock.get('fault_code')==13 and lock_detail:window=window_of_13(run_dir,lock['scan'])
    return dict(schema='tr05-run-digest/1',cell=s.get('cell') or ('cell-b' if meta.get('factory_tick_ms')==10 else 'cell-a'),variant=s.get('variant') or meta.get('variant'),scenario=s.get('scenario'),seed=s.get('seed'),physics=s.get('physics_mode'),
                belt_factor=s.get('belt_factor'),physics_values=s.get('physics_values') or {},category=s.get('category'),status=s.get('status'),ticks=s.get('ticks'),verdict_kind=s.get('verdict_kind'),
                first_lock=lock,lock_window=window,chute_on_at_lock=chute_on_at_lock,end_fault_code=s.get('end_fault_code'),arrivals=(s.get('probes') or {}).get('Arrivals'),events=events,judgments=judg,parts=parts,
                ledger_free=(s.get('ledger_free') or {}).get('status'),reference=s.get('reference'),reference_raw=ref,run=read_json(run_dir/'run.json') if (run_dir/'run.json').exists() else None,trace_hash=s.get('trace_hash'),physics_hashes={k:(s.get('physics_report') or {}).get(k) for k in ('values_sha256','setup_sha256')})

def correct(p):return p['route'] in (1,3) if p['cls'] else p['route']==2
def first_divergence(f,m):
    cands=[]
    lf,lm=f.get('first_lock'),m.get('first_lock')
    if (lf or {}).get('fault_code')!=(lm or {}).get('fault_code'):
        t=min(x['tick'] for x in (lf,lm) if x);who=lm if lm and lm['tick']==t else lf;cands.append((t,0,dict(kind='lock',fault_code=who['fault_code'],side='M' if who is lm else 'F',window=m.get('lock_window') if who is lm else f.get('lock_window'))))
    for key,kind,order in (('events','event',1),('judgments','judgment',2)):
        a,b=f[key],m[key]
        for i in range(max(len(a),len(b))):
            x=a[i] if i<len(a) else None;y=b[i] if i<len(b) else None
            if x is None or y is None or x[1:]!=y[1:]:
                z=min((v for v in (x,y) if v),key=lambda v:v[0]);cands.append((z[0],order,dict(kind=kind,name=z[1],rule=z[2] if kind=='event' else None,part=z[3] if kind=='event' else None,side='M' if z is y else 'F')));break
    fr={p['id']:p for p in f['parts']}
    for p in m['parts']:
        q=fr.get(p['id'])
        if q and q['route']!=p['route']:
            t=p['route_tick'] if p['route']!=0 else m['ticks'];cands.append((t or m['ticks'],3,dict(kind='route',part=p['id'],F=q['route'],M=p['route'],on_floor=p.get('on_floor'),stacked=p.get('stacked'))))
    return min(cands,key=lambda c:(c[0],c[1])) if cands else None
def part_causes(m,out_x=2.2):
    res=[]
    for p in m['parts']:
        if correct(p):continue
        if 'on_floor' not in p:cause='parts[] 없음'
        elif p['on_floor']:cause='on_floor'
        elif p['stacked']:cause='stacked'
        elif not p['cls'] and p['route']==0 and p['x']>out_x:cause='출력 줄 휨'
        else:cause='기타'
        res.append(dict(id=p['id'],route=p['route'],cause=cause))
    return res
def e1_row(fd):
    if not fd:return None
    d=fd[2]
    if d['kind']=='lock':
        c=d['fault_code'];row={3:'r5',4:'r8',5:'r1'}.get(c)
        if c==13:row={'chute':'r3','out':'r8'}.get(d.get('window'))
        return row
    if d['kind']=='event':
        if d['name']=='PART_DROP':return 'r15'
        if d['name']=='PUSH_MISSED':return 'r11'
        return RULE_ROW.get(d['rule'])
    if d['kind']=='route':
        if d.get('on_floor'):return 'r16'
        if d.get('stacked'):return 'r17'
        if d['M']==0 and d['F']==2:return 'r8'
    return None
def classify(f,m):
    flipped=f['status']!=m['status'];fd=first_divergence(f,m)
    lf=(f.get('first_lock') or {}).get('fault_code',0);lm=(m.get('first_lock') or {}).get('fault_code',0)
    only_ledger=(lm==0 or lm==lf) and not m['events'] and not m['judgments'] and m.get('arrivals')==20 and not all(correct(p) for p in m['parts'])
    if not flipped:cat='same'
    elif only_ledger:cat='다'
    elif fd and fd[2]['kind']=='lock':cat='가'
    elif fd and fd[2]['kind'] in ('event','judgment'):cat='나'
    else:cat='라'
    row=e1_row(fd)
    return dict(flipped=flipped,direction=f'{f["status"]}->{m["status"]}' if flipped else None,category=cat,first_divergence=dict(tick=fd[0],**fd[2]) if fd else None,
                e1_row=row,e1_class=SAME.get(row,'분류 불가') if flipped else None,part_causes=part_causes(m) if cat=='다' else None,ledger_free=m.get('ledger_free'),first_lock_M=lm,first_lock_F=lf)

def selftest(runs=None):
    from common import Selftest
    import recompute
    T=Selftest('classify')
    P=lambda i,cls,route,**k:dict(id=f'part{i}',cls=cls,route=route,route_tick=100*i,x=7.0,**k)
    base=dict(status='[PASS]',first_lock=None,lock_window=None,events=[],judgments=[],arrivals=20,ticks=5000,parts=[P(i,int(i%4==1),1 if i%4==1 else 2,on_floor=False,stacked=False) for i in range(1,21)],ledger_free='[PASS]')
    m=json.loads(json.dumps(base));m['status']='[FAIL]';m['parts'][17].update(route=0,x=2.8)
    T.red_green('부품 하나를 route 0 으로 바꾼 합성 기록이 (다) · 출력 줄 휨',lambda:classify(base,dict(m,first_lock=dict(tick=900,scan=900,fault_code=3)))['category']=='다',
                lambda:(lambda c:c['category']=='다' and c['part_causes'][0]['cause']=='출력 줄 휨')(classify(base,m)))
    l=dict(m,parts=base['parts'],first_lock=dict(tick=1710,scan=1710,fault_code=3),arrivals=20)
    T.check('합성: 잠금 FaultCode 3 이 처음 갈라짐 → (가) · r5 · 다름',(lambda c:c['category']=='가' and c['e1_row']=='r5' and c['e1_class']=='다름')(classify(base,l)))
    e=dict(m,parts=base['parts'],events=[[295,'PUSH_TOO_EARLY','FLY-SIDE','part2']])
    T.check('합성: 물리 사건이 처음 갈라짐 → (나) · r11',(lambda c:c['category']=='나' and c['e1_row']=='r11')(classify(base,e)))
    for name,(a,b) in dict(ledger=(base,m),lock=(base,l),event=(base,e)).items():
        T.check(f'독립 검산 구현과 같은 결과({name})',classify(a,b)['category']==recompute.classify(a,b)['category'] and classify(a,b)['e1_row']==recompute.classify(a,b)['e1_row'])
    if runs:
        runs=Path(runs);fd=runs/'gate-fast-1/cell-b-seed1/r1';md=runs/'dev-b-m0-normal/r1'
        if fd.exists() and md.exists():
            F=digest(fd);M=digest(md);c=classify(F,M);r=recompute.classify(F,M)
            T.check(f'시드 1 M0 normal: ({c["category"]}) · 첫 갈라짐 {c["first_divergence"]} · E1 {c["e1_row"]} {c["e1_class"]}',c['category']=='가' and c['first_divergence']['fault_code']==3 and c['e1_row']=='r5')
            T.check('시드 1 M0 normal: 독립 검산과 같음',(c['category'],c['e1_row'])==(r['category'],r['e1_row']))
    T.finish()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0]);ap.add_argument('runs_pair',nargs='*',type=Path);ap.add_argument('--selftest',action='store_true');ap.add_argument('--runs',type=Path);a=ap.parse_args()
    if a.selftest:selftest(a.runs)
    if len(a.runs_pair)!=2:ap.error('F 실행 폴더와 M 실행 폴더')
    print(json.dumps(classify(digest(a.runs_pair[0]),digest(a.runs_pair[1])),ensure_ascii=False,indent=1))
