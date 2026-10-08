"""TR-2026-05 시드 표 생성기(구현 목록 I8, 사전 등록 §5-2 · §10 시드 표 · §8 [VALID]) — 새로 씀.

seed_k = SHA-256(UTF-8(접두 + str(k))) 의 첫 4바이트(빅 엔디언 uint32), k = 1 부터(앞자리 0 없는 10진). 시드 0 · 1 · 2 · 3 은 건너뜀.
앱 적재(load, 틱 0, 플랜트를 한 틱도 돌리지 않음)로 불량 개수를 세고, 불량 3 · 4 · 5 개 묶음마다 집합별 개수(공식 4 · 교정 2 · 개발 1)를 고른다.
불량 6개 이상 · 0~2개는 고르지 않는다. 앞 집합에 이미 있는 시드는 다음 k 로 넘어간다. k ≤ 1000 안에서 묶음을 못 채우면 표를 만들지 않고 멈춘다.
조사한 모든 k 의 (k, seed, 불량 개수)와 고른 시드의 부품 분류 · 셀 B values_sha256(기본 · 설정별)을 적는다. 표 바이트는 실행 시각 · 경로와 무관하다.

**공식 · 교정 시드는 동결(§14-6) 뒤에만 이 생성기로 만든다.** 동결 전 시험은 다른 접두(--prefix-set selftest)로만 한다.
    python3 bridge/seed_table.py build --app <앱> --out <seed-table.json> --prefix-set official   # 동결 뒤에만
    python3 bridge/seed_table.py --selftest [--app <앱>]
"""
import argparse, hashlib, json, sys, tempfile
from pathlib import Path
from common import ROOT, app_path, canon, file_sha, sha_bytes, Selftest
SEEN={0,1,2,3};BINS=(3,4,5);KMAX=1000
PREFIX_SETS={'official':[('official','TR-2026-05/official/',4),('calib','TR-2026-05/calib/',2),('dev','TR-2026-05/dev/',1)],
             'selftest':[('official','TR-2026-05/selftest-a/',1),('calib','TR-2026-05/selftest-b/',1),('dev','TR-2026-05/selftest-c/',1)]}
def seed_of(prefix,k):
    if not (isinstance(k,int) and k>=1):raise ValueError(k)
    return int.from_bytes(hashlib.sha256((prefix+str(k)).encode('utf-8')).digest()[:4],'big')

class Loader:
    """앱 한 프로세스에 load 만 보낸다(틱 0). 설정마다 셀 사본이 다르므로 설정마다 프로세스 하나."""
    def __init__(self,app,cell_name='cell-b',physics='fast',setting=None):
        from transport import Vision
        from run import cell_file, source_tree
        self.tmp=tempfile.TemporaryDirectory();out=Path(self.tmp.name);s=setting or {}
        self.cell=cell_file(source_tree(app),cell_name,out,s.get('belt_factor',1.0),s.get('physics_values'),None,s.get('initial_z_offset',0.0))
        self.vision=Vision(app,self.cell,out,physics=physics)
    def load(self,seed):
        r=self.vision.send(dict(cmd='load',cell=str(self.cell),seed=seed,defect_rate=.2))
        if r['tick']!=0:raise RuntimeError('load 가 틱 0 이 아님')
        parts=r['state']['parts'];ph=r['state'].get('physics') or {}
        return dict(defects=sum(1 for p in parts if p['class']),classes={p['id']:int(p['class']) for p in parts},values_sha256=ph.get('values_sha256'),setup_sha256=ph.get('setup_sha256'),
                    values={x['name']:x['value'] for x in ph.get('values',[])} if ph else None,z=[p['z'] for p in parts])
    def close(self):
        try:self.vision.close(True)
        finally:self.tmp.cleanup()

