"""TR-2026-05 회차 실행기(구현 목록 I9 · I14, 사전 등록 §5-3 · §6-3 · §6-4 · §8 ③ ④ · §14) — 새로 씀.

시드 표 · 고정값 파일을 읽어 주 162 · M 쌍별 2회째 106 · F 게이트 2회째 9 · 열린 고리 14 · P8 감도 156 · 모형 가정 설정 10 × (f + 2) · E4 100 을 돌린다.
- 시작 전 거부: 고정값 파일(스크립트 · 래더 · 셀 · 시드 표 sha256, 앱 · libmujoco sha256, 40자 빌드 커밋) 하나라도 다르면 시작하지 않는다.
- 실행마다 run.json(조건 · 묶음 · 설정 · 반복 번호)과 results.jsonl 한 줄. [VALID] = 실행기 범주 valid ∧ 틱 수 표 ∧ M 은 setup_sha256 · values_sha256 이 고정값 · 시드 표와 같음.
- [INVALID] 은 같은 입력으로 최대 2번 다시(모든 시도 보존). M 쌍은 두 번 비교 → 다르면 10회 규칙(한 번만 [PLANT_ERROR] 도 같음), 둘 다 [PLANT_ERROR] 면 멈춤.
- 실행 전체 무효(§8): F 게이트 불일치 · 정답 래더 참조 일치 무효 · 한 M 조건 [PLANT_ERROR] 10 % 초과 · 기대 실행 수 부족 · 모드 확인 실패 → 회차 폴더를 _invalid/<시각>_<원인>/ 로 옮김.
- 감도 · 모형 가정 설정 표(I14)는 SETTINGS. 모형 가정 설정 대상 = M0 에서 뒤바뀐 셀 B normal 배치 + 묶음 3 · 4 에서 뒤바뀌지 않은 첫 배치.
    python3 bridge/round.py run --app <앱> --seed-table <표> --seed-table-sha256 <64자> --fixed <고정값.json> --fixed-sha256 <64자> --out <회차 폴더>
    python3 bridge/round.py run --dev --dev-batches 1:5 --stages main,repeat,gate --app <앱> --out <폴더>     # 개발 시험(이미 본 시드만)
    python3 bridge/round.py fixed --app <앱> --out <고정값.json> [--seed-table <표>]      # 지금 상태로 고정값 파일 만들기(동결 때)
    python3 bridge/round.py settings-check --app <앱> [--seed 1]                          # I14: 설정마다 적재 응답의 물리값 · 해시 확인
    python3 bridge/round.py --selftest
"""
import argparse, datetime, json, shutil, sys
from pathlib import Path
from common import ROOT, app_path, file_sha, sha_bytes, read_json, write_json, Selftest
from run import run, ticks_category, source_tree
import tables, seed_table
P8_B=[('transition_mu_0.5',dict(physics_values=dict(transition_mu_scale=.5))),('transition_mu_1.5',dict(physics_values=dict(transition_mu_scale=1.5))),('wall_friction_0.3',dict(physics_values=dict(wall_friction=.3))),
      ('chute_x_force_off',dict(physics_values=dict(chute_x_force=0))),('friction_0.7',dict(physics_values=dict(friction_scale=.7))),('friction_1.3',dict(physics_values=dict(friction_scale=1.3))),('belt_0.95',dict(belt_factor=.95)),('belt_1.05',dict(belt_factor=1.05))]
P8_A=[x for x in P8_B if x[0].startswith(('friction','belt'))]
MODEL=[('sensor_rotated',dict(physics_values=dict(sensor_footprint_rotated=1))),('step_0.0005',dict(physics_values=dict(fixed_step_s=.0005))),('facets_20',dict(physics_values=dict(transition_facets=20))),
       ('deck_static_0',dict(physics_values=dict(deck_friction_static_weight=0))),('torsion_0',dict(physics_values=dict(torsional_friction_m=0))),('torsion_0.02',dict(physics_values=dict(torsional_friction_m=.02))),
       ('z_+0.005',dict(initial_z_offset=.005)),('z_-0.005',dict(initial_z_offset=-.005))]
