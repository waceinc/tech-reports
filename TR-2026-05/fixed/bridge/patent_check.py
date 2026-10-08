"""TR-2026-05 특허 사전 확인(구현 목록 I16, 사전 등록 §13-1 · §14-5) — 새로 씀.

TR-2026-08(E5)이 쓴 핵심어 대조 도구(patent_scan.py — 등록 제10-2904772호 · 제10-3003470호 · 출원 KP26038 핵심어)를 그대로 불러
이 편의 대상 목록(사전 등록 동결판 · 실행기 공개본 · 표 · 독립 검산 · 공개본 변환 · 공개할 3i 정답 래더 원래 · M1)에 돌린다.
도구의 양성 대조 파일(특허 문구)이 먼저 잡혀야 하고, 잡힌 핵심어는 단어 경계 일치인지(영문 핵심어가 다른 단어 안에 든 것인지)를 함께 적는다.
    python3 bridge/patent_check.py --tool <patent_scan.py> --prereg <사전 등록 동결판.md> [--bundle <공개본 묶음>] --out <결과.json>
    python3 bridge/patent_check.py --selftest --tool <patent_scan.py>
"""
import argparse, importlib.util, json, re, sys
from pathlib import Path
from common import ROOT, write_json, Selftest
PUBLIC=['bridge/run.py','bridge/tr05.py','bridge/transport.py','bridge/round.py','bridge/seed_table.py','bridge/calibrate.py','bridge/tables.py','bridge/recompute.py','bridge/public.py',
        'bridge/common.py','bridge/refcheck.py','bridge/classify.py','bridge/replay.py','bridge/probe_engine.mjs','ladders/cell-b/correct/program.ldprog.json','ladders/cell-b-m1/correct/program.ldprog.json']
def load_tool(path):
    spec=importlib.util.spec_from_file_location('patent_scan',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def word_hit(text,w):
    """영문 핵심어는 앞뒤가 영문자가 아닌 일치만 단어 일치로 본다(예: average 안의 rag 는 단어 일치 아님). 한글은 그대로."""
    if re.fullmatch(r'[\x00-\x7f]+',w):return len(re.findall(r'(?<![A-Za-z])'+re.escape(w)+r'(?![A-Za-z])',text,flags=re.I))
    return len(re.findall(re.escape(w),text))
def check(tool,targets,positive):
    t=load_tool(tool);pc=t.scan([positive])
    if not pc:raise RuntimeError('양성 대조(특허 문구)가 잡히지 않음 — 도구 고장')
    files=[str(p) for p in targets if Path(p).exists()];missing=[str(p) for p in targets if not Path(p).exists()];hits=[]
    for f,pat,w,n in t.scan(files):
        text=Path(f).read_text(encoding='utf-8',errors='ignore');hits.append(dict(file=str(Path(f).relative_to(ROOT)) if Path(f).is_relative_to(ROOT) else Path(f).name,patent=pat,keyword=w,count=n,word_matches=word_hit(text,w)))
    return dict(tool=str(Path(tool).name),positive_control_hits=len(pc),targets=[Path(f).name for f in files],missing=missing,hits=hits,word_level_hits=[h for h in hits if h['word_matches']],
                composition='플랜트 모형 두 개(빠른 이송 · MuJoCo)에 같은 래더를 붙여 사건 · 판정을 비교한다. 그래프 저장소 · 검색 증강 · 변화율 동적 속성 · SHACL 제약 · 명령 선제 차단은 없다')

def selftest(tool):
    T=Selftest('patent_check');tool=Path(tool);pos=tool.parent/'positive_control.txt'
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        clean=Path(d)/'clean.txt';clean.write_text('셀 B(3i) 정답 래더와 MuJoCo 플랜트 비교\n')
        T.red_green('도구의 양성 대조(특허 문구)는 잡히고 깨끗한 글은 0 건',lambda:bool(load_tool(tool).scan([str(clean)])),lambda:bool(load_tool(tool).scan([str(pos)])) and not load_tool(tool).scan([str(clean)]))
    T.check('단어 경계: average 안의 rag 는 단어 일치가 아님, RAG 는 일치',word_hit('the average value','RAG')==0 and word_hit('a RAG system','RAG')==1)
    T.finish()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0]);ap.add_argument('--tool',type=Path,required=True);ap.add_argument('--prereg',type=Path);ap.add_argument('--bundle',type=Path);ap.add_argument('--out',type=Path);ap.add_argument('--selftest',action='store_true');a=ap.parse_args()
    if a.selftest:selftest(a.tool)
    targets=[ROOT/x for x in PUBLIC]+([a.prereg] if a.prereg else [])+([p for p in (a.bundle/'tables.json',a.bundle/'ladders') for p in ([p] if p.is_file() else sorted(p.glob('*')))] if a.bundle else [])
    r=check(a.tool,targets,a.tool.parent/'positive_control.txt')
    if a.out:write_json(a.out,r)
    print('[PASS] patent scan','positive',r['positive_control_hits'],'targets',len(r['targets']),'hits',len(r['hits']),'word-level',len(r['word_level_hits']),'missing',len(r['missing']))
    for h in r['hits']:print('  ',h['file'],h['patent'],h['keyword'],h['count'],'word',h['word_matches'])
