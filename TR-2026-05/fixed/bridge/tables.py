"""TR-2026-05 표 · 예측 판정(구현 목록 I15, 사전 등록 §7 · §9 표 1~8) — 새로 씀.

입력: 회차 폴더(round.py 의 results.jsonl + 실행 폴더) 또는 공개본 묶음(public.py — results.jsonl + runs/<run_id>.json 축약 파일).
범주(§8) · 판정(§6-3 두 번 같음 / 10회 규칙) · 검출 두 지표(주 28쌍, 보조 29쌍 = 13쌍 · 16쌍) · 불일치 쌍 · 뒤바뀜(방향 · (가)~(라)) ·
결측 규칙(정해지지 않은 쌍을 유리 · 불리 양쪽으로 채워 같으면 그 결과, 다르면 [판정 불가]) · 예측 P1~P8 · 반증 F1~F3 · 표 1~8.
독립 검산(recompute.py)은 이 파일을 읽지 않고 같은 규칙을 따로 다시 구현한다.
    python3 bridge/tables.py <회차 또는 공개본 폴더> --out <tables.json>
    python3 bridge/tables.py --selftest
"""
import argparse, itertools, json, statistics, sys
from pathlib import Path
from common import read_json, write_json, Selftest
import classify
REASON={'late-reverse':('event','PART_DROP'),'swapped-sensors':('event','PART_DROP'),'push-timing-off':('event',{'PUSH_TOO_EARLY','PUSH_TOO_LATE','PUSH_MISSED'}),'ignore-curtain':('judgment','PLC_CURTAIN_IGNORED')}
FLIP_CATS={'가','나','라'};CAP=8
def load(folder):
    folder=Path(folder);rows=[json.loads(l) for l in (folder/'results.jsonl').read_text().splitlines() if l.strip()]
    for r in rows:
        if r['group']=='openloop':r['replay']=read_json(folder/'runs'/f'{r["run_id"]}.json') if (folder/'runs').exists() else read_json(folder/r['dir']/'summary.json');continue
        r['digest']=read_json(folder/'runs'/f'{r["run_id"]}.json') if (folder/'runs').exists() else classify.digest(folder/r['dir'])
    return rows
def pair(r):return (r['cell'],r['variant'],r['scenario'],r.get('seed'))
def decide(runs):
    """§6-3 · §8: [VALID] 두 번이 같으면 그 판정 · 두 번 모두 [PLANT_ERROR] 면 그대로 · 그 밖은 10회 규칙(6 이상, [VALID] 아닌 실행은 판정 없음)."""
    ok=[r for r in runs if r['valid']]
    if len(runs)==1:return (runs[0]['digest']['status'] if runs[0]['valid'] else None),'single'
    if len(ok)==len(runs) and len({r['digest']['trace_hash'] for r in ok})==1:return ok[0]['digest']['status'],'deterministic'
    if len(runs)==2 and all(r['digest'].get('category')=='plant_error' for r in runs):return None,'plant_error_twice'
    votes={};[votes.__setitem__(r['digest']['status'],votes.get(r['digest']['status'],0)+1) for r in ok if r['digest']['status'] in ('[PASS]','[FAIL]')]
    top=max(votes.items(),key=lambda kv:kv[1]) if votes else (None,0)
    return (top[0] if 10*top[1]>=6*len(runs) and len(runs)>=10 else None),'nondeterministic'
def detected(d,variant):
    if d is None or d['status']!='[FAIL]':return False
    if variant not in REASON:return False
    kind,want=REASON[variant];names={e[1] for e in (d['events'] if kind=='event' else d['judgments'])}
    return bool(names&(want if isinstance(want,set) else {want}))
