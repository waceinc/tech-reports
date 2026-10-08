"""TR-2026-05 실행 묶음: 빠른 모형 회귀 게이트(D14 · §8 양성 대조 1), 결정성 반복 · 10회 규칙(§6-3), 단일 실행.

시드 수용(§5-2, seed_table.accept_seed): 시드 0~3 은 그대로, 그 밖은 --dev-seed 표시(시드 표의 공식 · 교정 시드면 거부) 또는
고정 sha256 이 맞는 시드 표에서 읽은 시드만. 앱 경로는 --app 또는 TR05_APP(기본 경로 없음).
    python3 bridge/tr05.py gate   --out <폴더>                         # 3i 검증 묶음(fe605e1 verify_3i 의 셀 A · B 부분, 빠른 모형)
    python3 bridge/tr05.py repeat --out <폴더> --cell cell-b --physics mujoco --seed 1 [--n 2]   # 결정성: 틱 해시 비교, 다르면 10회 규칙
    python3 bridge/tr05.py one    --out <폴더> --cell cell-b --variant correct --scenario curtain --physics mujoco --seed 1
    python3 bridge/tr05.py --selftest
"""
import argparse, json, sys, time
from collections import Counter
from pathlib import Path
from run import run, write_json, file_sha, source_tree
from common import app_path, Selftest
from seed_table import accept_seed
VERDICTS=('[PASS]','[FAIL]')
def rows_q(path):
    with (path/'trace.jsonl').open() as f:
        for line in f:
            r=json.loads(line)
            if r['type']=='tick':yield r['Q']

def decide(results,full=10):
    """§6-3 · §8: 두 번이 같으면(모두 [VALID] · 틱 기록 해시 같음) 그 판정. 둘 다 [PLANT_ERROR] 면 다시 하지 않음.
    그 밖은 10회 규칙 — 같은 판정 6번 이상이면 그 판정, 아니면 [UNDECIDED]. [VALID] 가 아닌 실행은 판정 없음(분모에서 빼지 않음)."""
    cats=[r.get('category') for r in results];valid=[r for r in results if r.get('category')=='valid']
    same=len(valid)==len(results)>=2 and all(r['tick_hashes']==valid[0]['tick_hashes'] for r in valid)
    if same:return dict(state='deterministic',decided=valid[0]['status'],need=0)
    if len(results)==2 and cats==['plant_error','plant_error']:return dict(state='plant_error_twice',decided='[PLANT_ERROR]',need=0)
    if len(results)<full:return dict(state='nondeterministic',decided=None,need=full-len(results))
    votes=Counter(r['status'] for r in valid if r['status'] in VERDICTS);top=votes.most_common(1)
    decided=top[0][0] if top and 10*top[0][1]>=6*len(results) else '[UNDECIDED]'
    return dict(state='nondeterministic',decided=decided,need=0,votes=dict(votes),no_verdict=len(results)-sum(votes.values()))

def repeat(out,spec,n=2,full=10):
    results=[];out.mkdir(parents=True,exist_ok=False)
    for i in range(n):results.append(run(out=out/f'r{i+1}',**spec))
    d=decide(results,full)
    while d['need']:
        results.append(run(out=out/f'r{len(results)+1}',**spec));d=decide(results,full)
    valid=[r for r in results if r.get('category')=='valid'];first_diff=None
    if d['state']=='nondeterministic' and len(valid)>=2:
        a,b=valid[0]['tick_hashes'],valid[1]['tick_hashes'];first_diff=next((i+1 for i,(x,y) in enumerate(zip(a,b)) if x!=y),None)
    report=dict(spec={k:str(v) if isinstance(v,Path) else v for k,v in spec.items() if k!='app'},runs=len(results),deterministic=d['state']=='deterministic',state=d['state'],first_different_tick=first_diff,
                votes=dict(Counter(r['status'] for r in results)),decided=d['decided'],trace_hashes=[r.get('trace_hash') for r in results],categories=[r.get('category') for r in results],timing=[r['timing'] for r in results])
    write_json(out/'repeat.json',report);print('[PASS]' if report['deterministic'] else '[FAIL]','determinism',spec['cell_name'],spec['variant'],spec['scenario'],spec['physics'],'runs',len(results),'decided',d['decided'],flush=True);return report