BOTH={'belt_0.95','belt_1.05','z_+0.005','z_-0.005'}  # F 와 M 둘 다
SETTINGS=dict(p8_cell_b=dict(P8_B),p8_cell_a=dict(P8_A),model=dict(MODEL))
A_LADDERS=('correct','late-reverse','swapped-sensors');A_SCEN=('normal','cycle-stop')
B_EACH=[('correct','normal'),('correct','curtain'),('push-timing-off','normal'),('ignore-curtain','curtain')];B_BIN5=[('correct','recovery'),('no-sort-check','flow')]
def S(group,cond,cell,variant,scenario,seed=1,bin=None,setting=None,rep=1):return dict(group=group,condition=cond,cell=cell,variant=variant,scenario=scenario,seed=seed,bin=bin,setting=setting,rep=rep)
def b_pairs(batches):
    out=[(v,s,seed,b) for seed,b in batches for v,s in B_EACH]
    first5=next((x for x in batches if x[1]==5),None)
    return out+([(v,s,first5[0],5) for v,s in B_BIN5] if first5 else [])
def plan_main(batches,m1=True):
    p=[S('main',c,'cell-a',v,s) for c in ('F','M0') for v in A_LADDERS for s in A_SCEN]
    return p+[S('main',c,'cell-b',v,s,seed,b) for c in (('F','M0','M1') if m1 else ('F','M0')) for v,s,seed,b in b_pairs(batches)]
def plan_repeat(main):return [dict(m,group='repeat',rep=2) for m in main if m['condition']!='F']
def plan_gate(batches):
    first=lambda b:next((x for x in batches if x[1]==b),None);g=[S('gate','F','cell-a',v,'normal',rep=2) for v in A_LADDERS]
    if first(3):g+=[S('gate','F','cell-b',v,s,first(3)[0],3,rep=2) for v,s in B_EACH]
    if first(5):g+=[S('gate','F','cell-b',v,s,first(5)[0],5,rep=2) for v,s in B_BIN5]
    return g
def plan_openloop(batches):return [S('openloop','M0','cell-b','correct','normal',seed,b) for seed,b in batches]+[S('openloop','M0','cell-a','correct',s) for s in A_SCEN]
def plan_p8(batches):
    p=[]
    for seed,b in batches:
        for name,_ in P8_B:p+=[S('p8','M0','cell-b','correct','normal',seed,b,name)]+([S('p8','F','cell-b','correct','normal',seed,b,name)] if name in BOTH else [])
    for v in A_LADDERS:
        for s in A_SCEN:
            for name,_ in P8_A:p+=[S('p8','M0','cell-a',v,s,setting=name)]+([S('p8','F','cell-a',v,s,setting=name)] if name in BOTH else [])
    return p
FROZEN=dict(main=162,repeat=106,gate=9,openloop=14,p8=156,e4=100)  # 동결 문안(v1.0 §5-2 · §5-3 · §8 ④)의 수 — 공식 모드는 계획을 이 상수와 대조(배치 목록에서 셈한 값과 대조하지 않음). 모형 가정 = 10 × (f + 2)
FROZEN_BATCHES=dict(total=12,per_bin=4,bins=(3,4,5))
def e4_ids(variants_json):return [v['id'] for v in read_json(variants_json)['variants'] if v['sampled'] and v['cell']=='cell-a']
def official_plan_check(batches,m1,n_e4):
    errs=[];bins={b:sum(1 for _,x in batches if x==b) for _,b in batches}
    if len(batches)!=FROZEN_BATCHES['total'] or sorted(bins)!=list(FROZEN_BATCHES['bins']) or any(v!=FROZEN_BATCHES['per_bin'] for v in bins.values()) or len({s for s,_ in batches})!=len(batches):
        errs.append(f'배치 {len(batches)}개 · 묶음별 {bins} — 동결 수 12(묶음 3 · 4 · 5 각 4)와 다름')
    main=plan_main(batches,m1);counts=dict(main=len(main),repeat=len(plan_repeat(main)),gate=len(plan_gate(batches)),openloop=len(plan_openloop(batches)),p8=len(plan_p8(batches)),e4=len(plan_e4(range(n_e4))))
    errs+=[f'{k} {counts[k]} ≠ 동결 {v}' for k,v in FROZEN.items() if counts[k]!=v]
    return counts,errs
def model_targets(batches,out):
    flipped=[(s,b) for s,b in batches if (lambda f,m:f and m and f['v'] and m['v'] and f['v']!=m['v'])(out.get(('F',('cell-b','correct','normal',s))),out.get(('M0',('cell-b','correct','normal',s))))]
    extra=[next(((s,b) for s,b in batches if b==bb and (s,b) not in flipped),None) for bb in (3,4)]
    return flipped+[x for x in extra if x]