def outcomes(rows):
    """(조건, 쌍) → {v 판정, d 대표 축약, state}. 주 실행 + 2회째 · 10회 규칙 실행."""
    by={}
    for r in rows:
        if r['group'] in ('main','repeat'):by.setdefault((r['condition'],pair(r)),[]).append(r)
    out={}
    for k,rs in by.items():
        rs.sort(key=lambda r:r['rep']);v,state=decide(rs);rep=next((r['digest'] for r in rs if r['valid'] and r['digest']['status']==v),rs[0]['digest'])
        out[k]=dict(v=v,d=rep,state=state,runs=len(rs))
    for (c,p),o in out.items():
        f=out.get(('F',p))
        o['cat']=classify.classify(f['d'],o['d'])['category'] if c!='F' and f and f['v'] and o['v'] and f['v']!=o['v'] else ('same' if f and o['v']==f['v'] else None)
        o['fc']=((o['d'].get('first_lock') or {}).get('fault_code') or 0) if o['v'] else None
        o['det']=detected(o['d'],p[1]) if o['v'] else None
    return out
def flex(o):
    """정해지지 않은 결과는 None → 결측 규칙에서 양쪽으로 채운다."""
    return o if o and o['v'] else None
def judge(pred,keys,out):
    """결측 규칙: keys 가운데 정해지지 않은 쌍을 극단값(통과 · 조건 모두 참인 실패 · 조건 모두 거짓인 실패)으로 모두 채워 본다."""
    und=[k for k in keys if not flex(out.get(k))]
    if len(und)>CAP:return dict(result='[판정 불가]',reason=f'정해지지 않은 쌍 {len(und)} > {CAP}')
    fills=[dict(v='[PASS]',cat='same',fc=0,det=False),dict(v='[FAIL]',cat='가',fc=3,det=True),dict(v='[FAIL]',cat='다',fc=0,det=False)]
    res=set();detail=None
    for combo in itertools.product(fills,repeat=len(und)):
        o=dict(out);o.update({k:dict(c,filled=True) for k,c in zip(und,combo)});r=pred(o);res.add(r['ok']);detail=detail or (r if not und else None)
    decided=pred({k:v for k,v in out.items() if flex(v)} | {k:dict(v=None) for k in und}) if und else None
    r=pred(out) if not und else pred({**out,**{k:dict(fills[0]) for k in und}})
    if len(res)>1 or None in res:return dict(result='[판정 불가]',undecided=[list(map(str,k)) for k in und],decided_only={k:v for k,v in (decided or r).items() if k!='ok'},reason='대상 0' if res=={None} else '양쪽 채움 결과가 다름')
    return dict(result='[맞음]' if res.pop() else '[틀림]',**{k:v for k,v in r.items() if k!='ok'},undecided=len(und))