def gate(out,app):
    """fe605e1 verify_3i.py 의 셀 A · B 검사를 이 브랜치 리눅스 빌드 · 빠른 모형으로(포장 · GUI 제외). macOS 3i-final-2 와 같은 항목."""
    app=app_path(app);out.mkdir(parents=True,exist_ok=False);checks=[];started=time.monotonic()
    def check(name,ok,**detail):
        checks.append(dict(name=name,status='[PASS]' if ok else '[FAIL]',**detail));print(checks[-1]['status'],name,flush=True)
        write_json(out/'gate.json',dict(status='[NOT_RUN]',checks=checks))
    fixture=source_tree(app)/'native/tests/external_control/plc-devices-3i-4a-seed-results.json';expected=json.loads(fixture.read_text())
    write_json(out/'classification-source.json',dict(path=str(fixture),sha256=file_sha(fixture)))
    base=dict(app=app,physics='fast')
    for cell,seed in [('cell-a',1),('cell-b',1),('cell-b',2),('cell-b',3)]:
        name=f'{cell}-seed{seed}';r=repeat(out/name,dict(base,cell_name=cell,variant='correct',seed=seed,scenario='normal'),n=2,full=2)
        a=json.loads((out/name/'r1/summary.json').read_text());check(name+' 정상',r['votes'].get('[PASS]')==2,votes=r['votes'])
        check(name+' 결정성',r['deterministic'],trace_hash=r['trace_hashes'][0])
        da=json.loads((out/name/'r1/reference-10ms-differences.json').read_text());db=json.loads((out/name/'r2/reference-10ms-differences.json').read_text())
        # §8 ②: 첫 잠금 전 차이는 예외 모양 하나(셀 B, 시드마다 틱 4461) 외 0. 기계 판정은 refcheck.split(run.py 가 summary['reference'] 에 기록).
        ref=a.get('reference') or {};documented=(not da) if cell=='cell-a' else (ref.get('before_lock')==0 and (ref.get('exception') or {}).get('tick')==4461)
        check(name+' 동일입력 참조 분석',da==db and documented,different_scans=len(da),exception=ref.get('exception'),before_lock=ref.get('before_lock'))
        check(name+' 첫 잠금 없음',a.get('first_lock') is None,first_lock=a.get('first_lock'))
        if cell=='cell-b':
            table=expected['seeds'][str(seed)]['parts']
            check(name+' 시드 ID 분류',len(a['classification'])==len(table)==20 and all(x['defective']==bool(table[x['id']]['class']) and x['correct'] and x['route']==table[x['id']]['route'] for x in a['classification']),
                  routes={x['id']:x['route'] for x in a['classification']},confirmed=dict(out=a['probes'].get('OutArrivals'),chute=a['probes'].get('ChuteArrivals')),expected_confirmed=expected['seeds'][str(seed)].get('confirmed'))
        else:check(name+' A 왕복·주소',a['visits']==['right','left']*3 and a['probes'].get('Rounds')==3)
        ref=run(cell,'correct',out/(name+'-reference'),app=app,controller='reference',seed=seed)
        diffs=sum(1 for x,y in zip(rows_q(out/name/'r1'),rows_q(out/(name+'-reference'))) if x!=y)
        check(name+' 폐루프 참조 기록',ref['status']=='[PASS]' and ref['ticks']==a['ticks'],different_ticks=diffs)
    negatives=[('cell-a','swapped-sensors','normal'),('cell-a','late-reverse','normal'),('cell-b','push-timing-off','normal'),('cell-b','ignore-curtain','curtain'),('cell-b','no-sort-check','flow')]
    for cell,variant,scenario in negatives:
        r=run(cell,variant,out/('negative-'+variant),app=app,scenario=scenario);events={e['name'] for e in r.get('events',[])};judge={e['name'] for e in r.get('judgments',[])}
        detected={'swapped-sensors':'PART_DROP' in events,'late-reverse':'PART_DROP' in events,'push-timing-off':bool(events&{'PUSH_TOO_EARLY','PUSH_TOO_LATE','PUSH_MISSED'}),'ignore-curtain':'PLC_CURTAIN_IGNORED' in judge,'no-sort-check':'SORT_CHECK_MISSING' in events|judge}[variant]
        check(variant+' 음성 검출',r['status']=='[FAIL]' and detected,process_status=r['status'],events=sorted(events),judgments=sorted(judge),fault_code=r.get('probes',{}).get('FaultCode'),first_lock=r.get('first_lock'))
    # fe605e1 verify_3i 와 같은 500 틱 커튼 검사(§3-5 표의 1,000 틱과 다르므로 비표준 표시 — 게이트 전용)
    r=run('cell-b','correct',out/'curtain',app=app,ticks=500,scenario='curtain',nonstandard_ticks=True);check('운전 중 커튼 정지',r['status']=='[PASS]',safety=r.get('safety'))
    r=run('cell-b','correct',out/'recovery',app=app,scenario='recovery');check('격리·복귀·추적 초기화',r['status']=='[PASS]' and r['same_input_reference_differences']==0,recovery=r.get('recovery'),events=r.get('events'))
    final=dict(status='[PASS]' if all(c['status']=='[PASS]' for c in checks) else '[FAIL]',checks=checks,elapsed_s=time.monotonic()-started,app=str(app),exe_sha256=file_sha(app))
    write_json(out/'gate.json',final);print(final['status'],'gate',flush=True);return final