def plan_model(targets):return [S('model',c,'cell-b','correct','normal',seed,b,name) for seed,b in targets for name,_ in MODEL for c in (('F','M0') if name in BOTH else ('M0',))]
def plan_e4(ids):return [S('e4',c,'cell-a',f'e4:{i}',s) for i in ids for s in A_SCEN for c in ('F','M0')]
def expected(batches,m1=True,f=0,e4=25):
    nb=len(batches);b5=any(b==5 for _,b in batches);nB=4*nb+2*b5
    return dict(main=12+(3 if m1 else 2)*nB,repeat=6+nB+(nB if m1 else 0),gate=3+4*any(b==3 for _,b in batches)+2*b5,openloop=nb+2,p8=nb*10+36,model=10*f,e4=4*e4)

def e4_ladders(variants_json,dest,sha_table=None):
    """TR-2026-03 셀 A 연동 제거 변종(추출된 25종): 정답 래더의 지정 접점 칸을 {"k":"hwire"} 로 바꾼 JSON(JS JSON.stringify 와 같은 바이트)."""
    lst=read_json(variants_json)['variants'];src=json.loads((ROOT/'ladders/cell-a/correct/program.ldprog.json').read_text());ids=[];bad=[]
    for v in [x for x in lst if x['sampled'] and x['cell']=='cell-a']:
        p=json.loads(json.dumps(src))
        for r,c in v['cells']:
            cell=p['rungs'][v['rung']]['grid'][r][c]
            if cell.get('k')!='contact' or cell.get('tag')!=v['tag']:raise ValueError('variant mismatch '+v['id'])
            p['rungs'][v['rung']]['grid'][r][c]={'k':'hwire'}
        text=json.dumps(p,ensure_ascii=False,separators=(',',':'));d=Path(dest)/v['id'];d.mkdir(parents=True,exist_ok=True);(d/'program.ldprog.json').write_text(text)
        shutil.copy(ROOT/'ladders/cell-a/correct/monitor-map.json',d/'monitor-map.json');ids.append(v['id'])
        if sha_table and sha_table.get(v['id'],{}).get('program')!=sha_bytes(text.encode()):bad.append(v['id'])
    return ids,bad

def check_fixed(fixed,app,seed_table_path=None):
    """§8 실행 시작 전 거부."""
    errs=[];c=fixed.get('build_commit') or ''
    if not (len(c)==40 and all(x in '0123456789abcdef' for x in c)):errs.append('빌드 커밋이 40자 16진수가 아님')
    if fixed.get('exe_sha256')!=file_sha(app):errs.append('앱 실행 파일 sha256 다름')
    lib=source_tree(app)/'native/third_party/simulation/mujoco-3.12.0/lib/libmujoco.so.3.12.0'
    if fixed.get('libmujoco_sha256')!=(file_sha(lib) if lib.exists() else None):errs.append('libmujoco sha256 다름')
    for rel,want in (fixed.get('files') or {}).items():
        p=ROOT/rel
        if not p.exists() or file_sha(p)!=want:errs.append(f'{rel} sha256 다름')
    if seed_table_path and fixed.get('seed_table_sha256')!=file_sha(seed_table_path):errs.append('시드 표 sha256 다름')
    for rel,want in (fixed.get('app_files') or {}).items():
        if file_sha(source_tree(app)/rel)!=want:errs.append(f'앱 쪽 {rel} sha256 다름')
    return errs
EXTERNAL=['native/third_party/plc-devices/cells/cell-a-shuttle.plccell.json','native/third_party/plc-devices/cells/cell-a-shuttle.io-map.json','native/third_party/plc-devices/cells/cell-b-sort.plccell.json',
          'native/third_party/plc-devices/cells/cell-b-sort.io-map.json','native/third_party/plc-devices/library/asm-pusher/versions/1.5.0/device.json','native/tests/external_control/logic.py',
          'native/tests/external_control/plc-devices-3i-4a-seed-results.json','native/third_party/plc-devices/tests/phase3c-control.json']