def build(app,prefix_set='official',settings=None,kmax=KMAX,bins=BINS):
    """settings: {이름: {physics_values|belt_factor|initial_z_offset}} — 고른 시드마다 M 적재로 values_sha256 을 잰다(기본은 이름 'default')."""
    app=app_path(app);plan=PREFIX_SETS[prefix_set];chosen=set();sets={};probed=[]
    fast=Loader(app,'cell-b','fast')
    try:
        for name,prefix,n in plan:
            picked={b:[] for b in bins};k=0
            while any(len(v)<n for v in picked.values()):
                k+=1
                if k>kmax:raise SystemExit(f'[STOP] {name}: k ≤ {kmax} 안에서 묶음을 채우지 못함 — 시드 표를 만들지 않는다(§5-2)')
                seed=seed_of(prefix,k);row=dict(set=name,k=k,seed=seed)
                if seed in SEEN:row['skip']='seed 0~3';probed.append(row);continue
                if seed in chosen:row['skip']='앞 집합과 겹침';probed.append(row);continue
                d=fast.load(seed);row['defects']=d['defects']
                if d['defects'] in picked and len(picked[d['defects']])<n:picked[d['defects']].append(dict(k=k,seed=seed,defects=d['defects'],classes=d['classes']));chosen.add(seed);row['chosen']=True
                probed.append(row)
            sets[name]={str(b):v for b,v in picked.items()}
    finally:fast.close()
    settings=dict(default={},**(settings or {}))
    hashes={}
    for sname,setting in settings.items():
        m=Loader(app,'cell-b','mujoco',setting)
        try:
            for name in sets:
                for b,items in sets[name].items():
                    for it in items:
                        d=m.load(it['seed']);hashes.setdefault(str(it['seed']),{})[sname]=dict(values_sha256=d['values_sha256'],setup_sha256=d['setup_sha256'])
                        if d['classes']!=it['classes']:raise RuntimeError(f'시드 {it["seed"]}: M 적재의 부품 분류가 F 와 다름')
        finally:m.close()
    return dict(schema='tr05-seed-table/1',rule='seed=SHA-256(UTF-8(prefix+str(k)))[0:4] big-endian; skip 0-3; load only (tick 0); defect bins 3/4/5; overlap -> next k; k<=1000',
                prefix_set=prefix_set,plan=[dict(set=a,prefix=b,per_bin=c) for a,b,c in plan],bins=list(bins),kmax=kmax,app_exe_sha256=file_sha(app),
                settings={k:v for k,v in settings.items()},sets=sets,values=hashes,probed=probed)
def next_seed(app,table,set_name,bin_,kmax=KMAX):
    """§6-1: 교정 시드의 F 연결 실행이 [PASS] 가 아니면 같은 묶음에서 그 집합 접두의 다음 k 로 넘어간다 — 표에 이미 조사한 k 다음부터 적재만으로 찾는다."""
    prefix=next(p for n,p,_ in PREFIX_SETS[table['prefix_set']] if n==set_name);used=set(table_seeds(table))|set(table.get('extra_seeds',[]))
    k=max([r['k'] for r in table['probed'] if r['set']==set_name]+table.get('extra_k',{}).get(set_name,[0]));L=Loader(app_path(app),'cell-b','fast')
    try:
        while k<kmax:
            k+=1;seed=seed_of(prefix,k)
            if seed in SEEN or seed in used:continue
            d=L.load(seed)
            if d['defects']==bin_:return dict(set=set_name,k=k,seed=seed,defects=d['defects'],classes=d['classes'])
    finally:L.close()
    raise SystemExit(f'[STOP] {set_name} 묶음 {bin_}: k ≤ {kmax} 안에 다음 시드 없음')
def dumps(table):return canon(table)+b'\n'
def table_seeds(table):
    """표의 시드 → (집합, 묶음)."""
    return {it['seed']:(name,int(b)) for name,bins in table['sets'].items() for b,items in bins.items() for it in items}

def accept_seed(seed,dev=False,table_path=None,expect_sha=None,want_set=None):
    """§5-2 실행기의 시드 수용: 시드 0~3 은 그대로. 그 밖은 (가) --dev-seed 표시 — 단 주어진 시드 표의 공식 · 교정 시드면 거부,
    또는 (나) 회차 실행기가 sha256 이 고정값과 같은 시드 표에서 읽은 시드. 표에 없는 시드는 거부."""
    table=None
    if table_path:
        raw=Path(table_path).read_bytes();digest=sha_bytes(raw)
        if expect_sha and digest!=expect_sha:raise SystemExit(f'[REFUSED] 시드 표 sha256 {digest[:12]}… ≠ 고정값 {expect_sha[:12]}…')
        table=json.loads(raw)
    if seed in SEEN:return 'seen'
    found=table_seeds(table).get(seed) if table else None
    if dev:
        if found and found[0] in ('official','calib'):raise SystemExit(f'[REFUSED] 시드 {seed} 는 시드 표의 {found[0]} 시드 — --dev-seed 로 줄 수 없다')
        return 'dev'
    if not table:raise SystemExit(f'[REFUSED] 시드 {seed}: 시드 0~3 밖 — --dev-seed 표시 또는 고정 시드 표가 필요')
    if not expect_sha:raise SystemExit('[REFUSED] 시드 표의 고정 sha256 이 주어지지 않음')
    if not found:raise SystemExit(f'[REFUSED] 시드 {seed} 는 시드 표에 없다')
    if want_set and found[0]!=want_set:raise SystemExit(f'[REFUSED] 시드 {seed} 는 {found[0]} 시드(요청 {want_set})')
    return found[0]

