"""TR-2026-05 실행기 · 분석 공용 도구(새로 씀): 해시, 기록 읽기, 앱 경로, 자기 시험(빨강 → 초록) 틀, 앱 보고 필드 읽기.

앱 보고 필드(state.physics.parts[] · first_contact[], 구현 목록 I3 · I4)는 이름이 확정되기 전에 쓴 읽기 함수다. 필드가 없으면
MissingField 로 멈추고 무엇이 없는지 적는다(조용히 0 으로 채우지 않는다).
"""
import hashlib, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(v):return hashlib.sha256(canon(v)).hexdigest()
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def file_sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_json(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def read_json(path):return json.loads(Path(path).read_text())

def app_path(arg=None):
    """§6-2: 앱 경로는 --app 또는 TR05_APP 으로만. 기본 경로는 없다(공개본과 등록 해시가 같은 바이트)."""
    value=arg or os.environ.get('TR05_APP')
    if not value:raise SystemExit('[REFUSED] 앱 경로가 없다 — --app <실행 파일> 또는 환경 변수 TR05_APP 를 준다(기본 경로 없음, 사전 등록 §6-2)')
    p=Path(value)
    if not p.is_file():raise SystemExit(f'[REFUSED] 앱 실행 파일이 없다: {p}')
    return p

def trace(run_dir,kinds=('tick',)):
    """실행 폴더의 trace.jsonl 을 줄마다 읽는다(첫 줄 metadata, 끝 줄 summary)."""
    with (Path(run_dir)/'trace.jsonl').open() as f:
        for line in f:
            r=json.loads(line)
            if kinds is None or r.get('type') in kinds:yield r

class MissingField(RuntimeError):
    """앱 보고 필드가 없음 — 공식 빌드(I3 · I4)가 아니거나 필드 이름이 다르다."""

# I3 · I4 필드 이름. 앱 상태 파일(e2_status_4, 2026-10-08)이 확정한 이름을 맨 앞에 두고, 나머지는 예전 후보(읽기 호환).
# parts[]: {id, route, body, position[x,y,z], quaternion[w,x,y,z], velocity[3], yaw_rad, tilt_rad, slope_angle_rad, slope_velocity_mps, support, support_gap_m, stacked, on_floor}
# first_contact[] · fast_first_contact: {part: k(1부터 정수), tick, ms, t_s, x(분류 위치 = x 0)}
PART_KEYS=dict(id=('id','part_id','part'),x=('position.0','x','pos.0'),y=('position.1','y','pos.1'),z=('position.2','z','pos.2'),
               v_slope=('slope_velocity_mps','v_slope_mps','v_slope'),support_gap_m=('support_gap_m',),stacked=('stacked',),on_floor=('on_floor',),route=('route',),
               quat=('quaternion','quat'),yaw=('yaw_rad',),support=('support',))
CONTACT_KEYS=dict(id=('part','id','part_id'),tick=('tick',),sample=('ms','sample_ms'),x=('x','x_m'))
def _get(entry,names):
    for n in names:
        cur=entry
        try:
            for k in n.split('.'):cur=cur[int(k)] if k.isdigit() else cur[k]
            return cur
        except (KeyError,IndexError,TypeError):continue
    raise KeyError(names)
def field(entry,name,table=PART_KEYS,where=''):
    try:return _get(entry,table[name])
    except KeyError:raise MissingField(f'{where} 항목에 {name} 필드가 없다(찾은 이름 {table[name]}, 있는 키 {sorted(entry) if isinstance(entry,dict) else type(entry).__name__})')
def physics_parts(state,where='state.physics.parts'):
    """M 의 부품별 보고(I3). 없으면 MissingField."""
    ph=state.get('physics')
    if ph is None:raise MissingField(f'{where}: state.physics 가 없다(F 실행이거나 적재 전)')
    if 'parts' not in ph:raise MissingField(f'{where}: state.physics.parts 가 없다 — 앱 I3(parts[]) 이 들어간 빌드가 아니다')
    return {str(field(p,'id',where=where)):p for p in ph['parts']}
def first_contacts(state,fast=False):
    """I4: M 은 state.physics.first_contact[], F 는 최상위 fast_first_contact. 부품 id → 항목."""
    if fast:
        if 'fast_first_contact' not in state:raise MissingField('state.fast_first_contact 가 없다 — 앱 I4(F 첫 이동 기록)가 들어간 빌드가 아니다')
        items=state['fast_first_contact']
    else:
        ph=state.get('physics') or {}
        if 'first_contact' not in ph:raise MissingField('state.physics.first_contact 가 없다 — 앱 I4 가 들어간 빌드가 아니다')
        items=ph['first_contact']
    def pid(c):
        k=field(c,'id',CONTACT_KEYS,'first_contact');return f'part{k}' if isinstance(k,int) else str(k)  # 앱은 부품 번호 k(1부터)를 낸다
    return {pid(c):c for c in items}

class Selftest:
    """자기 시험: 각 검사는 먼저 일부러 깨뜨린 입력에서 빨강([FAIL])이 나와야 하고, 그 다음 정상 입력에서 초록([PASS])이어야 한다."""
    def __init__(self,name):self.name=name;self.results=[]
    def red_green(self,label,broken,good):
        """broken() · good() 는 '검사가 통과했는가'를 bool 로 돌려준다. 예외도 빨강으로 친다."""
        def call(f):
            try:return bool(f()),None
            except KeyboardInterrupt:raise
            except BaseException as e:return False,f'{type(e).__name__}: {e}'
        r,er=call(broken);g,eg=call(good)
        print(f"  {'[FAIL]' if not r else '[PASS?]'} 깨뜨린 입력 — {label}"+(f' ({er})' if er else ''),flush=True)
        print(f"  {'[PASS]' if g else '[FAIL]'} 정상 입력 — {label}"+(f' ({eg})' if eg else ''),flush=True)
        self.results.append(dict(check=label,red_shown=not r,green=g,ok=(not r) and g));return (not r) and g
    def check(self,label,ok):
        print(f"  {'[PASS]' if ok else '[FAIL]'} {label}",flush=True);self.results.append(dict(check=label,red_shown=None,green=bool(ok),ok=bool(ok)));return ok
    def finish(self):
        ok=all(r['ok'] for r in self.results)
        print(f"{'[PASS]' if ok else '[FAIL]'} selftest {self.name}: {sum(r['ok'] for r in self.results)}/{len(self.results)}",flush=True)
        sys.exit(0 if ok else 1)
