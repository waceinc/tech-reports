"""S2 held-Q 연결 실행(S2-5 부터 셀 B·포장은 3k). 제어에는 I만 전달, state는 기록/판정/화면용."""
import argparse, hashlib, importlib.util, json, os, subprocess, sys, time
from pathlib import Path
from transport import Child, Vision, ROOT, canon, receive, local_path
EXTCTL=Path('<repos>/vexplor-vision-2-extctl')
# 녹화용 프레임: S2_RECORD_EVERY=N 이면 GUI 실행에서 N 틱마다 두 창을 캡처(시간을 진행하지 않는 read·capture — 판정·해시에 영향 없음)
RECORD_EVERY=int(os.environ.get('S2_RECORD_EVERY','0'))
# 포장 셀 로봇: S2_ROBOT_ID=abb-irb4600 등(미지정이면 extctl 기본 staubli-tx90). 공개물은 ABB 만(라이선스)
ROBOT_ID=os.environ.get('S2_ROBOT_ID')
def sha(x):return hashlib.sha256(canon(x)).hexdigest()
def file_sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
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

def wrap32(x):
    x=int(x)&0xffffffff
    return x-0x100000000 if x&0x80000000 else x

def reference(extctl,b,scale=1,count_start=None):
    if b:
        import types
        src=extctl/'native/third_party/plc-devices/tests';sys.path.insert(0,str(src))
        # 공급 시험 실행기의 부수효과 없이 정답 클래스 정의만 읽는다.
        if 'run_phase3g_cells' not in sys.modules:
            module=types.ModuleType('run_phase3g_cells')
            module.__dict__.update(DT=.01,DEFINITION=src.parent/'library/asm-pusher/versions/1.5.0/device.json',read=lambda path:json.loads(path.read_text()))
            code=(src/'run_phase3g_cells.py').read_text()
            exec(compile(code[code.index('class FlyingLogic:'):code.index('\ndef run(')],str(src/'run_phase3g_cells.py'),'exec'),module.__dict__)
            sys.modules[module.__name__]=module
        from phase3k_logic import SortLogic3k
        pos,scan=count_start or (0,0)
        return SortLogic3k(count_start_position=wrap32(pos),count_start_scan=wrap32(scan))
    src=extctl/'native/tests/external_control/logic.py'
    spec=importlib.util.spec_from_file_location('s2_reference',src);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    obj=mod.Logic(b)
    if not b:obj.cfg={k:v*scale for k,v in obj.cfg.items()}
    return obj

def metadata(extctl,program,cell):
    commits={name:subprocess.check_output(['git','--no-optional-locks','-C',str(path),'rev-parse','HEAD'],text=True).strip() for name,path in [('plc-simulator',ROOT/'vendor/plc-simulator'),('vexplor-vision-2',ROOT/'vendor/vexplor-vision-2'),('vision-2-extctl',extctl)]}
    tests=extctl/'native/third_party/plc-devices/tests'
    files=[program,cell,extctl/'native/tests/external_control/logic.py',tests/'phase3c-control.json',tests/'phase3k_logic.py',tests/'phase3k_pack_logic.py',tests/'phase3j_logic.py',tests/'phase3j_pack_logic.py',ROOT/'experiments/S2/criteria-3k.md',ROOT/'cells/3k-hmi.json']
    return dict(type='metadata',schema='s2-run/3k',commits=commits,files={str(f):file_sha(f) for f in files},plc_scan_ms=10,factory_tick_ms=10 if 'cell-b' in cell.name else 50,physical_comparison=0)