def selftest(app=None):
    T=Selftest('seed_table');p='TR-2026-05/selftest-a/'
    ref=int.from_bytes(hashlib.sha256(b'TR-2026-05/selftest-a/1').digest()[:4],'big')
    T.red_green('시드 식: 첫 4바이트 빅 엔디언(리틀 엔디언이면 다름)',lambda:int.from_bytes(hashlib.sha256(b'TR-2026-05/selftest-a/1').digest()[:4],'little')==ref,lambda:seed_of(p,1)==ref)
    T.red_green('k 는 앞자리 0 없는 10진(01 은 다른 시드)',lambda:seed_of(p,1)==int.from_bytes(hashlib.sha256(b'TR-2026-05/selftest-a/01').digest()[:4],'big'),lambda:seed_of(p,10)==int.from_bytes(hashlib.sha256(b'TR-2026-05/selftest-a/10').digest()[:4],'big'))
    tab=dict(sets=dict(official={'3':[dict(seed=111)]},calib={'4':[dict(seed=222)]},dev={'5':[dict(seed=333)]}))
    with tempfile.TemporaryDirectory() as d:
        f=Path(d)/'t.json';f.write_bytes(dumps(tab));good=sha_bytes(f.read_bytes())
        def refused(fn):
            try:fn();return False
            except SystemExit:return True
        T.red_green('공식 시드를 --dev-seed 로 주면 거부',lambda:not refused(lambda:accept_seed(111,True,f)),lambda:refused(lambda:accept_seed(111,True,f)) and accept_seed(333,True,f)=='dev')
        T.red_green('표에 없는 시드 거부(고정 sha256 일치 표)',lambda:not refused(lambda:accept_seed(999,False,f,good)),lambda:refused(lambda:accept_seed(999,False,f,good)) and accept_seed(111,False,f,good)=='official')
        T.red_green('표 sha256 이 고정값과 다르면 거부',lambda:not refused(lambda:accept_seed(111,False,f,'0'*64)),lambda:refused(lambda:accept_seed(111,False,f,'0'*64)))
        T.check('표 없이 시드 0~3 밖은 --dev-seed 없으면 거부',refused(lambda:accept_seed(12345,False)) and accept_seed(2,False)=='seen')
    if app:
        st=dict(friction_07=dict(physics_values=dict(friction_scale=.7)),belt_095=dict(belt_factor=.95))
        a=build(app,'selftest',st,kmax=200);b=build(app,'selftest',st,kmax=200)
        T.check(f'같은 입력으로 두 번 만든 표가 바이트 같음(sha256 {sha_bytes(dumps(a))[:12]}, 조사한 k {len(a["probed"])})',dumps(a)==dumps(b))
        L=Loader(app_path(app),'cell-b','fast')
        try:
            items=[it for bins in a['sets'].values() for v in bins.values() for it in v]
            bad=dict(items[0],defects=items[0]['defects']+1)
            T.red_green('앱 적재 불량 개수 = 표의 개수(고친 표는 어긋남)',lambda:L.load(bad['seed'])['defects']==bad['defects'],lambda:all(L.load(it['seed'])['defects']==it['defects'] for it in items))
        finally:L.close()
        v=a['values'][str(items[0]['seed'])]
        T.check('설정별 values_sha256: 벨트는 values 만 바꾸고 setup 은 같음, 마찰은 둘 다 바꿈',v['belt_095']['setup_sha256']==v['default']['setup_sha256'] and v['belt_095']['values_sha256']!=v['default']['values_sha256'] and v['friction_07']['setup_sha256']!=v['default']['setup_sha256'])
        nx=next_seed(app,a,'calib',items[1]['defects'])
        T.check(f'건너뛴 교정 시드의 대체: 같은 묶음 다음 k={nx["k"]}(표의 k 다음, 겹침 없음)',nx['defects']==items[1]['defects'] and nx['seed'] not in table_seeds(a) and nx['k']>max(r['k'] for r in a['probed'] if r['set']=='calib'))
        T.check('시드 0~3 · 겹침은 고르지 않음',all(it['seed'] not in SEEN for it in items) and len({it['seed'] for it in items})==len(items))
    T.finish()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0]);ap.add_argument('mode',nargs='?',choices=['build']);ap.add_argument('--app',type=Path);ap.add_argument('--out',type=Path)
    ap.add_argument('--prefix-set',choices=list(PREFIX_SETS),default='selftest');ap.add_argument('--settings',type=Path,help='설정 표 JSON(round.py settings)');ap.add_argument('--frozen-commit',help='공식 · 교정 시드: 동결(예측 · 분석) 커밋 해시(40자). 없으면 거부');ap.add_argument('--selftest',action='store_true');a=ap.parse_args()
    if a.selftest:selftest(a.app)
    if a.mode!='build' or not a.out:ap.error('build --out 필요')
    if a.out.exists():sys.exit(f'[REFUSED] {a.out} 가 이미 있다')
    if a.prefix_set=='official' and not (a.frozen_commit and len(a.frozen_commit)==40 and all(c in '0123456789abcdef' for c in a.frozen_commit)):sys.exit('[REFUSED] 공식 · 교정 시드는 동결 뒤에만 — --frozen-commit <40자 동결 커밋> 이 필요(§14-6)')
    t=build(a.app,a.prefix_set,json.loads(a.settings.read_text()) if a.settings else None);t['frozen_commit']=a.frozen_commit;a.out.write_bytes(dumps(t));print('[PASS] seed table',a.out,sha_bytes(dumps(t)))
