"""TR-2026-05 M1 래더 재생성(구현 목록 I12, 사전 등록 §6-1 공통 규칙 · §10 M1 래더) — 새로 씀.

generate_3i.program() 에 새 상수(슈트 확인 창 · 슈트 가득 · 발사 지연 뺄셈 상수)만 넣어 셀 B 정답 · push-timing-off(상대 +50 그대로) ·
ignore-curtain · no-sort-check 를 다시 만들고, 원래 래더와의 줄 단위 차이가 상수 리터럴 줄에만 있는지 확인한다.
M1 참조 논리 매개변수표(refcheck.m1_reference_params)와 새 상수 표도 함께 쓴다. 태그는 cells/cell-b.tagmap.json(io-map 사본) 에서 읽는다.
**M1 재생성은 동결(§14-6) · 교정 뒤에만 한다** — 고정 입력 폴더(ladders/cell-b-m1/)에 쓰려면 --frozen-commit 이 필요하다.
    python3 bridge/regenerate_m1.py --constants <새상수.json> --out <폴더> [--frozen-commit <40자>]
    python3 bridge/regenerate_m1.py --selftest
"""
import argparse, json, sys, tempfile
from pathlib import Path
from common import ROOT, sha_bytes, write_json, read_json, Selftest
import generate_3i
from refcheck import m1_reference_params
VARIANTS=('correct','push-timing-off','ignore-curtain','no-sort-check')
ORIGINAL_SHA={'correct':'eb44ce59b386e175ab22255f684dbd277b27e00906fb0b92d81703e7f389209f','push-timing-off':'78951c5517af831727f5518d5d31b0ad9a702ff0feb605b45a590afe829f4010',
              'ignore-curtain':'396aa80ffa273e6d0374ffd8a99c1eb619a5224a7ef7d8338c70961cd98e2d7d','no-sort-check':'22ccda36321cdbd4b9bd1c651deab467157ecfe88347d0ed9a3e515b035724dc'}
def bindings():
    return read_json(ROOT/'cells/cell-b.tagmap.json')['bindings']
def normalize(c):
    c=dict(generate_3i.CONSTANTS,**(c or {}));c['chute_window']=tuple(int(x) for x in c['chute_window']);c['chute_full_scans']=int(c['chute_full_scans']);c['fire_delay_sub']=int(c['fire_delay_sub']);return c
def texts(constants=None):
    b=bindings();c=normalize(constants);return {v:generate_3i.text(generate_3i.program(b,'cell-b',v,c)).encode() for v in VARIANTS}
def literal_pairs(c):
    """원래 → 새 리터럴(바뀐 상수만). 리터럴은 INT#n 과 렁 설명문의 숫자로 나타난다."""
    o=generate_3i.CONSTANTS;pairs=[]
    for (a,b) in zip(o['chute_window'],c['chute_window']):
        if a!=b:pairs.append((a,b))
    if o['chute_full_scans']!=c['chute_full_scans']:pairs.append((o['chute_full_scans'],c['chute_full_scans']))
    if o['fire_delay_sub']!=c['fire_delay_sub']:pairs.append((o['fire_delay_sub'],c['fire_delay_sub']))
    return pairs
def line_diff(old,new,pairs):
    """줄 수가 같고, 다른 줄은 모두 '원래 줄에서 상수 리터럴 하나(INT#a → INT#b, 또는 설명문의 a → b)만 바꾼 줄'이어야 한다."""
    lo=old.decode().split('\n');ln=new.decode().split('\n')
    if len(lo)!=len(ln):return dict(ok=False,reason=f'줄 수 다름 {len(lo)} → {len(ln)}')
    changed=[(i+1,a,b) for i,(a,b) in enumerate(zip(lo,ln)) if a!=b];bad=[]
    for i,a,b in changed:
        if not any(a.replace(f'INT#{x}',f'INT#{y}')==b or a.replace(f' {x}"',f' {y}"')==b for x,y in pairs):bad.append(dict(line=i,old=a.strip(),new=b.strip()))
    return dict(ok=not bad,changed_lines=len(changed),bad=bad[:5],examples=[dict(line=i,old=a.strip(),new=b.strip()) for i,a,b in changed[:6]])
