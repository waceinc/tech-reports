"""TR-2026-05 (E2) held-Q 연결 실행 — plc-twin-lab a362610 bridge/run.py 의 사본을 E2 용으로 줄이고 고친 것.

바뀐 것(사본 README 「원본과 다른 점」): 셀 B 는 3i(표준 cell-b-sort, asm-pusher 1.5.0, 참조 = extctl logic.py SafeguardLogic,
3i 시나리오 = scenarios_3i.py fe605e1), 리눅스 앱, --physics fast|mujoco 를 CLI 로만 넘김(자식 환경의 VEXPLOR_EXTCTL_PHYSICS
삭제, stderr EXTCTL_PHYSICS mode=… source=cli 확인, M 이면 state.physics 있음 · F 이면 없음), 물리값 · 해시를 metadata.json 에 기록,
실행 범주(valid · plant_error · invalid), 벨트 배율 · M 물리값 · 초기 측면 위치를 넣은 셀 사본, 실행 시간. GUI · 포장 셀 · HMI · 녹화 경로는 뺐다.
v0.5 구현(I6 · I7): 앱 기본 경로 없음(--app 또는 TR05_APP), 틱 수는 시나리오 표(§3-5)로 고정하고 다르면 시작 거부 · 기록 불일치는 [INVALID],
시나리오별 판정(정답 curtain = 안전 판정, 정답 recovery = 복구 검사, 그 밖 = 공정 판정), 셀 B 장부 무관 판정, 첫 잠금 틱 · FaultCode,
참조 일치를 첫 잠금 전/뒤로 나눠 세고 §8 ② 예외 모양을 기계 판정(refcheck.py), M1 참조 논리 매개변수표(--reference-params).
제어에는 I 만 전달, state 는 기록 · 판정용. Python 은 Q 를 계산하지 않는다(controller=reference 는 참조 기록용).
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path
from transport import Child, Vision, ROOT, canon, receive, local_path
from scenarios_3i import recovery_stimuli, recovery_check, negative_judgments  # fe605e1 3i 판(fault_cell 은 cell_file 의 io_constants 로 대신)
from common import app_path, sha, file_sha, write_json, physics_parts, MissingField, field, Selftest
import refcheck
APP=None  # 기본 앱 경로 없음(§6-2). app_path() 가 --app · TR05_APP 만 받는다.
SCENARIOS={'cell-a':('normal','cycle-stop'),'cell-b':('normal','curtain','recovery','flow')}
# §3-5 시나리오별 틱 수. (셀, 래더 역할, 시나리오) → 틱. 셀 A 는 정답 · 음성 · E4 변종 모두 같은 표.
TICKS={('cell-a','*','normal'):1000,('cell-a','*','cycle-stop'):1200,('cell-b','correct','normal'):5000,('cell-b','correct','curtain'):1000,('cell-b','correct','recovery'):2800,
       ('cell-b','push-timing-off','normal'):1800,('cell-b','ignore-curtain','curtain'):500,('cell-b','no-sort-check','flow'):800}
Z_LIMIT=.125
def expected_ticks(cell,variant,scenario):return TICKS.get((cell,'*' if cell=='cell-a' else variant,scenario))
def plan_ticks(cell,variant,scenario,ticks=None,nonstandard=False):
    """§3-5: 틱 수는 표의 값. 다른 값은 --nonstandard-ticks(개발 · 게이트 전용, 공식 회차는 받지 않음)일 때만."""
    want=expected_ticks(cell,variant,scenario)
    if ticks is None:ticks=want
    if ticks is None:raise ValueError(f'[REFUSED] {cell} {variant} {scenario}: 시나리오 표(§3-5)에 없는 조합 — --ticks 와 --nonstandard-ticks 를 함께 준다')
    if ticks!=want and not nonstandard:raise ValueError(f'[REFUSED] --ticks {ticks} ≠ 시나리오 표 {want}({cell} {variant} {scenario}) — 개발용이면 --nonstandard-ticks')
    return ticks,want
def ticks_category(summary,cell,variant,scenario):
    """summary.json 의 ticks 가 표의 값이 아니면 [INVALID](비표준 표시가 있는 개발 실행은 'nonstandard')."""
    want=expected_ticks(cell,variant,scenario)
    if summary.get('ticks_rule')=='nonstandard':return 'nonstandard'
    return 'valid' if summary.get('category')=='valid' and summary.get('ticks')==want else 'invalid'
def source_tree(app):return Path(app).resolve().parents[2]
def reconstruct(previous,response):
    image=dict(previous);samples=[];edges=response['edges'];index=0;last=0
    duration=round(response.get('dt_s',.05)*1000)
    if duration not in (10,50):raise ValueError('factory tick must be 10/50 ms')
    if set(image)!=set(response['I']) or any(type(v) not in (bool,int) or type(v)!=type(image[k]) for k,v in response['I'].items()):raise ValueError('I schema')
    for edge in edges:
        ms=round(edge['t_s']*1000)
        if not (1<=ms<=duration and ms>=last and abs(edge['t_s']*1000-ms)<1e-8):raise ValueError('edge time')
        if edge['tag'] not in image or type(edge['value'])!=type(image[edge['tag']]):raise ValueError('edge tag/value')
        last=ms
    for boundary in range(10,duration+1,10):
        while index<len(edges) and round(edges[index]['t_s']*1000)<=boundary:
            e=edges[index]
            if image[e['tag']]==e['value']:raise ValueError('edge not a change')
            image[e['tag']]=e['value'];index+=1
        samples.append(dict(image))
    if image!=response['I']:raise ValueError('edges do not reconstruct final I')
    return samples

def reference(src,b,scale=1,params=None):
    # fe605e1 과 같음: extctl logic.py Logic(b) — B 는 SafeguardLogic(3i), A 는 ShuttleLogic(스캔 비교용은 시간 상수 ×5). M1 = 같은 코드 + 매개변수표.
    return refcheck.reference(src,b,scale,params)

def base_cell(src,cell_name):return src/'native/third_party/plc-devices/cells'/('cell-b-sort.plccell.json' if cell_name=='cell-b' else 'cell-a-shuttle.plccell.json')
def cell_file(src,cell_name,out,belt_factor=1.0,physics_values=None,io_constants=None,z_offset=0.0):
    """원본 셀(3i 표준)을 그대로 쓰거나, 벨트 배율 · M 물리값 · io-map 상수 · 초기 측면 위치가 있으면 실행 폴더에 사본을 만든다(원본 파일은 읽기만)."""
    base=base_cell(src,cell_name)
    if belt_factor==1.0 and not physics_values and not io_constants and not z_offset:return base
    definition=json.loads(base.read_text())
    if z_offset:  # §6-4 초기 측면 위치(셀 B 만 — 앱이 셀 A 부품 z 를 거부, 리드 결정): 모든 부품 인스턴스 transform.position[2] 에 더한다(앱 ac78d02 가 initial_z 로 읽음).
        if cell_name!='cell-b':raise ValueError('[REFUSED] 초기 측면 위치 설정은 셀 B 만(셀 A 는 모형 없음)')
        for i in definition['instances']:
            if i['module']=='obj-part':
                z=float(i['transform']['position'][2])+z_offset
                if abs(z)>Z_LIMIT+1e-12:raise ValueError(f'[REFUSED] {i["id"]} 초기 z {z} — |z| ≤ {Z_LIMIT} 밖')
                i['transform']['position'][2]=z
    target=out/'cell';target.mkdir();io_src=base.with_name(definition['wiring'])
    if io_constants:
        io=json.loads(io_src.read_text());io.setdefault('constants',{}).update(io_constants);io_src=target/io_src.name;io_src.write_text(json.dumps(io,ensure_ascii=False,indent=2))
    definition['wiring']=str(io_src)
    for inst in definition['instances']:
        if inst['module']=='conv-belt' and belt_factor!=1.0:inst['parameters']['speed_mps']=inst['parameters']['speed_mps']*belt_factor
    if physics_values:definition['physics']={'values':dict(physics_values)}  # 모드는 넣지 않는다(CLI 로만)
    path=target/base.name;path.write_text(json.dumps(definition,ensure_ascii=False,indent=2));return path

def metadata(src,app,program,cell,cell_name):
    tests=src/'native/third_party/plc-devices/tests'
    wiring=Path(json.loads(Path(cell).read_text())['wiring']);wiring=wiring if wiring.is_absolute() else Path(cell).parent/wiring
    files=[program,cell,wiring,src/'native/tests/external_control/logic.py',tests/'phase3c-control.json',ROOT/'experiments/S2/criteria-3i.md',ROOT/'cells/3i-parameters.json',ROOT/'cells'/f'{cell_name}.tagmap.json']
    try:commit=subprocess.check_output(['git','--no-optional-locks','-C',str(src),'rev-parse','HEAD'],text=True).strip();dirty=subprocess.check_output(['git','--no-optional-locks','-C',str(src),'status','--porcelain','--untracked-files=no'],text=True)!=''
    except Exception:commit,dirty=None,None
    node=subprocess.check_output(['node','--version'],text=True).strip()
    return dict(type='metadata',schema='tr05-run/3i',commits={'vexplor-vision-2':commit,'tracked_changes':dirty,'plc-simulator':'b415c25 (vendor copy, sha256 in SOURCES.json)'},files={str(f):file_sha(f) for f in files},
                app=str(app),exe_sha256=file_sha(app),node=node,plc_scan_ms=10,factory_tick_ms=10 if cell_name=='cell-b' else 50,physical_comparison=0,
                bridge_files={str(p.relative_to(ROOT)):file_sha(p) for p in sorted((ROOT/'bridge').glob('*')) if p.suffix in ('.py','.mjs')})

def correct_part(p):return p['route'] in (1,3) if p['class'] else p['route']==2
def verdict(cell,rows,probes,visits):
    all_events=[e for r in rows for e in r['events']];production=[e for e in all_events if e['name'] in ('PART_PACKED','REJECT_COLLECTED')]
    events=[e for e in all_events if e not in production and e['name'] not in ('PACK_PLACED','CONTAINER_EXCHANGED','PART_COLLECTED')];judgments=[e for r in rows for e in r.get('judgments',[])];parts=rows[-1]['state']['parts'];q=rows[-1]['Q_next']
    if cell=='cell-a':completed=visits==['right','left']*3 and probes.get('Rounds')==3 and not any(q.values())
    else:completed=len(parts)==20 and all(correct_part(p) for p in parts) and probes.get('Arrivals')==20
    return dict(status='[PASS]' if completed and not events and not judgments else '[FAIL]',completed=completed,event_count=len(events),events=events,production_events=production,judgment_count=len(judgments),judgments=judgments,visits=visits,routes={p['id']:p['route'] for p in parts},classification=[dict(id=p['id'],defective=bool(p['class']),route=p['route'],correct=correct_part(p)) for p in parts],probes=probes)

def ledger_free(state,result,out_x):
    """§3-5 장부 무관 판정(셀 B 공정 판정, 보고용): 양품이 route 2, 또는 route 0 이면서 x > out 센서 위치 ∧ on_floor 아님이면 맞음으로 친다.
    M 은 state.physics.parts[](I3)의 x · on_floor, F 는 state.parts 의 x(F 에는 바닥 낙하가 없어 on_floor = 거짓)."""
    try:pp=physics_parts(state) if 'physics' in state else None
    except MissingField as e:return dict(status='[NOT_AVAILABLE]',reason=str(e))
    rows=[];ok=True
    for p in state['parts']:
        good=(p['route'] in (1,3)) if p['class'] else p['route']==2;why=None
        if not p['class'] and p['route']==0:
            src=pp.get(p['id']) if pp is not None else p
            if src is None:return dict(status='[NOT_AVAILABLE]',reason=f'state.physics.parts 에 {p["id"]} 없음')
            x=field(src,'x');floor=bool(field(src,'on_floor')) if pp is not None else False
            good=x>out_x and not floor;why=dict(x=x,on_floor=floor)
        ok&=bool(good);rows.append(dict(id=p['id'],route=p['route'],correct=bool(good),**({'route0':why} if why else {})))
    completed=ok and len(state['parts'])==20 and result['probes'].get('Arrivals')==20
    return dict(status='[PASS]' if completed and not result['event_count'] and not result['judgment_count'] else '[FAIL]',completed=completed,out_x=out_x,source='state.physics.parts' if pp is not None else 'state.parts(F)',parts=rows)

def safety_verdict(rows):
    active=[r for r in rows if r['stimuli'].get('operator.present')]
    detected=next((r for r in active if r['I']['B.Safety.curtain']),None)
    if not detected:return dict(status='[FAIL]',reason='curtain never detected')
    before=rows[detected['tick']-2]
    stopped=next((r for r in rows[detected['tick']-1:] if abs(r['state']['belt_v'])<1e-9 and abs(r['state']['pusher_v'])<1e-9),None)
    lag=(stopped['tick']-detected['tick'])*.01 if stopped else None
    safe=all(not r['Q_next']['B.Conv.run'] and not r['Q_next']['B.Psh.sol'] for r in rows[detected['tick']-1:] if r['I']['B.Safety.curtain'])
    ok=before['Q']['B.Conv.run'] and safe and lag is not None and lag<=.265 and not any(r['events'] for r in rows)
    return dict(status='[PASS]' if ok else '[FAIL]',detected_tick=detected['tick'],stopped_tick=stopped['tick'] if stopped else None,stop_after_detection_s=lag,before_belt_v=before['state']['belt_v'],all_commands_off=safe)
def verdict_kind(variant,scenario):
    """§3-5 시나리오별 판정: 정답 curtain = 안전 판정, 정답 recovery = 복구 검사, 그 밖(ignore-curtain curtain 포함) = 공정 판정."""
    if variant=='correct' and scenario=='curtain':return 'safety'
    if variant=='correct' and scenario=='recovery':return 'recovery'
    return 'process'

def check_mode(out,physics,load_state):
    """§6-2: 모드는 CLI 로만. stderr 마지막 EXTCTL_PHYSICS 줄 = 기대 모드 · source=cli, M 이면 state.physics 있음, F 이면 없음."""
    lines=[l for l in (out/'vision-stderr.log').read_text(errors='replace').splitlines() if l.startswith('EXTCTL_PHYSICS ')]
    expected=f'EXTCTL_PHYSICS mode={physics} source=cli'
    ok=bool(lines) and lines[-1]==expected and (('physics' in load_state)==(physics=='mujoco'))
    return dict(status='[PASS]' if ok else '[FAIL]',stderr_line=lines[-1] if lines else None,expected=expected,state_physics=('physics' in load_state))

def run(cell_name,variant,out,app=APP,physics='fast',controller='ladder',ticks=None,seed=1,scenario='normal',defect_rate=.2,belt_factor=1.0,physics_values=None,keep_trace=True,
        initial_z_offset=0.0,program=None,reference_params=None,nonstandard_ticks=False,debug_perturb=None):
    """debug_perturb=(틱, Q 태그): 개발 시험 전용 — 그 틱에 보내는 Q 한 태그를 뒤집는다(비결정 쌍 시험). 공식 회차는 받지 않는다(round.py)."""
    if scenario not in SCENARIOS[cell_name]:raise ValueError(f'{cell_name} scenario {scenario} not in {SCENARIOS[cell_name]}')
    if physics not in ('fast','mujoco'):raise ValueError('physics fast|mujoco')
    app=app_path(app).resolve();ticks,want=plan_ticks(cell_name,variant,scenario,ticks,nonstandard_ticks)
    out=local_path(out);out.mkdir(parents=True,exist_ok=False);src=source_tree(app)
    b=cell_name=='cell-b';dt=.01 if b else .05
    cell=cell_file(src,cell_name,out,belt_factor,physics_values,{'pusher.flow_restriction':True} if scenario=='flow' else None,initial_z_offset)
    program=Path(program) if program else ROOT/'ladders'/cell_name/variant/'program.ldprog.json'
    meta=metadata(src,app,program,cell,cell_name);meta.update(controller=controller,scenario=scenario,seed=seed,defect_rate=defect_rate,ticks=ticks,ticks_table=want,physics_mode=physics,belt_factor=belt_factor,physics_values=physics_values or {},
        initial_z_offset=initial_z_offset,variant=variant,reference_params=reference_params,debug_perturb=debug_perturb,initial_Q='all false' if controller=='ladder' else 'original Logic.step(initial I)')
    write_json(out/'metadata.json',meta)
    engine=None;vision=None;rows=[];visits=[];scaled=reference(src,b,5,reference_params);original=reference(src,b,1,reference_params)
    meta['reference_logic']=dict(logic_sha256=scaled.tr05_logic_sha256,params_sha256=scaled.tr05_params_sha256,margin_amendment1=scaled.tr05_margin);write_json(out/'metadata.json',meta)
    same_input_diffs=[];probes={};trigger=None;result=None;started=time.monotonic();t_app=t_plc=0.0;category='invalid';error=None
    try:
        if controller=='ladder':
            engine=Child(['node',str(ROOT/'bridge/engine.mjs'),str(program)],out,'plc');static=receive(engine.process.stdout);assert static['ok'];write_json(out/'static.json',static)
            tagmap=json.loads((ROOT/'cells'/f'{cell_name}.tagmap.json').read_text());declared={x['symbol']:x['address'] for x in json.loads(program.read_text())['tags']}
            for x in tagmap['bindings']:assert declared[x['tag']]==x['address']==x['plc_address'],('tag map',x['tag'])
        vision=Vision(app,cell,out,physics=physics);meta['app_flags']=vision.args[6:]
        current=vision.send(dict(cmd='load',cell=str(cell),seed=seed,defect_rate=defect_rate));assert current['tick']==0 and current['dt_s']==dt
        mode=check_mode(out,physics,current['state']);meta['mode_check']=mode;meta['physics']=current['state'].get('physics');write_json(out/'metadata.json',meta)
        if mode['status']!='[PASS]':raise RuntimeError(f'mode check failed: {mode}')
        if initial_z_offset and any(abs(p['z']-initial_z_offset)>1e-9 for p in current['state']['parts']):raise RuntimeError(f'[REFUSED] 앱이 초기 측면 위치를 받지 않음(적재된 부품 z {sorted({p["z"] for p in current["state"]["parts"]})} ≠ {initial_z_offset}) — 앱이 셀의 부품 z 를 읽어야 한다')
        io=json.loads((ROOT/'cells'/f'{cell_name}.tagmap.json').read_text());q={x['tag']:False if x.get('type','BOOL')=='BOOL' else 0 for x in io['bindings'] if x['direction']=='out'}
        log=(out/'trace.jsonl').open('wb') if keep_trace else None
        try:
            if log:log.write(canon(meta)+b'\n')
            for tick in range(ticks):
                stimuli={'panel.pb0.press':tick==(30 if b else 6)}
                if b:stimuli['panel.pb3.press']=tick==5
                if scenario=='recovery':stimuli=recovery_stimuli(tick)
                if scenario=='cycle-stop':stimuli['panel.pb1.press']=tick==600
                if scenario=='curtain':
                    if trigger is None and q['B.Psh.sol']:trigger=tick
                    stimuli['operator.present']=trigger is not None
                if controller=='reference':q=original.step(current['I'])
                if debug_perturb and tick+1==debug_perturb[0]:q=dict(q,**{debug_perturb[1]:not q[debug_perturb[1]]})
                t0=time.perf_counter();response=vision.send(dict(cmd='step',Q=q,stimuli=stimuli));t_app+=time.perf_counter()-t0
                assert response['tick']==tick+1 and abs(response['time_s']-(tick+1)*dt)<1e-9
                images=reconstruct(current['I'],response)
                if engine:
                    t0=time.perf_counter();scans=engine.send(dict(cmd='scan',inputs=images,monitor=False))['scans'];t_plc+=time.perf_counter()-t0;qnext=scans[-1]['Q'];probes=scans[-1]['probes']
                    for scan,I in zip(scans,images):
                        expected=scaled.step(I)
                        if variant=='correct' and expected!=scan['Q']:same_input_diffs.append(dict(tick=tick+1,scan=scan['scan'],expected=expected,actual=scan['Q']))
                else:
                    scans=[];qnext=q;probes={'Rounds':getattr(original,'rounds',0),'Arrivals':original.arrivals}
                if not b:
                    wanted='right' if len(visits)%2==0 else 'left'
                    if len(visits)<6 and any(e['tag']==f'A.Sen.{wanted}' and e['value'] for e in response['edges']):visits.append(wanted)
                judgments=negative_judgments(cell_name,response['I'] if engine else current['I'],qnext,probes,tick+1)
                if b and response['I']['B.Safety.curtain'] and (qnext['B.Conv.run'] or qnext['B.Psh.sol']):judgments.append(dict(name='PLC_CURTAIN_IGNORED',tick=tick+1,rule='S2-3F-CURTAIN-Q',origin='bridge-verdict'))
                record=dict(type='tick',tick=tick+1,dt_s=dt,I_start=current['I'],I=response['I'],Q=q,Q_next=qnext,stimuli=response['stimuli'],edges=response['edges'],events=response['events'],judgments=judgments,state=response['state'],state_hash=sha(response['state']),scans=scans)
                record['hash']=sha(record)
                if log:log.write(canon(record)+b'\n')
                rows.append(record);current=response;q=qnext
            result=verdict(cell_name,rows,probes,visits);kind=verdict_kind(variant,scenario);result['verdict_kind']=kind
            if kind=='recovery':result['production_status']='[NOT_RUN]';result['recovery']=recovery_check(rows);result['status']=result['recovery']['status']
            if kind=='safety':result['production_status']='[NOT_RUN]';result['safety']=safety_verdict(rows);result['status']=result['safety']['status']
            if kind=='process' and b:result['ledger_free']=ledger_free(rows[-1]['state'],result,json.loads(base_cell(src,cell_name).read_text())['placement']['parameters']['out_x'])
            result['first_lock']=refcheck.first_lock(rows);result['end_fault_code']=probes.get('FaultCode')
            if variant=='correct' and engine:result['reference']=refcheck.split(same_input_diffs,rows)
            last=rows[-1]['state'].get('physics') or {}
            result.update(type='summary',category='valid',ticks=len(rows),ticks_table=want,ticks_rule='table' if ticks==want else 'nonstandard',scans=sum(len(r['scans']) for r in rows),trace_hash=sha([r['hash'] for r in rows]),tick_hashes=[r['hash'] for r in rows],
                          same_input_reference_differences=len(same_input_diffs),seed=seed,scenario=scenario,variant=variant,cell=cell_name,physics_mode=physics,belt_factor=belt_factor,initial_z_offset=initial_z_offset,physics_values=physics_values or {},
                          physics_report={k:last.get(k) for k in ('values_sha256','setup_sha256','run_max_tilt_rad','run_max_yaw_rad','tilt_flag','plate_track_max_m','rules','drops','parts','first_contact')} if last else None,
                          fast_first_contact=rows[-1]['state'].get('fast_first_contact'))
            if log:log.write(canon(result)+b'\n')
            category='valid' if len(rows)==ticks else 'invalid'
            if category=='invalid':error=f'ticks {len(rows)} ≠ {ticks}'
        finally:
            if log:log.close()
    except BaseException as e:
        error=str(e);category='plant_error' if 'MuJoCo warning' in error else 'invalid'
        write_json(out/'failure.json',dict(status='[PLANT_ERROR]' if category=='plant_error' else '[INVALID]',category=category,error=error,completed_ticks=len(rows)))
        if isinstance(e,KeyboardInterrupt):raise
    finally:
        cleanup_errors=[]
        for child,close in [(vision,lambda:vision.close(True)),(engine,lambda:engine.close())]:
            if child:
                try:close()
                except BaseException as e:cleanup_errors.append(str(e))
        exits=dict(vision_exit=vision.process.returncode if vision else None,plc_exit=engine.process.returncode if engine else None)
        write_json(out/'processes.json',dict(status='[PASS]' if not cleanup_errors and all(v in (None,0) for v in exits.values()) else '[FAIL]',**exits,run_finished=category=='valid',cleanup_errors=cleanup_errors))
    wall=time.monotonic()-started;timing=dict(wall_s=wall,app_step_s=t_app,ladder_scan_s=t_plc,ticks=len(rows),ms_per_tick=wall*1000/max(1,len(rows)))
    if category=='valid' and cleanup_errors:category='invalid';error='cleanup: '+'; '.join(cleanup_errors)
    if category!='valid':
        result=dict(type='summary',status='[PLANT_ERROR]' if category=='plant_error' else '[INVALID]',category=category,error=error,ticks=len(rows),ticks_table=want,seed=seed,scenario=scenario,variant=variant,cell=cell_name,physics_mode=physics)
    result['timing']=timing;write_json(out/'summary.json',result);write_json(out/'reference-10ms-differences.json',same_input_diffs)
    print(result['status'],result['category'],cell_name,variant,scenario,physics,'seed',seed,'belt',belt_factor,'ticks',len(rows),'ref-diffs',len(same_input_diffs),'hash',result.get('trace_hash'),f'{wall:.1f}s',flush=True)
    return result

def selftest(app=None,runs=None,out=None):
    from common import trace
    T=Selftest('run');env=os.environ.pop('TR05_APP',None)
    T.red_green('앱 경로 없이 시작하면 거부(기본 경로 없음)',lambda:app_path(None) is not None,lambda:app_path(__file__) is not None)
    if env:os.environ['TR05_APP']=env
    T.red_green('--ticks 가 시나리오 표와 다르면 시작 거부',lambda:plan_ticks('cell-b','correct','normal',4999),lambda:plan_ticks('cell-b','correct','normal')==(5000,5000))
    T.red_green('표에 없는 조합(정답 curtain 500)은 비표준 표시 없이는 거부',lambda:plan_ticks('cell-b','correct','curtain',500),lambda:plan_ticks('cell-b','correct','curtain',500,True)==(500,1000))
    s=dict(category='valid',ticks=4999,ticks_rule='table')
    T.red_green('summary 틱 수가 표와 다르면 [INVALID]',lambda:ticks_category(s,'cell-b','correct','normal')=='valid',lambda:ticks_category(dict(s,ticks=5000),'cell-b','correct','normal')=='valid')
    T.check('시나리오별 판정 종류(정답 curtain=안전, ignore-curtain curtain=공정, 정답 recovery=복구)',verdict_kind('correct','curtain')=='safety' and verdict_kind('ignore-curtain','curtain')=='process' and verdict_kind('correct','recovery')=='recovery' and verdict_kind('push-timing-off','normal')=='process')
    parts=[dict(id=f'part{i}',route=2,**{'class':0}) for i in range(1,21)];res=dict(probes=dict(Arrivals=20),event_count=0,judgment_count=0)
    def st(x,floor,route=0):
        p=[dict(q) for q in parts];p[17]['route']=route
        return dict(parts=p,physics=dict(parts=[dict(id=q['id'],x=x if q['id']=='part18' else 7.0,on_floor=floor if q['id']=='part18' else False) for q in p]))
    T.red_green('장부 무관: route 0 양품이 out 센서 앞이면 [FAIL], 지나가고 바닥 아님이면 [PASS]',lambda:ledger_free(st(1.0,False),res,2.2)['status']=='[PASS]',lambda:ledger_free(st(3.0,False),res,2.2)['status']=='[PASS]')
    T.red_green('장부 무관: 바닥에 떨어진 route 0 양품은 맞음이 아님',lambda:ledger_free(st(3.0,True),res,2.2)['status']=='[PASS]',lambda:ledger_free(st(3.0,False),res,2.2)['status']=='[PASS]')
    T.check('장부 무관: M 기록에 parts[] 가 없으면 [NOT_AVAILABLE] 와 이유',ledger_free(dict(parts=parts,physics={}),res,2.2)['status']=='[NOT_AVAILABLE]')
    if app:
        src=source_tree(app_path(app).resolve());import tempfile
        with tempfile.TemporaryDirectory() as d:
            T.red_green('초기 측면 위치 |z| > 0.125 거부 / +0.005 는 모든 부품 z 에 더함',lambda:cell_file(src,'cell-b',Path(d)/'a',z_offset=.2),
                        lambda:(Path(d,'b').mkdir() or True) and all(i['transform']['position'][2]==.005 for i in json.loads(cell_file(src,'cell-b',Path(d)/'b',z_offset=.005).read_text())['instances'] if i['module']=='obj-part'))
    if runs:
        runs=Path(runs)
        for s in (1,2,3):
            d=runs/f'gate-fast-1/cell-b-seed{s}/r1'
            if d.exists():rows=list(trace(d));T.check(f'F 게이트 시드 {s}: 첫 잠금 없음',refcheck.first_lock(rows) is None)
        d=runs/'dev-b-f-curtain1000'
        if d.exists():rows=list(trace(d));v=safety_verdict(rows);T.check(f'F 정답 curtain 1,000: 안전 판정 {v["status"]} 감지 {v.get("detected_tick")} 정지 {v.get("stopped_tick")}',v['status']=='[PASS]' and v['detected_tick']==237 and v['stopped_tick']==257)
    if app and out:  # 빠른 경로 회귀: 이 사본으로 돌린 F 기록 해시가 E2-3 기준(0edb740 빌드)과 같은가
        r=run('cell-a','correct',Path(out)/'cell-a-fast',app=app);T.check(f'F 셀 A normal 기록 해시 {r.get("trace_hash","")[:8]} = d753e4ab',r.get('trace_hash','').startswith('d753e4ab') and r['first_lock'] is None)
        r=run('cell-b','correct',Path(out)/'cell-b-fast',app=app);hs=[]
        for t in trace(Path(out)/'cell-b-fast'):  # --report-first-contact 가 더한 키만 빼고 다시 해시하면 E2-3 기준과 같아야 한다
            st=dict(t['state']);st.pop('fast_first_contact',None);t=dict(t,state=st,state_hash=sha(st));t.pop('hash');hs.append(sha(t))
        fc=r.get('fast_first_contact') or []
        T.check(f'F 셀 B 시드 1: fast_first_contact 를 뺀 기록 해시 {sha(hs)[:8]} = 9a55f6e4, 첫 이동 기록 {len(fc)}건, 예외 {r.get("reference",{}).get("exception",{}).get("tick")}',sha(hs).startswith('9a55f6e4') and len(fc)==5 and r['reference']['exception']['tick']==4461 and r['ledger_free']['status']=='[PASS]')
    T.finish()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--cell',choices=['cell-a','cell-b'],default='cell-a');p.add_argument('--variant',choices=['correct','swapped-sensors','late-reverse','push-timing-off','ignore-curtain','no-sort-check'],default='correct')
    p.add_argument('--output',type=Path);p.add_argument('--app',type=Path,help='앱 실행 파일(없으면 TR05_APP, 둘 다 없으면 거부)');p.add_argument('--physics',choices=['fast','mujoco'],default='fast')
    p.add_argument('--controller',choices=['ladder','reference'],default='ladder');p.add_argument('--ticks',type=int);p.add_argument('--nonstandard-ticks',action='store_true',help='시나리오 표와 다른 틱 수(개발 · 게이트 전용)');p.add_argument('--seed',type=int,default=1)
    p.add_argument('--scenario',choices=['normal','cycle-stop','curtain','recovery','flow'],default='normal');p.add_argument('--defect-rate',type=float,default=.2)
    p.add_argument('--belt-factor',type=float,default=1.0);p.add_argument('--physics-value',action='append',default=[],metavar='NAME=VALUE',help='M 전용 물리값(셀 JSON physics.values)')
    p.add_argument('--initial-z-offset',type=float,default=0.0,help='모든 부품 인스턴스 z 에 더함(|z| ≤ 0.125)');p.add_argument('--program',type=Path,help='래더 파일(기본 ladders/<셀>/<래더>/program.ldprog.json)')
    p.add_argument('--reference-params',type=Path,help='M1 참조 논리 매개변수표(refcheck.m1_reference_params 출력)');p.add_argument('--selftest',action='store_true');p.add_argument('--runs',type=Path,help='selftest: 개발 기록 폴더')
    a=p.parse_args()
    if a.selftest:selftest(a.app,a.runs,a.output)
    if not a.output:p.error('--output 필요')
    values={k:float(v) for k,v in (x.split('=',1) for x in a.physics_value)}
    try:r=run(a.cell,a.variant,a.output,a.app,a.physics,a.controller,a.ticks,a.seed,a.scenario,a.defect_rate,a.belt_factor,values or None,True,a.initial_z_offset,a.program,json.loads(a.reference_params.read_text()) if a.reference_params else None,a.nonstandard_ticks)
    except ValueError as e:sys.exit(str(e))
    sys.exit(0 if r['status']=='[PASS]' else 1)