def verdict(cell,rows,probes,visits):
    all_events=[e for r in rows for e in r['events']];production=[e for e in all_events if e['name'] in ('PART_PACKED','REJECT_COLLECTED')]
    events=[e for e in all_events if e not in production and e['name'] not in ('PACK_PLACED','CONTAINER_EXCHANGED','PART_COLLECTED')];judgments=[e for r in rows for e in r.get('judgments',[])];parts=rows[-1]['state']['parts'];q=rows[-1]['Q_next']
    def correct(p):return p['route'] in ((6,) if cell=='cell-b-pack' else (1,3)) if p['class'] else p['route']==(5 if cell=='cell-b-pack' else 2)
    if cell=='cell-a':completed=visits==['right','left']*3 and probes.get('Rounds')==3 and not any(q.values())
    elif cell=='cell-b-pack':
        packed=rows[-1]['state']['pack']['parts'];completed=len(packed)==60 and all(p['stage']==(4 if p['reason'] else 2) for p in packed) and len({(e['name'],e['part_id']) for e in production})==60 and probes.get('Arrivals')==60
    else:completed=len(parts)==20 and all(correct(p) for p in parts) and probes.get('Arrivals')==20
    return dict(status='[PASS]' if completed and not events and not judgments else '[FAIL]',completed=completed,event_count=len(events),events=events,production_events=production,judgment_count=len(judgments),judgments=judgments,visits=visits,routes={p['id']:p['route'] for p in parts},classification=[dict(id=p['id'],defective=bool(p['class']),route=p['route'],correct=correct(p)) for p in parts],probes=probes)

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

STROKE_FLOW=.75
PACK_FAULTS=[(2000,'P.R0.drive_failure'),(4000,'P.C1.failure')]
def word_stimuli(tick,q,edge_period=20):
    """strokeclear 운전원: 화면 워드(D641 복귀 단계·D642 운전 상태)만 보고 누른다. 공정 출력은 만들지 않는다."""
    edge=tick%edge_period<3;step=q.get('B.HMI.recoveryStep',0);state=q.get('B.HMI.runState',0);s={}
    if state in (4,5):
        s.update({'panel.pb3.press':step==1 and edge,'recovery.quarantine':step==2 and edge,'recovery.home':step in (3,4),'panel.pb0.press':step==5 and edge,'recovery.clear':step==7 and edge})
    elif tick>100:s['panel.pb0.press']=state==0 and edge
    return s

