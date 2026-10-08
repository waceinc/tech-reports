"""TR-2026-05 공개본 변환 · 공개 전 문자열 검사(구현 목록 I15, 사전 등록 §12) — 새로 씀.

회차 폴더 → 공개본 묶음: results.jsonl(경로 뺀 꼬리표) · runs/<run_id>.json(실행별 축약 — 범주 · 판정 · 사건 코드 묶음 · 경로 · 첫 잠금 ·
참조 일치 원자료 · M 진단 해시, 절대 경로 없음) · tables.json · fixed.json · seed-table.json · 공개 래더(셀 A · 셀 B(3i) 정답, M1 정답이 있으면 함께 —
`marker` 줄을 뺀 공개본과 실행본 sha256). 끝에 묶음 전체를 문자열 검사(로컬 절대 경로 · 홈 · 계정 이름 · 세션 경로 · 비공개 호스트 URL · 메일 · 기밀 표지)해
0 건일 때만 [PASS]. 검사기는 매번 일부러 넣은 양성 대조 한 줄을 잡는지 먼저 본다. 이 파일도 공개본이므로 찾는 문자열(기밀 표지 · 양성 대조)은
조각을 이어 만들고, 계정 이름 목록은 공개하지 않는 파일(--names, 한 줄에 하나) 또는 환경 변수 TR05_PRIVATE_NAMES(쉼표)로만 받는다.
    python3 bridge/public.py build <회차 폴더> --out <묶음> [--fixed <고정값.json>] [--seed-table <표>]
    python3 bridge/public.py scan <파일 · 폴더…>
    python3 bridge/public.py --selftest
"""
import argparse, json, os, re, shutil, sys, tempfile
from pathlib import Path
from common import ROOT, read_json, write_json, sha_bytes, Selftest
SECRET='CONFI'+'DENTIAL';SESSION='scratch'+'pad'
def accounts(path=None):
    names=[x.strip() for x in os.environ.get('TR05_PRIVATE_NAMES','').split(',') if x.strip()]
    if path:names+=[x.strip() for x in Path(path).read_text().splitlines() if x.strip()]
    return names
def patterns(names):
    return BASE+([('계정 이름',r'(?<![A-Za-z0-9])(?:'+'|'.join(map(re.escape,names))+r')(?![A-Za-z0-9])')] if names else [])
BASE=[('로컬 절대 경로',r'(?<![\w.])/(?:home|Users|tmp|var/folders|private/var|mnt|Volumes|media|opt/homebrew)/[^\s"\'<>]+'),('윈도우 경로',r'\b[A-Za-z]:\\\\?(?:Users|Documents|Windows)\\'),
          ('홈 폴더',r'(?<![\w/])'+'~'+r'/[^\s"\']+'),('세션 경로',r'claude-\d{3,}|'+SESSION+r'|-home-[\w-]+|/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/'),
          ('비공개 호스트 URL',r'https?://(?:localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|[\w.-]+\.local\b|[\w.-]*(?:synology|quickconnect|nas)[\w.-]*)'),
          ('메일 주소',r'[\w.+-]+@[\w-]+\.[\w.-]+'),('기밀 표지',SECRET)]
PLANT='/'+'home/someone/secret/run.json  user'+'@'+'example.com'
NAMES=[]
def scan_text(text,name='?'):
    hits=[]
    for i,line in enumerate(text.splitlines(),1):
        for label,pat in patterns(NAMES):
            for m in re.finditer(pat,line):hits.append(dict(file=name,line=i,kind=label,match=m.group(0)[:80]))
    return hits
def scan(paths):
    """양성 대조를 먼저 잡은 뒤에 실제 검사(잡지 못하면 검사기 고장으로 [FAIL])."""
    if len({h['kind'] for h in scan_text(PLANT)})<2:raise RuntimeError('문자열 검사기 양성 대조 실패')
    hits=[];files=0
    for p in paths:
        p=Path(p);items=[x for x in p.rglob('*') if x.is_file()] if p.is_dir() else [p]
        for f in items:
            files+=1;b=f.read_bytes()
            try:text=b.decode('utf-8')
            except UnicodeDecodeError:text=b.decode('latin-1')
            hits+=scan_text(text,str(f.name if not p.is_dir() else f.relative_to(p)))
            hits+=scan_text(str(f.relative_to(p) if p.is_dir() else f.name),'(파일 이름)')
    return dict(files=files,hits=hits)
def public_ladder(src):
    """실행본에서 `"marker": …` 줄을 뺀 공개본. 공개본 + 그 줄(4번째 줄)로 실행본 sha256 을 다시 만들 수 있다."""
    raw=src.read_bytes();lines=raw.decode().split('\n');keep=[l for l in lines if not l.lstrip().startswith('"marker":')]
    if len(keep)!=len(lines)-1:raise ValueError(f'{src}: marker 줄이 정확히 하나가 아님')
    out='\n'.join(keep).encode();return out,dict(run_sha256=sha_bytes(raw),public_sha256=sha_bytes(out),marker_line=lines.index(next(l for l in lines if l.lstrip().startswith('"marker":')))+1)
