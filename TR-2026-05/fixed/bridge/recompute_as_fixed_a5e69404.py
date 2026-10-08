"""TR-2026-05 독립 검산(구현 목록 I15, 사전 등록 §9 「독립 검산」) — 새로 씀. tables.py · classify.py · refcheck.py · round.py 를 import 하지 않는다.

공개본 묶음(public.py 출력: results.jsonl 의 꼬리표 + runs/<run_id>.json 실행별 축약 + fixed.json · seed-table.json)만 읽고
범주(틱 수 · 해시) · 판정(두 번 같음 / 10회 규칙) · 원인 분류 (가)~(라) · E1 행 · 검출 두 지표 · 뒤바뀜 · 참조 일치 무효(예외 모양 포함) ·
결측 규칙 · 예측 P1~P8 · 반증 F1~F3 를 다시 계산해 tables.json 과 전부 대조한다(다르면 [FAIL] 과 차이 목록).
    python3 bridge/recompute.py <공개본 묶음> --tables <tables.json>
    python3 bridge/recompute.py --selftest
"""
import argparse, itertools, json, statistics, sys
from pathlib import Path
from common import read_json, write_json
TICKS={'cell-a':{'normal':1000,'cycle-stop':1200}}
TICKS_B={('correct','normal'):5000,('correct','curtain'):1000,('correct','recovery'):2800,('push-timing-off','normal'):1800,('ignore-curtain','curtain'):500,('no-sort-check','flow'):800}
WANT={'late-reverse':{'PART_DROP'},'swapped-sensors':{'PART_DROP'},'push-timing-off':{'PUSH_TOO_EARLY','PUSH_TOO_LATE','PUSH_MISSED'},'ignore-curtain':{'PLC_CURTAIN_IGNORED'}}
QUIET={'PART_PACKED','REJECT_COLLECTED','PACK_PLACED','CONTAINER_EXCHANGED','PART_COLLECTED'}
def ticks_for(d):
    return TICKS.get('cell-a',{}).get(d['scenario']) if d['cell']=='cell-a' else TICKS_B.get((d['variant'],d['scenario']))
def valid(row,d,fixed=None,seeds=None):
    if d.get('category')!='valid' or d.get('ticks')!=ticks_for(d):return False
    if fixed and d.get('physics')=='mujoco':
        want=(fixed.get('setup_sha256') or {}).get(d['cell'],{}).get(row.get('setting') or 'default')
        if want and d['physics_hashes'].get('setup_sha256')!=want:return False
    if seeds and d.get('physics')=='mujoco' and d['cell']=='cell-b':
        want=(seeds.get('values') or {}).get(str(d['seed']),{}).get(row.get('setting') or 'default',{}).get('values_sha256')
        if want and d['physics_hashes'].get('values_sha256')!=want:return False
    return True
def good(p):return (p['route'] in (1,3)) if p['cls'] else p['route']==2

# 원인 분류(§7) — classify.py 와 따로 쓴 구현
def lockcode(d):return ((d.get('first_lock') or {}).get('fault_code')) or 0
def diverge(f,m):
    cand=[]
    if lockcode(f)!=lockcode(m):
        locks=[x for x in (f.get('first_lock'),m.get('first_lock')) if x];x=min(locks,key=lambda l:l['tick']);side='M' if x is m.get('first_lock') else 'F'
        cand.append((x['tick'],0,'lock',dict(code=x['fault_code'],window=(m if side=='M' else f).get('lock_window'))))
    for rank,key in ((1,'events'),(2,'judgments')):
        A,B=f[key],m[key];n=0
        while n<max(len(A),len(B)):
            a=A[n] if n<len(A) else None;b=B[n] if n<len(B) else None
            if a is None or b is None or a[1:]!=b[1:]:
                pick=b if a is None or (b is not None and b[0]<a[0]) else a;cand.append((pick[0],rank,'event' if key=='events' else 'judgment',dict(name=pick[1],rule=pick[2] if key=='events' else None)));break
            n+=1
    routes={p['id']:p['route'] for p in f['parts']}
    for p in m['parts']:
        if p['id'] in routes and routes[p['id']]!=p['route']:
            cand.append((m['ticks'] if p['route']==0 else (p['route_tick'] or m['ticks']),3,'route',dict(F=routes[p['id']],M=p['route'],on_floor=p.get('on_floor'),stacked=p.get('stacked'))))
    cand.sort(key=lambda c:(c[0],c[1]));return cand[0] if cand else None