def predictions(rows,out):
    cb=sorted({(r['seed'],r.get('bin')) for r in rows if r['cell']=='cell-b' and r['group']=='main' and r['variant']=='correct' and r['scenario']=='normal'})
    N=lambda b:[('cell-b','correct','normal',s) for s,bb in cb if bb==b]
    g=lambda o,c,p:o.get((c,p)) or {}
    def p1sat(o,p):return g(o,'F',p).get('v')=='[PASS]' and g(o,'M0',p).get('v')=='[FAIL]' and g(o,'M0',p).get('fc')==3 and g(o,'M0',p).get('cat')=='가'
    def flip(o,c,p):return g(o,'F',p).get('v') and g(o,c,p).get('v') and g(o,'F',p)['v']!=g(o,c,p)['v'] and g(o,c,p).get('cat') in FLIP_CATS
    P={}
    P['P1']=judge(lambda o:(lambda x:dict(ok=x>=3 if N(5) else None,count=x,of=len(N(5))))(sum(p1sat(o,p) for p in N(5))),[(c,p) for p in N(5) for c in ('F','M0')],out)
    P['P2']=judge(lambda o:(lambda x:dict(ok=x<=2 if N(3)+N(4) else None,count=x,of=len(N(3)+N(4))))(sum(bool(flip(o,'M0',p)) for p in N(3)+N(4))),[(c,p) for p in N(3)+N(4) for c in ('F','M0')],out)
    def p3(o):
        n0=[p for p in N(5) if p1sat(o,p)];x=sum(1 for p in n0 if g(o,'F',p).get('v')=='[PASS]' and g(o,'M1',p).get('v')=='[FAIL]' and g(o,'M1',p).get('cat') in FLIP_CATS)
        return dict(ok=(2*x>len(n0)) if n0 else None,x=x,n0=len(n0))
    P['P3']=judge(p3,[(c,p) for p in N(5) for c in ('F','M0','M1')],out)
    main=[p for p in {pair(r) for r in rows if r['group']=='main'} if p[1] in REASON]
    P['P4']=judge(lambda o:(lambda x:dict(ok=x<=1 if main else None,discordant=x,of=len(main)))(sum(g(o,'F',p).get('det')!=g(o,'M0',p).get('det') for p in main)),[(c,p) for p in main for c in ('F','M0')],out)
    A=[p for p in main if p[0]=='cell-a']
    P['P5']=judge(lambda o:dict(ok=all(g(o,c,p).get('det') for p in A for c in ('F','M0')) if A else None,of=len(A)),[(c,p) for p in A for c in ('F','M0')],out)
    gate=[r for r in rows if r['group']=='gate'];fmain={pair(r):r for r in rows if r['group']=='main' and r['condition']=='F'}
    gate_same=all(r['valid'] and fmain.get(pair(r)) and fmain[pair(r)]['digest'].get('trace_hash')==r['digest'].get('trace_hash') for r in gate)
    mdet=all(o['state'] in ('deterministic','single') for (c,_),o in out.items() if c!='F')
    P['P6']=dict(result='[맞음]' if gate_same and mdet and gate else '[틀림]',gate_pairs=len(gate),gate_same=gate_same,m_deterministic=mdet)
    ol=[r['replay'] for r in rows if r['group']=='openloop' and r['cell']=='cell-b']
    n=sum(x['p7']['n'] for x in ol);w=sum(x['p7']['within'] for x in ol);ch=[d for x in ol for d in x['p7']['chute_rise_diffs']]
    P['P7']=dict(result='[판정 불가]' if not ol else '[맞음]' if 10*w>=9*n and ch and statistics.median(ch)>0 else '[틀림]',n=n,within=w,chute_median=statistics.median(ch) if ch else None,batches=len(ol))
    sens=[r for r in rows if r['group']=='p8' and r['cell']=='cell-b']
    def p8(o):
        n1=[p for p in N(5) if p1sat(o,p)];hold=0;detail={}
        for p in n1:
            sets={r['setting'] for r in sens if pair(r)==p};h=0
            for s in sets:
                m=next((r for r in sens if pair(r)==p and r['setting']==s and r['condition']!='F'),None);f=next((r for r in sens if pair(r)==p and r['setting']==s and r['condition']=='F'),None)
                fv=f['digest']['status'] if f and f['valid'] else g(o,'F',p).get('v') if not f else None
                if m and m['valid'] and fv=='[PASS]' and m['digest']['status']=='[FAIL]' and classify.classify((f or {'digest':g(o,'F',p).get('d')})['digest'],m['digest'])['category'] in FLIP_CATS:h+=1
            detail[p[3]]=dict(h=h,k=len(sets));hold+=8*h>=5*len(sets) and len(sets)>0
        return dict(ok=(2*hold>len(n1)) if n1 and all(x['k'] for x in detail.values()) else None,n=len(n1),holding=hold,detail=detail)  # 설정 실행이 없는 배치가 있으면 판정 불가
    r=p8(out);P['P8']=dict(result='[판정 불가]' if r['ok'] is None else '[맞음]' if r['ok'] else '[틀림]',**{k:v for k,v in r.items() if k!='ok'})
    C=[p for p in {pair(r) for r in rows if r['group']=='main' and r['cell']=='cell-b' and r['variant']=='correct'}]
    P['F1']=judge(lambda o:(lambda x:dict(ok=x==0,count=x,of=len(C)))(sum(bool(flip(o,'M0',p)) for p in C)),[(c,p) for p in C for c in ('F','M0')],out)
    P['F2']=judge(lambda o:(lambda x:dict(ok=x>=2,discordant=x))(sum(g(o,'F',p).get('det')!=g(o,'M0',p).get('det') for p in main)),[(c,p) for p in main for c in ('F','M0')],out)
    P['F3']=judge(lambda o:(lambda x:dict(ok=x==0,count=x,of=len(C)))(sum(1 for p in C if g(o,'F',p).get('v')=='[PASS]' and g(o,'M1',p).get('v')=='[FAIL]' and g(o,'M1',p).get('cat') in FLIP_CATS)),[(c,p) for p in C for c in ('F','M1')],out)
    for k in ('F1','F2','F3'):P[k]['meaning']='반증 조건 성립(주장을 틀린 것으로 적음)' if P[k]['result']=='[맞음]' else '반증 조건 불성립' if P[k]['result']=='[틀림]' else P[k]['result']
    return P