def regenerate(constants,out):
    c=normalize(constants);orig={v:(ROOT/'ladders/cell-b'/v/'program.ldprog.json').read_bytes() for v in VARIANTS};new=texts(c);pairs=literal_pairs(c);report={}
    out.mkdir(parents=True,exist_ok=False)
    for v in VARIANTS:
        (out/v).mkdir();(out/v/'program.ldprog.json').write_bytes(new[v])
        report[v]=dict(sha256=sha_bytes(new[v]),original_sha256=sha_bytes(orig[v]),diff=line_diff(orig[v],new[v],pairs))
    params=m1_reference_params(dict(chute_window=list(c['chute_window']),chute_full_scans=c['chute_full_scans'],fire_delay_sub=c['fire_delay_sub']))
    table=dict(schema='tr05-m1-constants/1',constants=dict(chute_window=list(c['chute_window']),chute_full_scans=c['chute_full_scans'],fire_delay_sub=c['fire_delay_sub']),unchanged=dict(coefficient_232=232,initial_delay=16,out_window=[198,269],arrival_on_limit=29,output_full=100,pusher_timeout=31))
    write_json(out/'m1-constants.json',table);write_json(out/'m1-reference-params.json',params)
    ok=all(r['diff']['ok'] for r in report.values())
    write_json(out/'regenerate-report.json',dict(status='[PASS]' if ok else '[FAIL]',ladders=report,constants_sha256=sha_bytes((out/'m1-constants.json').read_bytes()),params_sha256=sha_bytes((out/'m1-reference-params.json').read_bytes())))
    return ok,report

def selftest():
    T=Selftest('regenerate_m1');orig=texts()
    T.red_green('원래 상수로 재생성하면 4개 래더가 원래 sha256(§10)과 바이트 같음(창 하한 166 은 다름)',lambda:all(sha_bytes(t)==ORIGINAL_SHA[v] for v,t in texts(dict(chute_window=(166,235))).items()),
                lambda:all(sha_bytes(t)==ORIGINAL_SHA[v] and (ROOT/'ladders/cell-b'/v/'program.ldprog.json').read_bytes()==t for v,t in orig.items()))
    for name,c in [('슈트 창',dict(chute_window=(150,251))),('슈트 가득',dict(chute_full_scans=60)),('발사 지연 뺄셈',dict(fire_delay_sub=5))]:
        new=texts(c);pairs=literal_pairs(normalize(c));d={v:line_diff(orig[v],new[v],pairs) for v in VARIANTS}
        tamper=new['correct'].replace(b'"B.Lamp.red"',b'"B.Lamp.yellow"',1)
        T.red_green(f'{name}: 차이가 그 리터럴 줄에만 있음(다른 줄을 고친 래더는 잡힘), 바뀐 줄 {d["correct"]["changed_lines"]}',lambda:line_diff(orig['correct'],tamper,pairs)['ok'],lambda:all(x['ok'] and x['changed_lines']>0 for k,x in d.items() if not (k=='no-sort-check' and name=='슈트 창')))
    nsc=line_diff(orig['no-sort-check'],texts(dict(chute_window=(150,251)))['no-sort-check'],[(165,150),(235,251)])
    T.check(f'no-sort-check 는 창 판정 렁이 없어 창 상수의 바뀐 줄이 적음({nsc["changed_lines"]}) — 결함 줄은 원래와 같음',nsc['ok'])
    ptoff=texts(dict(fire_delay_sub=5))['push-timing-off'].decode()
    T.check('push-timing-off 결함 +50 은 상대 오프셋으로 그대로',ptoff.count('"IN2": "INT#50"')==orig['push-timing-off'].decode().count('"IN2": "INT#50"')>0)
    with tempfile.TemporaryDirectory() as d:
        ok,rep=regenerate(dict(chute_window=[160,240],chute_full_scans=50,fire_delay_sub=6),Path(d)/'m1')
        T.check('regenerate(): 4개 래더 · 새 상수 표 · M1 참조 매개변수표 · 보고서',ok and all((Path(d)/'m1'/f).exists() for f in ('m1-constants.json','m1-reference-params.json','regenerate-report.json')))
    T.finish()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0]);ap.add_argument('--constants',type=Path);ap.add_argument('--out',type=Path);ap.add_argument('--frozen-commit');ap.add_argument('--selftest',action='store_true');a=ap.parse_args()
    if a.selftest:selftest()
    if not (a.constants and a.out):ap.error('--constants 와 --out 필요')
    out=a.out.resolve()
    if out.is_relative_to(ROOT) and not (a.frozen_commit and len(a.frozen_commit)==40):sys.exit('[REFUSED] 고정 입력 폴더 안의 M1 래더는 동결 · 교정 뒤에만 — --frozen-commit <40자>')
    if out.is_relative_to(ROOT/'ladders/cell-b'):sys.exit('[REFUSED] 원래 래더 폴더에는 쓰지 않는다(ladders/cell-b-m1/ 을 쓴다)')
    c=read_json(a.constants);c=c.get('constants',c);ok,rep=regenerate(c,out)
    print('[PASS]' if ok else '[FAIL]','M1 ladders',{v:r['sha256'][:12] for v,r in rep.items()});sys.exit(0 if ok else 1)