def build(round_dir,out,fixed=None,seed_tab=None):
    import classify, tables
    round_dir=Path(round_dir);out=Path(out);out.mkdir(parents=True,exist_ok=False);(out/'runs').mkdir();(out/'ladders').mkdir();idx=[]
    for line in (round_dir/'results.jsonl').read_text().splitlines():
        if not line.strip():continue
        r=json.loads(line);d=round_dir/r['dir']
        if r['group']=='openloop':
            s=read_json(d/'summary.json');dig={k:s[k] for k in ('physics_mode','ticks','identical_to_source','p7','routes','part_drop','chute') if k in s};dig['edge_table']={k:{kk:vv for kk,vv in v.items()} for k,v in s['edge_table'].items()}
        else:dig=classify.digest(d)
        write_json(out/'runs'/f'{r["run_id"]}.json',dig);idx.append({k:v for k,v in r.items() if k not in ('dir','attempts')})
    (out/'results.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in idx))
    if fixed:shutil.copy(fixed,out/'fixed.json')
    if seed_tab:shutil.copy(seed_tab,out/'seed-table.json')
    lad={}
    for rel in ('cell-a/correct','cell-b/correct','cell-b-m1/correct'):
        src=ROOT/'ladders'/rel/'program.ldprog.json'
        if src.exists():b,info=public_ladder(src);name=rel.replace('/','__')+'.program.ldprog.json';(out/'ladders'/name).write_bytes(b);lad[name]=info
    write_json(out/'ladders/ladders-sha256.json',lad)
    t=tables.build(out);write_json(out/'tables.json',t)
    s=scan([out]);write_json(out/'string-scan.json',dict(status='[PASS]' if not s['hits'] and NAMES else '[FAIL]',account_names_checked=len(NAMES),**s))
    if not NAMES:s['hits'].append(dict(file='-',line=0,kind='계정 이름',match='계정 이름 목록이 없어 검사하지 않음(--names)'))
    return t,s

def selftest():
    T=Selftest('public')
    with tempfile.TemporaryDirectory() as d:
        d=Path(d);(d/'a.json').write_text(json.dumps(dict(status='[PASS]',hash='ab'*32)))
        dirty=d/'dirty';dirty.mkdir();(dirty/'x.txt').write_text('ok\n'+PLANT+'\n');clean=d/'clean';clean.mkdir();(clean/'x.txt').write_text('셀 B(3i) 정답 래더 sha256 eb44ce59\nhttps://zenodo.org/records/1\n')
        T.red_green('문자열 검사: 일부러 넣은 경로 · 메일 한 줄을 잡고, 깨끗한 묶음은 0 건',lambda:not scan([dirty])['hits'],lambda:not scan([clean])['hits'] and len(scan([dirty])['hits'])>=2)
        NAMES[:]=['acct'+'x1'];T.check('계정 이름 · 세션 경로 · 비공개 URL · 기밀 표지 · 홈 각각 잡음',all(scan_text(x) for x in ('user '+'acct'+'x1 here','/'+'tmp/claude-'+'1000/x','http://'+'192.168.0.5/a',SECRET+' — x','~'+'/proj/a')));NAMES[:]=[]
        src=ROOT/'ladders/cell-b/correct/program.ldprog.json';pub,info=public_ladder(src);lines=pub.decode().split('\n');marker=next(l for l in src.read_text().split('\n') if '"marker"' in l)
        rebuilt='\n'.join(lines[:info['marker_line']-1]+[marker]+lines[info['marker_line']-1:]).encode()
        T.red_green('공개 래더: marker 줄을 빼고, 그 줄을 되넣으면 실행본 sha256(eb44ce59…)',lambda:SECRET.encode() not in src.read_bytes(),lambda:SECRET.encode() not in pub and sha_bytes(rebuilt)==info['run_sha256']=='eb44ce59b386e175ab22255f684dbd277b27e00906fb0b92d81703e7f389209f')
    T.finish()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0]);ap.add_argument('mode',nargs='?',choices=['build','scan']);ap.add_argument('paths',nargs='*',type=Path);ap.add_argument('--out',type=Path)
    ap.add_argument('--fixed',type=Path);ap.add_argument('--seed-table',type=Path);ap.add_argument('--names',type=Path,help='계정 이름 목록(공개하지 않는 파일)');ap.add_argument('--selftest',action='store_true');a=ap.parse_intermixed_args()
    NAMES[:]=accounts(a.names)
    if a.selftest:selftest()
    if a.mode=='scan':
        s=scan(a.paths)
        if not NAMES:print('[WARN] 계정 이름 목록 없음 — --names 또는 TR05_PRIVATE_NAMES')
        [print(f"{h['file']}:{h['line']} {h['kind']} {h['match']}") for h in s['hits']];print('[PASS]' if not s['hits'] else '[FAIL]','string scan',s['files'],'files',len(s['hits']),'hits');sys.exit(0 if not s['hits'] else 1)
    if a.mode=='build':t,s=build(a.paths[0],a.out,a.fixed,a.seed_table);print('[PASS]' if not s['hits'] else '[FAIL]','public bundle',a.out,'hits',len(s['hits']),{k:v['result'] for k,v in t['predictions'].items()});sys.exit(0 if not s['hits'] else 1)
    ap.error('mode 필요')
