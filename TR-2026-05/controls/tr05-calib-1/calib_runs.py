# TR-05 v0.6 §14-7 교정 실행: 교정 시드마다 F 정답 래더 연결 실행(normal 5,000, 벨트 1.00) → 같은 요청을 M0 열린 고리로 재생. F 가 [PASS] 가 아니면 같은 묶음의 calib 다음 k.
import json, os, sys, subprocess
from pathlib import Path
ROOT=Path.home()/'<tr-public>/고정입력_TR-05';sys.path.insert(0,str(ROOT/'bridge'))
from common import file_sha, read_json
import seed_table
from replay import replay
OUT=Path.home()/'tr05-run/calib-1/calib';OUT.mkdir(parents=True,exist_ok=True)
table_path=ROOT/'seed-table.json';sha=file_sha(table_path);table=read_json(table_path);app=os.environ['TR05_APP']
plan=[(int(b),it['seed']) for b,items in sorted(table['sets']['calib'].items()) for it in items];log=[];pairs=[]
while plan:
    b,seed=plan.pop(0);fdir=OUT/f'F_s{seed}';mdir=OUT/f'M0replay_s{seed}'
    r=subprocess.run(['python3',str(ROOT/'bridge/tr05.py'),'one','--out',str(fdir),'--cell','cell-b','--variant','correct','--scenario','normal','--physics','fast','--seed',str(seed),'--seed-table',str(table_path),'--seed-table-sha256',sha],cwd=ROOT,capture_output=True,text=True)
    s=read_json(fdir/'summary.json');row=dict(bin=b,seed=seed,F_status=s['status'],F_category=s['category'],F_trace_hash=s.get('trace_hash'))
    if s['status']!='[PASS]':
        nx=seed_table.next_seed(app,dict(table,extra_seeds=[x['seed'] for x in log],extra_k={'calib':[x.get('k',0) for x in log if x.get('k')]}),'calib',b);row['skipped']=True;row['replacement']=nx;plan.insert(0,(b,nx['seed']));log.append(row);print('SKIP',row,flush=True);continue
    m=replay(fdir,mdir,app,'mujoco');row.update(M_routes=m['routes']['match'],M_ticks=m['ticks']);log.append(row);pairs.append((seed,str(fdir),str(mdir)));print(row,flush=True)
json.dump(dict(table_sha256=sha,runs=log,pairs=pairs),open(OUT/'calib-runs.json','w'),ensure_ascii=False,indent=1)