ROWS={'CENTER-SNAP':'r10','FLY-SIDE':'r11','PUSH-RETURN':'r11','FLY-01':'r11','FLY-02':'r11','FLOW-QUEUE':'r12','CHUTE-01':'r6','CHUTE-HOLD':'r6'}
def row_of(dv):
    if dv is None:return None
    _,_,kind,x=dv
    if kind=='lock':return {3:'r5',4:'r8',5:'r1'}.get(x['code']) if x['code']!=13 else {'chute':'r3','out':'r8'}.get(x['window'])
    if kind=='event':return 'r15' if x['name']=='PART_DROP' else 'r11' if x['name']=='PUSH_MISSED' else ROWS.get(x['rule'])
    if kind=='route':return 'r16' if x['on_floor'] else 'r17' if x['stacked'] else 'r8' if (x['M'],x['F'])==(0,2) else None
    return None
def classify(f,m):
    if f['status']==m['status']:return dict(category='same',e1_row=row_of(diverge(f,m)))
    dv=diverge(f,m);lf,lm=lockcode(f),lockcode(m)
    if lm in (0,lf) and not m['events'] and not m['judgments'] and m.get('arrivals')==20 and any(not good(p) for p in m['parts']):c='다'
    else:c={'lock':'가','event':'나','judgment':'나'}.get(dv[2] if dv else None,'라')
    return dict(category=c,e1_row=row_of(dv))

def ref_invalid(d):
    """§8 ②: 첫 잠금 전 차이에서 예외 모양 하나를 뺀 수 > 0 이면 무효."""
    r=d.get('reference_raw')
    if not r:return None
    scans={x[0] for x in r['before']};used=False;n=0
    for s,tags,act,exp in r['before']:
        shape=(set(tags)=={'B.Conv.run','B.Lamp.green','B.Lamp.yellow'} and act in (0,False) and exp in (1,True) and s-1 not in scans and s+1 not in scans
               and r['arrivals20_scan'] is not None and s>r['arrivals20_scan'] and r['last_arrive_scan'] is not None and abs(s-r['last_arrive_scan']-3000)<=1)
        if shape and not used:used=True
        else:n+=1
    return n>0

def decided(rs):
    ok=[(r,d) for r,d in rs if r['ok']]
    if len(rs)==1:return rs[0][1]['status'] if rs[0][0]['ok'] else None
    if len(ok)==len(rs) and len({d['trace_hash'] for _,d in ok})==1:return ok[0][1]['status']
    if len(rs)==2 and all(d.get('category')=='plant_error' for _,d in rs):return None
    if len(rs)<10:return None
    for v in ('[PASS]','[FAIL]'):
        if 10*sum(1 for _,d in ok if d['status']==v)>=6*len(rs):return v
    return None
def evaluate(bundle):
    bundle=Path(bundle);idx=[json.loads(l) for l in (bundle/'results.jsonl').read_text().splitlines() if l.strip()]
    fixed=read_json(bundle/'fixed.json') if (bundle/'fixed.json').exists() else None;seeds=read_json(bundle/'seed-table.json') if (bundle/'seed-table.json').exists() else None
    runs=[];ol=[]
    for r in idx:
        d=read_json(bundle/'runs'/f'{r["run_id"]}.json')
        if r['group']=='openloop':ol.append((r,d));continue
        r=dict(r,ok=valid(r,d,fixed,seeds));runs.append((r,d))
    key=lambda r:(r['cell'],r['variant'],r['scenario'],r.get('seed'))
    grp={}
    for r,d in runs:
        if r['group'] in ('main','repeat'):grp.setdefault((r['condition'],key(r)),[]).append((r,d))
    res={}
    for k,rs in grp.items():
        rs.sort(key=lambda x:x[0]['rep']);v=decided(rs);d=next((d for r,d in rs if r['ok'] and d['status']==v),rs[0][1]);res[k]=dict(v=v,d=d,n=len(rs),det=len({x[1].get('trace_hash') for x in rs})==1 and all(x[0]['ok'] for x in rs))
    for (c,p),o in res.items():
        f=res.get(('F',p));o['cat']=classify(f['d'],o['d'])['category'] if f and f['v'] and o['v'] and c!='F' else None
        o['fc']=lockcode(o['d']) if o['v'] else None;o['hit']=(o['v']=='[FAIL]' and bool(WANT.get(p[1],set())&({e[1] for e in o['d']['events']}|{j[1] for j in o['d']['judgments']}))) if o['v'] else None
    return idx,runs,ol,res
def fill_eval(keys,res,f):
    miss=[k for k in keys if not (res.get(k) or {}).get('v')]
    if len(miss)>8:return '[판정 불가]'
    seen=set()
    for combo in itertools.product(['P','FA','FO'],repeat=len(miss)):
        r=dict(res)
        for k,c in zip(miss,combo):r[k]=dict(v='[PASS]' if c=='P' else '[FAIL]',cat='same' if c=='P' else '가' if c=='FA' else '다',fc=3 if c=='FA' else 0,hit=c=='FA')
        seen.add(f(r))
    return '[판정 불가]' if len(seen)!=1 or None in seen else '[맞음]' if seen.pop() else '[틀림]'