def make_fixed(app,seed_table_path=None,e4_variants=None,e4_sha=None):
    files=[p for p in sorted((ROOT/'bridge').glob('*')) if p.suffix in ('.py','.mjs')]+sorted(ROOT.glob('ladders/**/program.ldprog.json'))+sorted(ROOT.glob('ladders/cell-b-m1/*.json'))+sorted(ROOT.glob('cells/*.json'))+sorted(ROOT.glob('experiments/**/*.md'))+[p for p in (ROOT/'SOURCES.json',ROOT/'calibration.json',ROOT/'seed-table.json') if p.exists()]
    src=source_tree(app);lib=src/'native/third_party/simulation/mujoco-3.12.0/lib/libmujoco.so.3.12.0';import subprocess
    commit=subprocess.run(['git','--no-optional-locks','-C',str(src),'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
    setup={}
    for cell,sets in (('cell-a',dict(default={},**SETTINGS['p8_cell_a'])),('cell-b',dict(default={},**SETTINGS['p8_cell_b'],**SETTINGS['model']))):
        setup[cell]={}
        for name,st in sets.items():
            try:L=seed_table.Loader(app,cell,'mujoco',st);setup[cell][name]=L.load(1)['setup_sha256'];L.close()
            except Exception as e:setup[cell][name]=None
    return dict(schema='tr05-fixed/1',build_commit=commit,exe_sha256=file_sha(app),libmujoco_sha256=file_sha(lib) if lib.exists() else None,seed_table_sha256=file_sha(seed_table_path) if seed_table_path else None,
                files={str(p.relative_to(ROOT)):file_sha(p) for p in files},setup_sha256=setup,app_files={r:file_sha(src/r) for r in EXTERNAL if (src/r).exists()},
                vendor_tree_sha256=read_json(ROOT/'SOURCES.json')['plc_simulator']['tree_sha256'],node=subprocess.run(['node','--version'],capture_output=True,text=True).stdout.strip(),
                e4={Path(x).name:file_sha(x) for x in (e4_variants,e4_sha) if x})

class Round:
    def __init__(self,out,app,fixed=None,seeds=None,dev=False,m1_dir=ROOT/'ladders/cell-b-m1',e4_dir=None):
        self.out=Path(out);self.app=app;self.fixed=fixed or {};self.seeds=seeds;self.dev=dev;self.m1=Path(m1_dir);self.e4_dir=e4_dir;self.rows=[];self.out.mkdir(parents=True,exist_ok=False)
    def kwargs(self,s):
        k=dict(cell_name=s['cell'],variant=s['variant'],scenario=s['scenario'],seed=s['seed'],physics='fast' if s['condition']=='F' else 'mujoco',app=self.app)
        st=dict(SETTINGS['p8_cell_b'],**SETTINGS['model']) if s['cell']=='cell-b' else SETTINGS['p8_cell_a']
        if s['setting']:k.update(st[s['setting']])
        if s['condition']=='M1':k.update(program=self.m1/s['variant']/'program.ldprog.json',reference_params=read_json(self.m1/'m1-reference-params.json'))
        if s['variant'].startswith('e4:'):k['program']=Path(self.e4_dir)/s['variant'][3:]/'program.ldprog.json'
        return k
    def valid(self,s,r):
        if r.get('category')!='valid':return False,r.get('error') or r.get('category')
        if ticks_category(r,s['cell'],'correct' if s['variant'].startswith('e4:') else s['variant'],s['scenario'])!='valid':return False,'틱 수가 시나리오 표와 다름'
        if s['condition']!='F':
            ph=r.get('physics_report') or {};want=(self.fixed.get('setup_sha256') or {}).get(s['cell'],{}).get(s['setting'] or 'default')
            if want and ph.get('setup_sha256')!=want:return False,'setup_sha256 ≠ 고정값'
            if self.seeds and s['cell']=='cell-b':
                v=self.seeds['values'].get(str(s['seed']),{}).get(s['setting'] or 'default',{}).get('values_sha256')
                if v and ph.get('values_sha256')!=v:return False,'values_sha256 ≠ 시드 표'
        return True,None
    def name(self,s,a=1):return f"{s['group']}/{s['condition']}/{s['cell']}__{s['variant'].replace(':','-')}__{s['scenario']}__s{s['seed']}"+(f"__{s['setting']}" if s['setting'] else '')+f"__r{s['rep']}"+(f'__a{a}' if a>1 else '')
    def execute(self,s,perturb=None):
        attempts=[]
        for a in (1,2,3):
            d=self.out/self.name(s,a)
            try:r=run(out=d,debug_perturb=perturb,**self.kwargs(s))
            except ValueError as e:r=dict(category='refused',error=str(e));d.mkdir(parents=True,exist_ok=True)
            ok,why=self.valid(s,r);write_json(d/'run.json',dict(s,attempt=a));attempts.append(str(d.relative_to(self.out)))
            if r.get('category')!='invalid':break
        row=dict(s,run_id=self.name(s,a).replace('/','.'),dir=attempts[-1],attempts=attempts,valid=ok,category_round='valid' if ok else ('plant_error' if r.get('category')=='plant_error' else 'invalid'),reason=why,status=r.get('status'),trace_hash=r.get('trace_hash'),
                 reference_invalid=(r.get('reference') or {}).get('invalid'),mode_failed='mode check failed' in str(r.get('error','')))
        with (self.out/'results.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        self.rows.append(row);return row,r
    def pair_repeat(self,s,perturb=None):
        """§6-3: 2회째. 다르면 10회까지(10회 규칙). 둘 다 [PLANT_ERROR] 면 멈춤."""
        first=next(x for x in self.rows if x['group']=='main' and all(x[k]==s[k] for k in ('condition','cell','variant','scenario','seed')))
        second,_=self.execute(s,perturb)
        if first['trace_hash'] and first['trace_hash']==second['trace_hash'] and first['valid'] and second['valid']:return 'deterministic'
        if first['category_round']==second['category_round']=='plant_error':return 'plant_error_twice'
        for rep in range(3,11):self.execute(dict(s,rep=rep))
        return 'nondeterministic'
    def whole_invalid(self):
        causes=[]
        for g in [x for x in self.rows if x['group']=='gate']:
            m=next((x for x in self.rows if x['group']=='main' and x['condition']=='F' and all(x[k]==g[k] for k in ('cell','variant','scenario','seed'))),None)
            if not m or m['trace_hash']!=g['trace_hash']:causes.append('F 게이트');break
        if any(x['reference_invalid'] for x in self.rows if x['variant']=='correct' and x['group'] in ('main','repeat','gate')):causes.append('참조 일치')
        for c in ('M0','M1'):
            rs=[x for x in self.rows if x['condition']==c and x['group'] in ('main','repeat')]
            if rs and 10*sum(x['category_round']=='plant_error' for x in rs)>len(rs):causes.append(f'{c} 플랜트 오류 10 % 초과')
        if any(x['mode_failed'] for x in self.rows):causes.append('모드 확인')
        return causes
    def move_invalid(self,cause):
        dest=self.out.parent/'_invalid'/f"{datetime.datetime.now().strftime('%Y%m%dT%H%M%S')}_{cause.replace(' ','-')}";dest.parent.mkdir(exist_ok=True);shutil.move(str(self.out),dest);return dest

def run_round(a):
    app=app_path(a.app);dev=a.dev
    if not dev:
        if not (a.seed_table and a.seed_table_sha256 and a.fixed and a.fixed_sha256):sys.exit('[REFUSED] 공식 회차: --seed-table/--seed-table-sha256/--fixed/--fixed-sha256 모두 필요')
        if file_sha(a.fixed)!=a.fixed_sha256 or file_sha(a.seed_table)!=a.seed_table_sha256:sys.exit('[REFUSED] 고정값 파일 또는 시드 표 sha256 이 주어진 값과 다르다')
        if a.stages!='all' or a.inject_nondeterminism:sys.exit('[REFUSED] 공식 회차는 전체 단계만, 시험용 주입 없음')
    fixed=read_json(a.fixed) if a.fixed else {};seeds=read_json(a.seed_table) if a.seed_table else None
    if fixed:
        errs=check_fixed(fixed,app,a.seed_table)
        for x in (a.e4_variants,a.e4_sha):
            if x and fixed.get('e4') and fixed['e4'].get(Path(x).name)!=file_sha(x):errs.append(f'E4 {Path(x).name} sha256 다름')
        if errs:sys.exit('[REFUSED] 고정 해시 불일치 — '+'; '.join(errs))
    if seeds:  # 배치 선택 — 자기 시험이 이 줄부터 m1= 앞까지를 그대로 실행한다(90cfe55c 판의 if/else 결함 수정)
        batches=[(it['seed'],int(b)) for b,items in sorted(seeds['sets']['dev' if dev else 'official'].items()) for it in items]  # 개발 모드 + 시드 표 = 개발 시드(양성 대조 2)
        if dev:[seed_table.accept_seed(s,True,a.seed_table) for s,_ in batches]
    else:
        batches=[(int(x.split(':')[0]),int(x.split(':')[1])) for x in (a.dev_batches or '').split(',') if x]
        for s,_ in batches:seed_table.accept_seed(s,dev)
    m1=(ROOT/'ladders/cell-b-m1/correct/program.ldprog.json').exists();e4ids=[]
    if not m1 and not dev:sys.exit('[REFUSED] M1 래더 없음(ladders/cell-b-m1/) — 교정 · 재생성 뒤에 공식 회차')
    if not dev and a.mode!='plan':
        counts,errs=official_plan_check(batches,m1,len(e4_ids(a.e4_variants)) if a.e4_variants else 0)
        if errs:sys.exit('[REFUSED] 공식 계획이 동결 수와 다르다 — '+'; '.join(errs))
    if a.mode=='plan':
        counts,errs=official_plan_check(batches,m1,len(e4_ids(a.e4_variants)) if a.e4_variants else 0)
        print(json.dumps(dict(batches=batches,m1=m1,counts=counts,frozen=FROZEN,model='10 × (f + 2) — f 는 M0 주 실행 뒤에 정해짐',errors=errs),ensure_ascii=False,indent=1));print('[PASS]' if not errs else '[FAIL]','plan only (앱 실행 없음)');return None
    R=Round(a.out,app,fixed,seeds,dev);R.e4_dir=R.out/'e4-ladders';stages=set(a.stages.split(',')) if a.stages!='all' else {'main','repeat','gate','openloop','p8','model','e4'}
    main=plan_main(batches,m1);exp=expected(batches,m1);only=set(a.only.split(',')) if a.only else None
    if only:main=[s for s in main if f"{s['cell']}:{s['variant']}:{s['scenario']}" in only]
    write_json(R.out/'plan.json',dict(batches=batches,m1=m1,stages=sorted(stages),expected=exp,dev=dev,only=sorted(only) if only else None,settings=SETTINGS))
    for s in main:R.execute(s)
    if 'repeat' in stages:
        lamp=lambda cell:sorted((x['tag'] for x in read_json(ROOT/'cells'/f'{cell}.tagmap.json')['bindings'] if x['direction']=='out'),key=lambda t:'Lamp' not in t)[0]  # 셀 B 는 판정과 무관한 램프 Q 한 틱
        for i,s in enumerate(plan_repeat(main)):R.pair_repeat(s,(300,lamp(s['cell'])) if a.inject_nondeterminism and i==0 else None)
    if 'gate' in stages:
        for s in plan_gate(batches):
            if not only or f"{s['cell']}:{s['variant']}:{s['scenario']}" in only:R.execute(s)
    causes=R.whole_invalid()
    if causes:print('[INVALID] 실행 전체 무효:',causes,'→',R.move_invalid(causes[0]));sys.exit(2)
    if 'openloop' in stages:
        from replay import replay
        for s in plan_openloop(batches):
            src=next(x for x in R.rows if x['group']=='main' and x['condition']=='F' and x['cell']==s['cell'] and x['variant']=='correct' and x['scenario']==s['scenario'] and x['seed']==s['seed'])
            d=R.out/R.name(s);sm=replay(R.out/src['dir'],d,app,'mujoco');write_json(d/'run.json',s)
            row=dict(s,run_id=R.name(s).replace('/','.'),dir=str(d.relative_to(R.out)),valid=True,category_round='valid')
            with (R.out/'results.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
            R.rows.append(row)
    if 'p8' in stages:
        for s in plan_p8(batches):R.execute(s)
    if 'model' in stages:
        out=tables.outcomes(tables.load(R.out));targets=model_targets(batches,out);exp['model']=10*len(targets)
        f=len(targets)-sum(1 for t in targets if (lambda F,M:not(F and M and F['v'] and M['v'] and F['v']!=M['v']))(out.get(('F',('cell-b','correct','normal',t[0]))),out.get(('M0',('cell-b','correct','normal',t[0])))))
        if not dev:exp['model']=10*(f+2)  # 동결 §8 ④: 10 × (f + 2)
        for s in plan_model(targets):R.execute(s)
    if 'e4' in stages and a.e4_variants:
        e4ids,bad=e4_ladders(a.e4_variants,R.e4_dir,read_json(a.e4_sha) if a.e4_sha else None)
        if bad:sys.exit(f'[REFUSED] E4 변종 sha256 불일치 {bad[:3]}')
        for s in plan_e4(e4ids):R.execute(s)
    if not dev:exp=dict(FROZEN,model=exp['model'])  # 공식: 동결 문안의 고정 수와 대조(배치 목록에서 셈하지 않음)
    got={g:sum(1 for x in R.rows if x['group']==g and x.get('rep',1)<=2) for g in exp};short=[g for g in stages if g in exp and not only and got.get(g,0)!=exp[g]]
    write_json(R.out/'counts.json',dict(expected=exp,got=got,short=short,stages=sorted(stages)))
    if short and not dev:print('[INVALID] 기대 실행 수 부족',short,'→',R.move_invalid('실행 수'));sys.exit(2)
    print('[PASS]' if not short else '[WARN]','round',got,'short',short);return R

def settings_check(app,seed=1):
    """I14: 설정마다 적재 응답의 state.physics.values 가 의도한 값으로 바뀌고 나머지는 그대로인가, 벨트 · 초기 위치는 setup 불변 · values 변화."""
    app=app_path(app);res=[]
    for cell,sets in (('cell-a',SETTINGS['p8_cell_a']),('cell-b',dict(SETTINGS['p8_cell_b'],**SETTINGS['model']))):
        L=seed_table.Loader(app,cell,'mujoco');base=L.load(seed);L.close()
        for name,st in sets.items():
            try:L=seed_table.Loader(app,cell,'mujoco',st);d=L.load(seed);L.close()
            except Exception as e:res.append(dict(cell=cell,setting=name,status='[FAIL]',error=f'앱이 이 설정을 받지 않음: {str(e)[:120]}'));continue
            pv=st.get('physics_values') or {};changed={k for k in d['values'] if d['values'][k]!=base['values'].get(k)}
            if pv:ok=changed==set(pv) and all(d['values'][k]==v for k,v in pv.items()) and d['setup_sha256']!=base['setup_sha256']
            else:ok=not changed and d['setup_sha256']==base['setup_sha256'] and (d['values_sha256']!=base['values_sha256'] if cell=='cell-b' else d['values_sha256']==base['values_sha256']) and ('initial_z_offset' not in st or all(abs(z-st['initial_z_offset'])<1e-9 for z in d['z']))  # 셀 A 해시는 플랜트 매개변수를 넣지 않는다(§3-1)
            res.append(dict(cell=cell,setting=name,status='[PASS]' if ok else '[FAIL]',changed=sorted(changed),setup_same=d['setup_sha256']==base['setup_sha256'],values_same=d['values_sha256']==base['values_sha256']))
    return res

# 음성 대조: 90cfe55c 판(공식 회차 tr05-official-1 무효 원인)의 배치 선택 줄 그대로.
DEFECT_90CFE55C='''if seeds:batches=[(it['seed'],int(b)) for b,items in sorted(seeds['sets']['dev' if dev else 'official'].items()) for it in items]
if seeds and dev:[seed_table.accept_seed(s,True,a.seed_table) for s,_ in batches]
else:
    batches=[(int(x.split(':')[0]),int(x.split(':')[1])) for x in (a.dev_batches or '').split(',') if x]
    for s,_ in batches:seed_table.accept_seed(s,dev)
'''
def selection_code(path):  # round.py 파일에서 run_round 의 배치 선택 줄(첫 `    if seeds` 부터 `    m1=(ROOT` 앞까지)
    import textwrap;L=Path(path).read_text().splitlines();i=next(n for n,l in enumerate(L) if l.startswith('    if seeds'));j=next(n for n,l in enumerate(L) if l.startswith('    m1=(ROOT'))
    return textwrap.dedent('\n'.join(L[i:j]))
def official_plan_from(code,seeds,n_e4=25):
    import types;ns=dict(seeds=seeds,dev=False,a=types.SimpleNamespace(dev_batches=None,seed_table=None),seed_table=seed_table);exec(code,ns)
    return official_plan_check(ns['batches'],True,n_e4)
def selftest(app=None,against=None):
    T=Selftest('round')
    tab=dict(sets=dict(official={str(b):[dict(seed=1000*b+i) for i in range(4)] for b in (3,4,5)},calib={'3':[dict(seed=5)]},dev={str(b):[dict(seed=9000+b)] for b in (3,4,5)}))
    T.red_green('공식 계획 경로: 결함 판(90cfe55c)의 배치 선택은 빈 목록 → 동결 수와 달라 거부 / 고친 판은 12 배치 · 162 · 106 · 9 · 14 · 156 · 100',
                lambda:not official_plan_from(DEFECT_90CFE55C,tab)[1],lambda:official_plan_from(selection_code(__file__),tab)==(dict(main=162,repeat=106,gate=9,openloop=14,p8=156,e4=100),[]))
    if against:T.red_green(f'실제 결함 파일 {Path(against).name} 의 배치 선택 줄로 돌리면 거부 / 이 파일은 통과',lambda:not official_plan_from(selection_code(against),tab)[1],lambda:not official_plan_from(selection_code(__file__),tab)[1])
    T.check('동결 상수가 문안 수와 같음(162 · 106 · 9 · 14 · 156 · 100, 12 배치 = 묶음 3 · 4 · 5 각 4)',FROZEN==dict(main=162,repeat=106,gate=9,openloop=14,p8=156,e4=100) and FROZEN_BATCHES['total']==12)
    T.check('배치가 11 개면 거부(한 묶음 3개)',bool(official_plan_check([(s['seed'],int(b)) for b,v in tab['sets']['official'].items() for s in v][1:],True,25)[1]))
    full=[(100+10*b+i,b) for b in (3,4,5) for i in range(4)];m=plan_main(full)
    T.check('기대 실행 수 식 = 계획 수',expected(full)==dict(main=162,repeat=106,gate=9,openloop=14,p8=156,model=0,e4=100))
    T.red_green('기대 실행 수: 주 162 · M 2회째 106 · 게이트 9 · 열린 고리 14 · P8 156 · E4 100(M1 빠지면 112)',lambda:len(plan_main(full,False))==162,
                lambda:(len(m),len(plan_repeat(m)),len(plan_gate(full)),len(plan_openloop(full)),len(plan_p8(full)),len(plan_e4(range(25))))==(162,106,9,14,156,100))
    T.check('모형 가정 설정: 배치당 10 실행(M 전용 6 + 초기 위치 ± 의 F · M 4)',len(plan_model([(1,5)]))==10)
    o={('F',('cell-b','correct','normal',s)):dict(v='[PASS]') for s,_ in full};o.update({('M0',('cell-b','correct','normal',s)):dict(v='[FAIL]' if b==5 else '[PASS]') for s,b in full})
    T.red_green('모형 가정 설정 대상 = 뒤바뀐 배치 전부 + 묶음 3 · 4 의 뒤바뀌지 않은 첫 배치',lambda:model_targets(full,o)==[x for x in full if x[1]==5],lambda:model_targets(full,o)==[x for x in full if x[1]==5]+[(130,3),(140,4)])
    fx=dict(build_commit='a'*40,exe_sha256='x',libmujoco_sha256='y',files={'bridge/run.py':file_sha(ROOT/'bridge/run.py')})
    if app:
        ap=app_path(app);good=dict(fx,exe_sha256=file_sha(ap),libmujoco_sha256=file_sha(source_tree(ap)/'native/third_party/simulation/mujoco-3.12.0/lib/libmujoco.so.3.12.0'))
        T.red_green('고정 해시 하나를 바꾸면 시작 거부',lambda:not check_fixed(dict(good,files={'bridge/run.py':'0'*64}),ap),lambda:not check_fixed(good,ap))
    v=Path.home()/'문서/GitHub/tech-reports/TR-2026-03/variants'
    if (v/'TR-03_변종목록_v1.json').exists():
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            ids,bad=e4_ladders(v/'TR-03_변종목록_v1.json',d,read_json(v/'ladders-sha256.json'));T.check(f'E4 변종 25종 재구성: TR-03 실행본 sha256 과 같음 {len(ids)-len(bad)}/{len(ids)}',len(ids)==25 and not bad)
    T.finish()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0]);ap.add_argument('mode',nargs='?',choices=['run','plan','fixed','settings-check']);ap.add_argument('--app',type=Path);ap.add_argument('--out',type=Path)
    ap.add_argument('--seed-table',type=Path);ap.add_argument('--seed-table-sha256');ap.add_argument('--fixed',type=Path);ap.add_argument('--fixed-sha256');ap.add_argument('--dev',action='store_true');ap.add_argument('--dev-batches')
    ap.add_argument('--stages',default='all');ap.add_argument('--only',help='개발: 셀:래더:시나리오 목록');ap.add_argument('--inject-nondeterminism',action='store_true',help='개발: 첫 M 쌍의 2회째에 Q 한 틱을 뒤집음')
    ap.add_argument('--e4-variants',type=Path);ap.add_argument('--e4-sha',type=Path);ap.add_argument('--seed',type=int,default=1);ap.add_argument('--selftest',action='store_true');ap.add_argument('--against',type=Path,help='selftest: 결함 판 round.py');a=ap.parse_args()
    if a.selftest:selftest(a.app,a.against)
    if a.mode in ('run','plan'):run_round(a)
    elif a.mode=='fixed':write_json(a.out,make_fixed(app_path(a.app),a.seed_table,a.e4_variants,a.e4_sha));print('[PASS] fixed',a.out,file_sha(a.out))
    elif a.mode=='settings-check':r=settings_check(a.app,a.seed);[print(x['status'],x['cell'],x['setting'],x.get('changed',''),x.get('error','')) for x in r];sys.exit(0 if all(x['status']=='[PASS]' for x in r) else 1)
    else:ap.error('mode 필요')
