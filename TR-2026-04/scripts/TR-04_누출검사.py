#!/usr/bin/env python3
"""TR-2026-04 누출 검사 — 사전 등록 v0.4 §7 다섯째 항목.

「빈칸 과제의 base 에는 정답 렁이 들어 있다(과제 정의상 불가피). 산출물에서 빈칸 블록의 정답 렁 주석 문자열이 나오면
누출로 보고 그 래더를 무효로 한다(수 보고).」
고정 실행 코드(tr04_개정1)에는 이 검사가 없었다 — 결과 뒤(2026-10-02) 이 정의대로 따로 센다 [작업자: 방동걸].

판정: 빈칸 과제마다 정답 래더의 빈칸 블록 렁(rungs[s0:s1+1]) 주석 중 비어 있지 않은 것을 모은다. 생성기 산출 `out/blank.json`
원문에 그 문자열 중 하나라도 그대로(부분 문자열 일치) 나오면 누출. 같은 문자열이 사양서·부록·base 에도 있으면 함께 표시한다
(생성기가 정답이 아니라 과제 묶음에서 옮겼을 수 있다 — 무효 판정은 사전 등록 정의대로 하되, 출처 후보를 같이 적는다).

사용: python3 TR-04_누출검사.py <task_list.json> <ladders 폴더> <work 폴더>   → 표준 출력(결정적)
"""
import json, re, sys
from datetime import datetime
from pathlib import Path

tasks = json.loads(Path(sys.argv[1]).read_text())['tasks']
ladders, work = Path(sys.argv[2]), Path(sys.argv[3])
total = leaks = 0
rows = []
for t in tasks:
    if t['kind'] == '전체':
        continue
    lad = json.loads((ladders / t['cell'] / 'correct' / 'program.ldprog.json').read_text())
    s0, s1 = t['rungs']
    comments = sorted({(r.get('comment') or '').strip() for r in lad['rungs'][s0:s1 + 1]} - {''})
    for d in sorted(work.glob(f"{t['id']}-G*-r*")):
        out = d / 'out' / 'blank.json'
        unit = d / 'unit.json'
        # 보정(2026-10-02): unit.json 이 없거나 산출이 단위 종료(finished)보다 5 초 넘게 늦으면 생성 산출이 아니다(고아 프로세스가 쓴 파일)
        if out.exists() and (not unit.exists() or out.stat().st_mtime > datetime.fromisoformat(json.loads(unit.read_text())['finished']).timestamp() + 5):
            rows.append((d.name, '늦은 파일(산출 아님)', []))
            continue
        if not out.exists():
            rows.append((d.name, '산출 없음', []))
            continue
        total += 1
        text = out.read_text(encoding='utf-8', errors='replace')
        hit = [c for c in comments if c in text]
        if hit:
            leaks += 1
            pack = ''.join(p.read_text(encoding='utf-8', errors='replace') for p in list((d / 'spec').glob('*.md')) + [d / 'appendix.md', d / 'TASK.md', d / 'base.ldprog.json'] if p.exists())
            rows.append((d.name, '누출', [(c, '과제 묶음에도 있음' if c in pack else '정답에만') for c in hit]))
        else:
            rows.append((d.name, '없음', []))
    print(f"{t['id']} {t['cell']} 렁 {s0}~{s1} · 정답 주석 {len(comments)} 개")
print(f'\n빈칸 산출 {total} 개 중 누출 {leaks} 개')
kinds = {'대입·연산 형식': 0, '알람 정형 문구': 0, '이름형': 0}; inpack = allhit = 0
for name, st, hit in rows:
    for c, where in hit:
        allhit += 1; inpack += where != '정답에만'
        body = re.sub(r'^\[[^\]]+\]\s*', '', c)
        kinds['대입·연산 형식' if re.search(r'←|=.*\b(ADD|SUB|MUL|DIV)\b', body) else '알람 정형 문구' if re.search(r'(SET 기억|발생 조건|해제)', body) else '이름형'] += 1
print(f'걸린 문자열(단위별 중복 포함) {allhit} · {kinds} · 과제 묶음에도 있음 {inpack}')
for name, st, hit in rows:
    if st != '없음':
        print(' ', name, st, hit)