def predict(bundle):
    idx,runs,ol,res=evaluate(bundle);V=lambda r,c,p:(r.get((c,p)) or {})
    batches=sorted({(r['seed'],r.get('bin')) for r,_ in runs if r['group']=='main' and r['cell']=='cell-b' and r['variant']=='correct' and r['scenario']=='normal'})
    B=lambda *bs:[('cell-b','correct','normal',s) for s,b in batches if b in bs]
    sat=lambda r,p:V(r,'F',p).get('v')=='[PASS]' and V(r,'M0',p).get('v')=='[FAIL]' and V(r,'M0',p).get('fc')==3 and V(r,'M0',p).get('cat')=='가'
    fl=lambda r,c,p:bool(V(r,'F',p).get('v') and V(r,c,p).get('v') and V(r,'F',p)['v']!=V(r,c,p)['v'] and V(r,c,p).get('cat') in ('가','나','라'))
    neg=sorted({k for _,k in res if k[1] in WANT})
    corr=sorted({k for _,k in res if k[0]=='cell-b' and k[1]=='correct'})
    out={}
    out['P1']=fill_eval([(c,p) for p in B(5) for c in ('F','M0')],res,lambda r:sum(sat(r,p) for p in B(5))>=3 if B(5) else None)
    out['P2']=fill_eval([(c,p) for p in B(3,4) for c in ('F','M0')],res,lambda r:sum(fl(r,'M0',p) for p in B(3,4))<=2 if B(3,4) else None)
    def p3(r):
        n0=[p for p in B(5) if sat(r,p)]
        return None if not n0 else 2*sum(1 for p in n0 if V(r,'F',p).get('v')=='[PASS]' and V(r,'M1',p).get('v')=='[FAIL]' and V(r,'M1',p).get('cat') in ('가','나','라'))>len(n0)
    out['P3']=fill_eval([(c,p) for p in B(5) for c in ('F','M0','M1')],res,p3)
    out['P4']=fill_eval([(c,p) for p in neg for c in ('F','M0')],res,lambda r:sum(V(r,'F',p).get('hit')!=V(r,'M0',p).get('hit') for p in neg)<=1 if neg else None)
    A=[p for p in neg if p[0]=='cell-a']
    out['P5']=fill_eval([(c,p) for p in A for c in ('F','M0')],res,lambda r:all(V(r,c,p).get('hit') for p in A for c in ('F','M0')) if A else None)
    fm={key:d['trace_hash'] for r,d in runs for key in [(r['cell'],r['variant'],r['scenario'],r.get('seed'))] if r['group']=='main' and r['condition']=='F'}
    gate=[(r,d) for r,d in runs if r['group']=='gate']
    out['P6']='[맞음]' if gate and all(r['ok'] and fm.get((r['cell'],r['variant'],r['scenario'],r.get('seed')))==d['trace_hash'] for r,d in gate) and all(o['det'] or o['n']==1 for (c,_),o in res.items() if c!='F') else '[틀림]'
    cb=[d for r,d in ol if r['cell']=='cell-b'];n=sum(d['p7']['n'] for d in cb);w=sum(d['p7']['within'] for d in cb);ch=[x for d in cb for x in d['p7']['chute_rise_diffs']]
    out['P7']='[판정 불가]' if not cb else '[맞음]' if 10*w>=9*n and ch and statistics.median(ch)>0 else '[틀림]'
    sens=[(r,d) for r,d in runs if r['group']=='p8' and r['cell']=='cell-b'];n1=[p for p in B(5) if sat(res,p)];hold=0;empty=False
    for p in n1:
        mine=[(r,d) for r,d in sens if key(r)==p];names=sorted({r['setting'] for r,_ in mine});h=0
        for s in names:
            md=next((d for r,d in mine if r['setting']==s and r['condition']!='F' and r['ok']),None);fr=next(((r,d) for r,d in mine if r['setting']==s and r['condition']=='F'),None)
            fd=(fr[1] if fr[0]['ok'] else None) if fr else V(res,'F',p).get('d')
            if md and fd and fd['status']=='[PASS]' and md['status']=='[FAIL]' and classify(fd,md)['category'] in ('가','나','라'):h+=1
        hold+=bool(names) and 8*h>=5*len(names);empty|=not names
    out['P8']='[판정 불가]' if not n1 or empty else '[맞음]' if 2*hold>len(n1) else '[틀림]'
    out['F1']=fill_eval([(c,p) for p in corr for c in ('F','M0')],res,lambda r:sum(fl(r,'M0',p) for p in corr)==0)
    out['F2']=fill_eval([(c,p) for p in neg for c in ('F','M0')],res,lambda r:sum(V(r,'F',p).get('hit')!=V(r,'M0',p).get('hit') for p in neg)>=2)
    out['F3']=fill_eval([(c,p) for p in corr for c in ('F','M1')],res,lambda r:sum(1 for p in corr if V(r,'F',p).get('v')=='[PASS]' and V(r,'M1',p).get('v')=='[FAIL]' and V(r,'M1',p).get('cat') in ('가','나','라'))==0)
    refbad=sorted(r['run_id'] for r,d in runs if r['variant']=='correct' and r['group'] in ('main','repeat','gate') and ref_invalid(d))
    counts=dict(main_detected={c:sum(1 for (cc,p),o in res.items() if cc==c and p[1] in WANT and o['hit']) for c in ('F','M0','M1')},
                aux13={c:sum(1 for (cc,p),o in res.items() if cc==c and p[1] in ('push-timing-off','no-sort-check') and o['v']=='[FAIL]') for c in ('F','M0','M1')},
                aux16={c:sum(1 for (cc,p),o in res.items() if cc==c and p[1] in ('late-reverse','swapped-sensors','ignore-curtain') and o['v']=='[FAIL]') for c in ('F','M0','M1')})
    verdicts={'|'.join(map(str,p))+'|'+c:dict(v=o['v'],cat=o['cat']) for (c,p),o in res.items()}
    return dict(predictions=out,counts=counts,reference_invalid=refbad,verdicts=verdicts,valid_runs=sum(1 for r,_ in runs if r['ok']),runs=len(runs))
