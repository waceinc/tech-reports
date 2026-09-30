"""검증 자극 및 판정. PLC 출력 결정에는 사용하지 않는다."""
import json
from pathlib import Path
from transport import ROOT

def fault_cell(cell,out):
    target=out/'fault-cell';target.mkdir();definition=json.loads(cell.read_text());io=json.loads(cell.with_name('cell-b-sort.io-map.json').read_text())
    io.setdefault('constants',{})['pusher.flow_restriction']=True
    (target/'cell-b-sort.io-map.json').write_text(json.dumps(io,ensure_ascii=False,indent=2))
    (target/'cell-b-sort.plccell.json').write_text(json.dumps(definition,ensure_ascii=False,indent=2))
    (target/'vision2').symlink_to(cell.parent/'vision2',target_is_directory=True)
    return target/'cell-b-sort.plccell.json'

def recovery_stimuli(tick):
    return {'panel.pb3.press':tick in (5,600),'panel.pb0.press':tick in (30,520,900,2750),
            'operator.present':280<=tick<450,'recovery.quarantine':tick==630,
            'recovery.home':650<=tick<850,'recovery.clear':tick in (950,2700),
            'collector.chute':tick>=650}

def recovery_check(rows):
    def p(t):return rows[t-1]['scans'][-1]['probes']
    stages={r['scans'][-1]['probes'].get('Recovery') for r in rows}
    results={'all_stages':{0,1,2,3,4,6,7,8,9}<=stages,'locked_start_refused':not p(525)['Running'],
             'early_clear_refused':p(955)['Recovery']==9,'tracking_cleared':p(2705)['Recovery']==0 and not p(2705)['Locked'],
             'clear_alone_stopped':not p(2705)['Running'],'separate_start':p(2760)['Running']}
    return dict(status='[PASS]' if all(results.values()) else '[FAIL]',checks=results,stages=sorted(stages))

def hmi_check(rows,records):
    if len(rows)<590:return dict(status='[NOT_RUN]',reason='HMI 전체 판정은 590틱 이상 필요',completed_ticks=len(rows))
    def at(t):return rows[t-1]
    checks={'start_contact':at(31)['I']['B.PB.start'],'start_ladder':at(31)['Q_next']['B.Conv.run'],
            'stop_contact':not at(101)['I']['B.PB.stop_nc'],'stop_ladder':not at(101)['Q_next']['B.Conv.run'],
            'restart_before_tracking':at(141)['Q_next']['B.Conv.run'],'estop_contact':not at(201)['I']['B.PB.estop_nc'],
            'estop_ladder':not at(201)['Q_next']['B.Conv.run'],'estop_latch':at(220)['scans'][-1]['probes']['Latch'],
            'reset_start_preserves_tracking':at(300)['Q_next']['B.Conv.run'] != at(220)['scans'][-1]['probes']['Locked'],
            'curtain_detected':any(r['I']['B.Safety.curtain'] for r in rows[370:450]),
            'all_widget_actions':len(records)>=12,
            'widget_held':all(at(t)['stimuli']['panel.pb0.press'] for t in (31,32,33)),
            'external_mode':all('외부' in x['response']['notice'] for x in records)}
    return dict(status='[PASS]' if all(checks.values()) else '[FAIL]',checks=checks)

def negative_judgments(cell,I,q,probes,tick):
    result=[]
    def add(name):result.append(dict(name=name,tick=tick,origin='bridge-verdict'))
    if cell=='cell-b-pack':
        for i in range(2):
            r=f'P.R{i}.';c=f'P.C{i}.'
            if I[c+'full'] and q[r+'request']:add('PLC_BOX_FULL_IGNORED')
            if (I[r+'done'] and not q[r+'ack']) or (I[c+'done'] and not q[c+'ack']):add('PLC_HANDSHAKE_MISSING')
        if (I['P.Tote.full'] or I['P.Tote.count']>=4) and q['P.Reject.gate']:add('PLC_REJECT_FULL_IGNORED')
        if I['P.Tote.done'] and not q['P.Tote.ack']:add('PLC_HANDSHAKE_MISSING')
    return result