def build(folder,calibration=None):
    rows=load(folder);out=outcomes(rows);P=predictions(rows,out);T={}
    keyname=lambda k:'|'.join(map(str,k[1]))+'|'+k[0]
    T['table1']=[dict(pair=list(p),condition=c,verdict=o['v'],state=o['state'],category=o['cat'],first_lock=o['fc'],ledger_free=o['d'].get('ledger_free'),runs=o['runs']) for (c,p),o in sorted(out.items(),key=lambda kv:str(kv[0])) if p[1]=='correct']
    neg=[(c,p,o) for (c,p),o in out.items() if p[1] in REASON or p[1]=='no-sort-check']
    T['table2']=dict(rows=[dict(pair=list(p),condition=c,verdict=o['v'],reason_detected=o['det'],verdict_detected=o['v']=='[FAIL]' if o['v'] else None) for c,p,o in sorted(neg,key=str)],
                     main_detected={c:sum(1 for cc,p,o in neg if cc==c and p[1] in REASON and o['det']) for c in ('F','M0','M1')},
                     aux13={c:sum(1 for cc,p,o in neg if cc==c and p[1] in ('push-timing-off','no-sort-check') and o['v']=='[FAIL]') for c in ('F','M0','M1')},
                     aux16={c:sum(1 for cc,p,o in neg if cc==c and p[1] in ('late-reverse','swapped-sensors','ignore-curtain') and o['v']=='[FAIL]') for c in ('F','M0','M1')})
    T['table3']=[dict(pair=list(pair(r)),p7=r['replay']['p7'],routes=r['replay']['routes']['match'],chute=r['replay'].get('chute',{}).get('outside_window')) for r in rows if r['group']=='openloop']
    T['table4']=P['P8'].get('detail');T['table5']=[dict(pair=list(pair(r)),setting=r['setting'],condition=r['condition'],verdict=r['digest']['status'] if r['valid'] else None) for r in rows if r['group']=='model']
    T['table6']=[dict(pair=list(p),condition=c,**{k:v for k,v in classify.classify(out[('F',p)]['d'],o['d']).items() if k in ('category','e1_row','e1_class','first_divergence','direction')}) for (c,p),o in out.items() if c!='F' and o['cat'] not in (None,'same')]
    T['table7']=[dict(run_id=r['run_id'],reference=(r['digest'].get('reference') or {}) and {k:r['digest']['reference'].get(k) for k in ('before_lock','exception','after_lock','after_lock_by_tag','invalid')}) for r in rows if r.get('digest') and r['variant']=='correct' and r['group'] in ('main','repeat','gate')]
    T['table8']=calibration
    bad_ref=[t['run_id'] for t in T['table7'] if (t['reference'] or {}).get('invalid')]
    cats={};[cats.__setitem__(r['category_round'],cats.get(r['category_round'],0)+1) for r in rows]
    return dict(schema='tr05-tables/1',categories=cats,whole_run_invalid_reference=bad_ref,predictions=P,tables=T,outcomes={keyname(k):dict(v=o['v'],cat=o['cat'],fc=o['fc'],det=o['det'],state=o['state']) for k,o in out.items()})