def compare(rec,tables):
    diffs=[]
    for k,v in rec['predictions'].items():
        t=tables['predictions'].get(k,{}).get('result')
        if t!=v:diffs.append(f'{k}: 검산 {v} · 표 {t}')
    for k in ('main_detected','aux13','aux16'):
        if rec['counts'][k]!=tables['tables']['table2'][k]:diffs.append(f'{k}: 검산 {rec["counts"][k]} · 표 {tables["tables"]["table2"][k]}')
    if sorted(rec['reference_invalid'])!=sorted(tables['whole_run_invalid_reference']):diffs.append('참조 일치 무효 목록 다름')
    for k,o in rec['verdicts'].items():
        t=tables['outcomes'].get(k)
        if not t or t['v']!=o['v'] or (o['cat'] not in (None,'same') and t['cat']!=o['cat']):diffs.append(f'{k}: 검산 {o} · 표 {t}')
    return diffs

def selftest():
    from common import Selftest
    T=Selftest('recompute')
    P=lambda i,cls,route:dict(id=f'part{i}',cls=cls,route=route,route_tick=10*i,x=7.0,on_floor=False,stacked=False)
    f=dict(status='[PASS]',first_lock=None,events=[],judgments=[],arrivals=20,ticks=5000,parts=[P(i,0,2) for i in range(1,4)])
    m=dict(f,status='[FAIL]',parts=[P(1,0,2),P(2,0,2),P(3,0,0)])
    T.red_green('독립 분류: route 0 하나 → (다)',lambda:classify(f,dict(m,first_lock=dict(tick=5,scan=5,fault_code=3)))['category']=='다',lambda:classify(f,m)['category']=='다')
    raw=dict(before=[[4461,['B.Conv.run','B.Lamp.green','B.Lamp.yellow'],False,True]],arrivals20_scan=1461,last_arrive_scan=1461)
    T.red_green('독립 참조 예외 모양: 다른 태그 한 스캔은 무효, 문서화된 모양은 유효',lambda:not ref_invalid(dict(reference_raw=dict(raw,before=[[4461,['B.Lamp.red'],True,True]]))),lambda:ref_invalid(dict(reference_raw=raw)) is False)
    T.red_green('독립 범주: summary 틱 수가 표와 다르면 [VALID] 아님',lambda:valid({},dict(category='valid',ticks=4999,cell='cell-b',variant='correct',scenario='normal')),lambda:valid({},dict(category='valid',ticks=5000,cell='cell-b',variant='correct',scenario='normal')))
    T.finish()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0]);ap.add_argument('bundle',nargs='?',type=Path);ap.add_argument('--tables',type=Path);ap.add_argument('--out',type=Path);ap.add_argument('--selftest',action='store_true');a=ap.parse_args()
    if a.selftest:selftest()
    if not (a.bundle and a.tables):ap.error('묶음과 --tables 필요')
    rec=predict(a.bundle);d=compare(rec,read_json(a.tables))
    if a.out:write_json(a.out,dict(rec,differences=d))
    print('[PASS]' if not d else '[FAIL]','recompute',rec['predictions'],'differences',len(d));[print('  ',x) for x in d[:20]];sys.exit(0 if not d else 1)
