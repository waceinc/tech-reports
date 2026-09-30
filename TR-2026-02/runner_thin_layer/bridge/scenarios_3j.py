"""사전 고정 3j 외부 자극/판정, 제어 출력은 수정하지 않는다."""
import json
from scenarios_3i import negative_judgments

def fault_cell(cell,out):
    definition=json.loads(cell.read_text())
    definition['wiring']=str(cell.with_name('cell-b-sort.io-map.json'))
    for inst in definition['instances']:
        if inst['id'].startswith('part') and inst['id']!='part1':inst['transform']['position'][0]-=1000
    target=out/'flow.plccell.json';target.write_text(json.dumps(definition,ensure_ascii=False,indent=2))
    return target

def recovery_stimuli(t,scenario='recovery'):
    return {'panel.pb3.press':t in [5,850],'panel.pb0.press':t in [30,1150,3400],
            'panel.pb2.press':t==(570 if scenario=='recovery-retract' else 536),'panel.pb2.twist':t==700,
            'recovery.quarantine':t==880,'recovery.finish':900<=t<(950 if scenario=='recovery-retract' else 1000),
            'recovery.home':1000<=t<1100,'recovery.clear':t==3350}

def recovery_check(rows):
    stages={r['scans'][-1]['probes'].get('Recovery') for r in rows}
    last=rows[-1]['scans'][-1]['probes']
    checks={'단계':{0,1,2,3,8,9,10}<=stages,'추적초기화':not last['Locked'],'위험사건없음':not any(r['events'] for r in rows)}
    return dict(status='[PASS]' if all(checks.values()) else '[FAIL]',checks=checks,stages=sorted(stages))

def hmi_check(rows,records):
    if len(rows)<2510:return dict(status='[NOT_RUN]',reason='2510틱 이상 필요')
    at=lambda t:rows[t-1]
    checks={'기동접점':at(31)['I']['B.PB.start'],'예고후운전':at(400)['Q_next']['B.Conv.run'],
            '사이클정지':at(605)['Q_next']['B.Feed.hold'] and at(605)['Q_next']['B.Conv.run'],
            '비상접점':not at(1601)['I']['B.PB.estop_nc'],'비상출력차단':not at(1601)['Q_next']['B.Conv.run'],
            '커튼감지':any(r['I']['B.Safety.curtain'] for r in rows[2100:2250]),
            '전체조작':len(records)==12,'운전자홀드':all(at(t)['stimuli']['panel.pb0.press'] for t in [31,32,33])}
    return dict(status='[PASS]' if all(checks.values()) else '[FAIL]',checks=checks)