def selftest():
    T=Selftest('tr05')
    def R(cat,status='[PASS]',h='a'):return dict(category=cat,status=status,tick_hashes=[h])
    T.red_green('두 번 실행 해시가 다르면 결정적이 아님',lambda:decide([R('valid'),R('valid',h='b')])['state']=='deterministic',lambda:decide([R('valid'),R('valid')])['state']=='deterministic')
    T.red_green('한 번만 [PLANT_ERROR] 면 10회 규칙으로',lambda:decide([R('plant_error','[PLANT_ERROR]'),R('valid')])['need']==0,lambda:decide([R('plant_error','[PLANT_ERROR]'),R('valid')])['need']==8 and decide([R('plant_error','[PLANT_ERROR]')]*2)['decided']=='[PLANT_ERROR]')
    ten=[R('valid','[FAIL]',str(i)) for i in range(6)]+[R('valid','[PASS]',str(i)) for i in range(4)]
    five=[R('valid','[FAIL]',str(i)) for i in range(5)]+[R('invalid','[INVALID]',str(i)) for i in range(5)]
    T.red_green('10회 규칙: 판정 없음 5번이면 [UNDECIDED](분모에서 빼지 않음) / 6:4 는 다수 판정',lambda:decide(five)['decided']!='[UNDECIDED]',lambda:decide(ten)['decided']=='[FAIL]')
    def refused(f):
        try:f();return False
        except SystemExit:return True
    T.red_green('시드 0~3 밖은 --dev-seed 없이 거부',lambda:not refused(lambda:accept_seed(77,False)),lambda:refused(lambda:accept_seed(77,False)) and accept_seed(77,True)=='dev')
    T.finish()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0]);p.add_argument('mode',nargs='?',choices=['gate','repeat','one']);p.add_argument('--out',type=Path);p.add_argument('--app',type=Path)
    p.add_argument('--cell',choices=['cell-a','cell-b'],default='cell-b');p.add_argument('--variant',default='correct');p.add_argument('--scenario',default='normal');p.add_argument('--physics',choices=['fast','mujoco'],default='fast')
    p.add_argument('--seed',type=int,default=1);p.add_argument('--dev-seed',action='store_true',help='시드 0~3 밖의 개발용 시드임을 표시');p.add_argument('--seed-table',type=Path);p.add_argument('--seed-table-sha256')
    p.add_argument('--ticks',type=int);p.add_argument('--nonstandard-ticks',action='store_true');p.add_argument('--n',type=int,default=2)
    p.add_argument('--belt-factor',type=float,default=1.0);p.add_argument('--physics-value',action='append',default=[],metavar='NAME=VALUE');p.add_argument('--initial-z-offset',type=float,default=0.0);p.add_argument('--selftest',action='store_true');a=p.parse_args()
    if a.selftest:selftest()
    if not a.mode or not a.out:p.error('mode 와 --out 필요')
    if a.mode=='gate':sys.exit(0 if gate(a.out,a.app)['status']=='[PASS]' else 1)
    accept_seed(a.seed,a.dev_seed,a.seed_table,a.seed_table_sha256);values={k:float(v) for k,v in (x.split('=',1) for x in a.physics_value)} or None
    spec=dict(app=app_path(a.app),cell_name=a.cell,variant=a.variant,scenario=a.scenario,physics=a.physics,seed=a.seed,ticks=a.ticks,belt_factor=a.belt_factor,physics_values=values,initial_z_offset=a.initial_z_offset,nonstandard_ticks=a.nonstandard_ticks)
    if a.mode=='repeat':r=repeat(a.out,spec,n=a.n);sys.exit(0 if r['deterministic'] else 1)
    r=run(out=a.out,**spec);sys.exit(0 if r['status']=='[PASS]' else 1)