def run(cell_name,variant,out,extctl=EXTCTL,gui=False,controller='ladder',ticks=None,seed=1,scenario='normal',defect_rate=.2,no_ladder=False,sync_qa=False,monitor_from_tick=0,flow_factor=None,count_start=None):
    if flow_factor is not None and (type(flow_factor) not in (float,int) or not 0<=flow_factor<=1 or not scenario.startswith('flow')):
        raise ValueError('flow_factor requires flow scenario and finite numeric 0..1')
    out=local_path(out);out.mkdir(parents=True,exist_ok=False)
    b=cell_name!='cell-a';pack=cell_name=='cell-b-pack';fullname='cell-b-pack' if pack else 'cell-b-sort' if b else 'cell-a-shuttle';dt=.01 if b else .05
    ticks=ticks or (10000 if pack else 5000 if b else 1000)
    if scenario=='hmi' and (not gui or not b or controller!='ladder'):raise ValueError('hmi requires GUI cell-b ladder')
    cell=extctl/'native/third_party/plc-devices/cells'/('phase3k/'+fullname+'.plccell.json' if b else fullname+'.plccell.json')
    if count_start is not None and (not b or pack or controller!='ladder'):raise ValueError('count_start requires cell-b ladder')
    program=ROOT/'ladders'/cell_name/variant/'program.ldprog.json'
    exe=extctl/'native/build-extctl/vexplor_studio_native.app/Contents/MacOS/vexplor_studio_native'
    if scenario.startswith('flow'):
        from scenarios_3j import fault_cell
        cell=fault_cell(cell,out)
    meta=metadata(extctl,program,cell);meta.update(controller=controller,gui=gui,scenario=scenario,seed=seed,defect_rate=defect_rate,exe_sha256=file_sha(exe),initial_Q='all false' if controller=='ladder' else 'original Logic.step(initial I)',bridge_files={str(p.relative_to(ROOT)):file_sha(p) for p in sorted((ROOT/'bridge').glob('*')) if p.suffix in ('.py','.mjs','.sh')})
    meta['monitor_from_tick']=monitor_from_tick;meta['count_start']=dict(position_udint=count_start[0]&0xffffffff,position_dint=wrap32(count_start[0]),scan_dint=wrap32(count_start[1])) if count_start else None
    # 수치 고장용 사본 이름(flow.plccell.json)으로 공장 주기를 추론하지 않는다.
    meta['factory_tick_ms']=round(dt*1000)
    if scenario.startswith('flow'):
        meta['flow_factor']=flow_factor if flow_factor is not None else (.5 if scenario=='flow50' else .7)
    if scenario in ('stroke75','strokeclear'):meta['flow_factor']=STROKE_FLOW
    write_json(out/'metadata.json',meta)
    engine=None;vision=None;monitor=None;rows=[];visits=[];captures=[];scaled=reference(extctl,b,5,count_start);original=reference(extctl,b,1,count_start);word_seq={};seen_words={};flow_now=None

    if pack:
        for ref in (scaled,original):ref.q['part_count']=60
        sys.path.insert(0,str(extctl/'native/third_party/plc-devices/tests'));from phase3k_pack_logic import PackLogic3k;pack_scaled=PackLogic3k();pack_original=PackLogic3k()
    same_input_diffs=[];probes={};success=False;trigger=None;hmi_records=[]
    actions={5:'reset',30:'start',600:'stop',1100:'start',1600:'estop',1700:'twist',1750:'reset',1800:'start',2100:'curtain',2250:'curtain',2400:'reset',2500:'start'}
    try:
        if controller=='ladder':
            engine=Child(['node',str(ROOT/'bridge/engine.mjs'),str(program)],out,'plc');static=receive(engine.process.stdout);assert static['ok'];write_json(out/'static.json',static)
            tagmap=json.loads((ROOT/'cells'/f'{cell_name}.tagmap.json').read_text());declared={x['symbol']:x['address'] for x in json.loads(program.read_text())['tags']}
            for x in tagmap['bindings']:assert declared[x['tag']]==x['address']==x['plc_address']
            if count_start is not None:write_json(out/'count-start.json',engine.send(dict(cmd='write',values={'D_누적이동펄스':count_start[0]&0xffffffff,'D_누적스캔':wrap32(count_start[1])})))
        vision=Vision(exe,cell,out,gui,scenario=='hmi' or (gui and not no_ladder and controller=='ladder'))
        current=vision.send(dict(cmd='load',cell=str(cell),seed=seed,defect_rate=defect_rate,**({'robot_id':ROBOT_ID} if ROBOT_ID and pack else {})));assert current['tick']==0 and current['dt_s']==dt
        if scenario.startswith('flow') or scenario in ('stroke75','strokeclear'):
            constant_response=vision.send(dict(cmd='set_constants',values={'pusher.flow_factor':meta['flow_factor']}));flow_now=meta['flow_factor']
            write_json(out/'constants.json',constant_response)
            assert constant_response['constants']['pusher.flow_factor']==meta['flow_factor']
        io=json.loads((ROOT/'cells'/f'{cell_name}.tagmap.json').read_text());q={x['tag']:False if x.get('type','BOOL')=='BOOL' else 0 for x in io['bindings'] if x['direction']=='out'}
        if gui and controller=='ladder' and not no_ladder and monitor_from_tick==0:
            from monitor import Monitor
            monitor=Monitor(engine,vision,out,cell_name,tagmap)
        with (out/'trace.jsonl').open('wb') as log:
            log.write(canon(meta)+b'\n')
            for tick in range(ticks):
                if gui and controller=='ladder' and not no_ladder and monitor is None and tick==monitor_from_tick:
                    from monitor import Monitor
                    monitor=Monitor(engine,vision,out,cell_name,tagmap)
                stimuli={'panel.pb0.press':tick==(30 if b else 6)}
                if b:stimuli['panel.pb3.press']=tick==5
                if scenario.startswith('recovery'):
                    from scenarios_3j import recovery_stimuli
                    stimuli=recovery_stimuli(tick,scenario)
                if scenario=='strokeclear':
                    stimuli.update(word_stimuli(tick,q))
                    if flow_now is not None and q.get('B.HMI.runState')==0 and q.get('B.HMI.recoveryStep')==8:
                        vision.send(dict(cmd='set_constants',values={'pusher.flow_factor':None}));flow_now=None;meta.setdefault('constant_changes',[]).append(dict(tick=tick,flow_factor=None))
                if scenario=='packfault':
                    for at,key in PACK_FAULTS:
                        if tick==at:vision.send(dict(cmd='set_constants',values={key:True}))
                        if tick==at+60:vision.send(dict(cmd='set_constants',values={key:None}))
                        if at+120<=tick<at+125:stimuli['panel.pb3.press']=True
                if scenario=='cycle-stop':stimuli['panel.pb1.press']=tick==600
                if scenario=='batch':stimuli['batch.ack']=tick==2400
                if pack and scenario in ('normal','packfault') and tick>1000 and tick%50==0:stimuli['panel.pb0.press']=True
                if scenario=='curtain':
                    if trigger is None and q['B.Psh.sol']:trigger=tick
                    stimuli['operator.present']=trigger is not None
                if scenario=='hmi':
                    stimuli={name:False for name in ('panel.pb0.press','panel.pb1.press','panel.pb2.press','panel.pb2.twist','panel.pb3.press','operator.present')}
                    if tick in actions:
                        h=vision.send(dict(cmd='hmi',action='click',target=actions[tick],held=tick==30));hmi_records.append(dict(tick_before=tick,action=actions[tick],response=h))
                if scenario=='hmi' and tick==33:vision.send(dict(cmd='hmi',action='release',target='start'))
                if controller=='reference':
                    q=original.step(current['I'])
                    if pack:q.update(pack_original.step(current['I']))
                response=vision.send(dict(cmd='step',Q=q,stimuli=stimuli))
                assert response['tick']==tick+1 and abs(response['time_s']-(tick+1)*dt)<1e-9
                images=reconstruct(current['I'],response)
                if engine:
                    scans=engine.send(dict(cmd='scan',inputs=images,monitor=monitor is not None))['scans'];qnext=scans[-1]['Q'];probes=scans[-1]['probes']
                    if count_start is not None and tick==0:
                        # 시작값 반영 확인: 첫 스캔 끝 누적 스캔 = 시작+1, 누적 위치 = 시작(첫 스캔은 고속계수 차분 없음)
                        assert probes['Scan']==wrap32(count_start[1]+1) and probes['Position']==count_start[0]&0xffffffff,('count_start',probes)
                    for scan,I in zip(scans,images):
                        expected=scaled.step(I)
                        if pack:expected.update(pack_scaled.step(I))
                        for tag,value in scan['Q'].items():
                            if '.HMI.' in tag or tag=='B.Lamp.strokeWarn':
                                seq=word_seq.setdefault(tag,[])
                                if not seq or seq[-1]!=value:seq.append(value)
                                seen_words.setdefault(tag,{}).setdefault(str(value),0);seen_words[tag][str(value)]+=1
                        if variant=='correct' and expected!=scan['Q']:same_input_diffs.append(dict(tick=tick+1,scan=scan['scan'],expected=expected,actual=scan['Q']))
                else:
                    scans=[];qnext=q;probes={'Rounds':getattr(original,'rounds',0),'Arrivals':original.arrivals}
                if not b:
                    wanted='right' if len(visits)%2==0 else 'left'
                    if len(visits)<6 and any(e['tag']==f'A.Sen.{wanted}' and e['value'] for e in response['edges']):visits.append(wanted)
                from scenarios_3j import negative_judgments
                # Reference Q is computed before the physical tick, from current I.
                judgments=negative_judgments(cell_name,response['I'] if engine else current['I'],qnext,probes,tick+1)
                if b and response['I']['B.Safety.curtain'] and (qnext['B.Conv.run'] or qnext['B.Psh.sol']):judgments.append(dict(name='PLC_CURTAIN_IGNORED',tick=tick+1,rule='S2-3F-CURTAIN-Q',origin='bridge-verdict'))
                if monitor:monitor.publish(response,scans)
                if sync_qa and tick==80:
                    if monitor:monitor.check_focus()
                    picked=vision.send(dict(cmd='hmi',action='pick',index=0));write_json(out/'3d-pick.json',picked)
                if sync_qa and tick==81 and monitor:monitor.check_selection()
                if sync_qa and scenario=='hmi' and monitor and tick==1599:monitor.check_follow('off')
                if sync_qa and scenario=='hmi' and monitor and tick==1601:monitor.check_follow('on')
                record=dict(type='tick',tick=tick+1,dt_s=dt,I_start=current['I'],I=response['I'],Q=q,Q_next=qnext,stimuli=response['stimuli'],edges=response['edges'],events=response['events'],judgments=judgments,state=response['state'],state_hash=sha(response['state']),scans=scans)
                record['hash']=sha(record);log.write(canon(record)+b'\n');rows.append(record);current=response;q=qnext
                if gui and tick>=monitor_from_tick:
                    view=response.get('view',{})
                    if scenario=='hmi' or view:
                        assert view.get('scene_tick')==tick+1
                        assert all(view['signal_lamps'][k]==v for k,v in {**response['I'],**response['Q']}.items())
                    targets=[];state=response['state']
                    if tick==0:targets.append('initial')

                    if scenario=='hmi':
                        for at,action in actions.items():
                            if tick==at:targets.append(f'{at:04}-{action}-contact')
                            if tick==at+3:targets.append(f'{at:04}-{action}')
                        if tick==2200:targets.append('curtain-stopped')
                        if tick==2390:targets.append('curtain-left-latched')
                    elif b:
                        if qnext['B.Psh.sol']:targets.append('normal-fire')
                        if state['pusher_x']>.20:targets.append('pusher')
                        if any(p['route']==1 for p in state['parts']):targets.append('chute')
                        if tick==ticks-1:targets.append('complete')
                        if pack:
                            for stage in range(5):
                                if probes.get('PackR0Stage')==stage and tick>350:targets.append('handshake-'+str(stage))
                            if probes.get('PackR0Stage')==0 and 'handshake-4' in captures:targets.append('handshake-6-done-low')
                        if scenario.startswith('recovery'):
                            if tick in (540,590,710,855,885,910,1010,1090,1155,1455,3355):targets.append('recovery-'+str(tick+1))
                            step=record['Q'].get('B.HMI.recoveryStep',0)  # 화면은 이번 step 에 보낸 Q 를 그린다
                            if step>0:targets.append(f'step{step}')
                        if scenario=='packfault':
                            device=record['Q'].get('P.HMI.faultDevice',0)
                            if device:targets.append(f'packfault-device{device}')
                            for at,_ in PACK_FAULTS:
                                if tick==at+130:targets.append(f'packfault-after{at}')
                    else:
                        if 'right' in visits:targets.append('right')
                        if len(visits)>=2:targets.append('left')
                        if probes.get('Rounds')==3:targets.append('complete')
                    for target in targets:
                        if target not in captures:
                            observed=vision.send(dict(cmd='read',capture=str(out/(target+'.png'))));assert observed['state']==state
                            if monitor:monitor.capture(target)
                            captures.append(target);write_json(out/(target+'.json'),dict(record=record,view=observed.get('view')))
                    if RECORD_EVERY and gui and tick%RECORD_EVERY==0:
                        (out/'frames').mkdir(exist_ok=True)
                        vision.send(dict(cmd='read',capture=str(out/'frames'/f'v{tick:05d}.png')))
                        if monitor:monitor.control('capture',out/'frames'/f'l{tick:05d}.png')
                    time.sleep(0)
            result=verdict(cell_name,rows,probes,visits)
            if scenario.startswith('recovery'):
                from scenarios_3j import recovery_check
                result['production_status']='[NOT_RUN]';result['recovery']=recovery_check(rows);result['status']=result['recovery']['status']
            if scenario in ('curtain','hmi'):
                result['production_status']='[NOT_RUN]';result['production_scope']='안전/조작 한정 시나리오, 20개 생산 완료 판정 대상 아님';result['safety']=safety_verdict(rows);result['status']=result['safety']['status']
            if scenario=='hmi':
                from scenarios_3j import hmi_check
                result['hmi']=hmi_check(rows,hmi_records);result['safety']['scope']='정지 상태에서 커튼 조작; 운전 중 정지 지연은 별도 curtain 시험';result['status']=result['hmi']['status']
                write_json(out/'hmi-actions.json',hmi_records)
            result.update(word_sequences=word_seq,word_values=seen_words,count_start=meta['count_start'],type='summary',ticks=len(rows),scans=sum(len(r['scans']) for r in rows),trace_hash=sha([r['hash'] for r in rows]),tick_hashes=[r['hash'] for r in rows],same_input_reference_differences=len(same_input_diffs),captures=captures,seed=seed,scenario=scenario)
            log.write(canon(result)+b'\n');write_json(out/'summary.json',result);write_json(out/'reference-10ms-differences.json',same_input_diffs)
            success=True
    except BaseException as e:
        write_json(out/'failure.json',dict(status='[FAIL]',error=str(e),completed_ticks=len(rows)));raise
    finally:
        cleanup_errors=[]
        for child,close in [(monitor,lambda:monitor.close()),(vision,lambda:vision.close(True)),(engine,lambda:engine.close())]:
            if child:
                try:close()
                except BaseException as e:cleanup_errors.append(str(e))
        exits=dict(vision_exit=vision.process.returncode if vision else None,plc_exit=engine.process.returncode if engine else None,ladder_exit=getattr(monitor,'window_exit',None))
        write_json(out/'processes.json',dict(status='[PASS]' if not cleanup_errors and all(v in (None,0) for v in exits.values()) else '[FAIL]',**exits,run_finished=success,cleanup_errors=cleanup_errors))
        if cleanup_errors:raise RuntimeError(cleanup_errors)
    print(result['status'],cell_name,variant,scenario,'seed',seed,'events',result['event_count'],'ref-diffs',len(same_input_diffs),'hash',result['trace_hash'],flush=True)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cell',choices=['cell-a','cell-b','cell-b-pack'],default='cell-a');p.add_argument('--variant',choices=['correct','swapped-sensors','late-reverse','push-timing-off','ignore-curtain','no-sort-check','no-handshake','ignore-box-full','ignore-reject-full','finish-after-retract','int16-tick','no-handshake-timeout','abs-compare','warn-latch'],default='correct');p.add_argument('--output',type=Path,required=True);p.add_argument('--extctl',type=Path,default=EXTCTL);p.add_argument('--gui',action='store_true');p.add_argument('--no-ladder',action='store_true');p.add_argument('--sync-qa',action='store_true');p.add_argument('--controller',choices=['ladder','reference'],default='ladder');p.add_argument('--ticks',type=int);p.add_argument('--seed',type=int,default=1);p.add_argument('--scenario',choices=['normal','curtain','hmi','recovery','recovery-retract','flow','flow50','flow70','cycle-stop','batch','stroke75','strokeclear','packfault'],default='normal');p.add_argument('--count-start',type=int,nargs=2,metavar=('POSITION','SCAN'));p.add_argument('--defect-rate',type=float,default=.2);a=p.parse_args()
    r=run(a.cell,a.variant,a.output,a.extctl,a.gui,a.controller,a.ticks,a.seed,a.scenario,a.defect_rate,a.no_ladder,a.sync_qa,count_start=tuple(a.count_start) if a.count_start else None);sys.exit(0 if r['status']=='[PASS]' else 1)