def selftest():
    T=Selftest('tables')
    def D(status,th='h',fc=None,events=(),judg=()):return dict(status=status,category='valid',trace_hash=th,first_lock=dict(tick=1710,scan=1710,fault_code=fc) if fc else None,events=list(events),judgments=list(judg),arrivals=20,ticks=5000,parts=[],ledger_free=None,lock_window=None)
    def R(g,c,v,s,b,d,rep=1,sc='normal',cell='cell-b'):return dict(run_id=f'{g}-{c}-{v}-{s}-{rep}',group=g,condition=c,cell=cell,variant=v,scenario=sc,seed=s,bin=b,setting=None,rep=rep,valid=True,category_round='valid',digest=d)
    rows=[]
    for s in (51,52,53,54):rows+= [R('main','F','correct',s,5,D('[PASS]')),R('main','M0','correct',s,5,D('[FAIL]','m',3)),R('repeat','M0','correct',s,5,D('[FAIL]','m',3),2)]
    out=outcomes(rows);P=predictions(rows,out)
    T.check(f'P1: 4/4 배치 (가) FaultCode 3 → {P["P1"]["result"]}',P['P1']['result']=='[맞음]')
    rows2=[r for r in rows if not (r['seed']==54 and r['condition']=='M0')]+[R('main','M0','correct',54,5,D('[FAIL]','x',3)),R('repeat','M0','correct',54,5,D('[PASS]','y'),2)]
    o2=outcomes(rows2);P2=predictions(rows2,o2)
    T.check(f'비결정 쌍(2회만)은 정해지지 않음 → 결측 규칙: 3/3 이 이미 성립하므로 {P2["P1"]["result"]}',o2[('M0',('cell-b','correct','normal',54))]['v'] is None and P2['P1']['result']=='[맞음]')
    rows3=[r for r in rows2 if not (r['seed']==53 and r['condition']=='M0')]+[R('main','M0','correct',53,5,D('[FAIL]','x',3)),R('repeat','M0','correct',53,5,D('[PASS]','y'),2)]
    P3=predictions(rows3,outcomes(rows3))
    T.red_green('결측 규칙: 한 쌍을 [UNDECIDED] 로 바꿔 양쪽 채움 결과가 다르면 [판정 불가]',lambda:P3['P1']['result']!='[판정 불가]',lambda:P3['P1']['result']=='[판정 불가]' and P['P1']['result']=='[맞음]')
    neg=[R('main','F','push-timing-off',51,5,D('[FAIL]',events=[[295,'PUSH_TOO_EARLY','FLY-SIDE','part2']]),sc='normal'),R('main','M0','push-timing-off',51,5,D('[FAIL]','m'),sc='normal'),R('repeat','M0','push-timing-off',51,5,D('[FAIL]','m'),2,sc='normal')]
    o=outcomes(neg)
    T.red_green('검출: 기대 사유 없는 [FAIL] 은 주 지표 검출 아님(보조 지표 판정 검출은 맞음)',lambda:o[('M0',('cell-b','push-timing-off','normal',51))]['det'],lambda:o[('F',('cell-b','push-timing-off','normal',51))]['det'] and predictions(neg,o)['P4']['discordant']==1)
    T.finish()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0]);ap.add_argument('folder',nargs='?',type=Path);ap.add_argument('--out',type=Path);ap.add_argument('--calibration',type=Path);ap.add_argument('--selftest',action='store_true');a=ap.parse_args()
    if a.selftest:selftest()
    if not (a.folder and a.out):ap.error('폴더와 --out 필요')
    t=build(a.folder,read_json(a.calibration) if a.calibration else None);write_json(a.out,t);print('[PASS] tables',{k:v['result'] for k,v in t['predictions'].items()})
