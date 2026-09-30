"""TR-03_분석.py 의 결과 md 표 생성부(파일 300줄 제한으로 분리). 계산은 하지 않고 결과 dict 를 표로만 옮긴다."""
from TR03_분석_집계 import CELLS, GROUPS, STAGES

CELL_NAME = {'cell-a': '셀 A', 'cell-b': '셀 B', 'cell-b-pack': '포장 셀'}
SET_NAME = {'full': '유량 0.45 포함(사전 등록 시나리오 전부 — 주 결과)', 'no045': '유량 0.45 제외'}
STAGE_NAME = {'1': '1 미활성', '2': '2 활성·출력 무변화', '3': '3 출력 변화·사건 무변화', '4a': '4a 드러남(위험 사건)',
              '4b': '4b 드러남(판정만)', '보류': '보류(실행 누락·재스캔 불일치)'}


def fr(x):
    """분모 20 미만이면 분자/분모만."""
    return f"{x['n']}/{x['d']}" if x.get('pct') is None else f"{x['n']}/{x['d']} ({x['pct']} %)"


def render(r):
    v = r['validity']
    L = [f"# TR-2026-03 결과 — {r['round']}", '',
         '사전 등록 v0.3 §5 4단계 · §6 지표 · §7 예측을 정의 그대로 집계했다. 생성: `실행/TR-03_분석.py` (결정적 — 시각 값 없음). '
         '결과 전 해석은 `실행/TR-03_분석_고정기록.md` I-1~I-8.', '',
         '| 입력 · 스크립트 | sha256 |', '| --- | --- |',
         f"| ledger.jsonl | `{r['ledger_sha256']}` |", f"| 변종 목록 | `{r['variant_list_sha256']}` |",
         f"| 브리지 run.py · engine.mjs | `{r['bridge_run_py_sha256']}` · `{r['engine_mjs_sha256']}` |"]
    L += [f'| {m} | `{h}` |' for m, h in r['modules'].items()]
    L += ['', '## 0. 무효 기준 재확인 (§7 → TR-2026-02 §6)', '', '| 항목 | 값 |', '| --- | --- |',
          f"| 실행기 상태 첫 줄 | {v['status_line']} |",
          f"| 고정 입력 대조 기록 · 불일치 | {len(v['fixed_input_checks'])} 회 · {'있음 [FAIL]' if v['fixed_input_mismatch'] else '없음'} |",
          f"| 변종 래더 해시표 = 첫 시작 기록 | {'[PASS]' if v['ladders_table_sha_ok'] else '[FAIL]'} |",
          f"| ledger 행 · 번호 | {v['ledger_rows']} · {v['distinct_no']} |",
          f"| 조합 수 = 사전 등록 §3-2 | {'[PASS]' if v['counts_match_prereg'] else '[FAIL]'} |",
          f"| 문제 있는 실행(무효·오류·건너뜀) | {len(v['run_problems'])} |"]
    for c, x in v['counts'].items():
        L.append(f"| {CELL_NAME[c]} 원본 기준 · 변종 · 변종 실행 (사전 등록) | {x['baseline_runs']} · {x['variants']} · {x['variant_runs']} ({x['expected'][0]} · {x['expected'][1]}) |")
    L += ['', '유효 시나리오와 제외한 시나리오(§4 — 원본 기준 실행이 오류·무효면 그 셀에서 뺀다):', '']
    for c in CELLS:
        L.append(f"- {CELL_NAME[c]}: 유효 {', '.join(v['valid_scenarios'][c]) or '-'}")
    for k, why in v['excluded_scenarios'].items():
        L.append(f'- 제외 {k}: {why}')
    L += ['', '원본 재스캔 자가검증(1단계 근거 — 기록된 스캔 digest·Q 와 다시 스캔한 값이 모두 같아야 [PASS]):', '',
          '| 원본 실행 | 판정 | 스캔 | digest 불일치 | Q 불일치 | 이미지 Q 불일치 | 복원 예외 | I_start 사슬 끊김 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for k, x in v['rescan'].items():
        c = x['checks']
        L.append(f"| {k} | {'[PASS]' if x['ok'] else '[FAIL]'} | {c.get('scans', 0)} | {c.get('digest_mismatch', 0)} | {c.get('q_mismatch', 0)} | "
                 f"{c.get('image_q_mismatch', 0)} | {c.get('reconstruct_exceptions', 0)} | {c.get('I_start_chain_breaks', 0)} |")
    if v['run_problems']:
        L += ['', '문제 있는 실행(번호: 사유) — 앞 30 건:', '']
        L += [f'- {no}: {"; ".join(w)}' for no, w in list(v['run_problems'].items())[:30]]
    for sname in ('full', 'no045'):
        s = r['sets'][sname]
        p = s['predictions']
        L += ['', f'## {SET_NAME[sname]}', '', '### 예측 판정 (§7, 세 셀 합산 · 보류는 분모에서 뺌)', '',
              '| 예측 | 판정 | 값 |', '| --- | --- | --- |',
              f"| P1 | {p['P1']['verdict']} | 미검출(1~3단계) 비율 — 복귀·포장 핸드셰이크 {fr(p['P1']['return_and_handshake'])} · 안전 {fr(p['P1']['safety'])} · "
              f"차이 {p['P1']['diff_pp']} %p (참고: 복귀만 {p['P1']['reference_diff_pp'].get('복귀')} · 포장 핸드셰이크만 {p['P1']['reference_diff_pp'].get('포장 핸드셰이크')} %p) |",
              f"| P2 | {p['P2']['verdict']} | 미검출 {p['P2']['undetected']} 중 1단계 {p['P2']['stage1']} ({p['P2']['pct']} %) |",
              '', '### 지표 1 — 드러난(4단계) 비율', '',
              '| 셀 | 묶음 | 분모 추출 변종 전체 | 분모 활성(2~4단계) | 보류 |', '| --- | --- | --- | --- | --- |']
        for c, gs in s['metric1'].items():
            for g in GROUPS + ['전체']:
                if g in gs:
                    L.append(f"| {CELL_NAME[c]} | {g} | {fr(gs[g]['all'])} | {fr(gs[g]['active'])} | {gs[g]['held']} |")
            w = gs['가중 전체']
            L.append(f"| {CELL_NAME[c]} | 가중 전체(§3-1 모집단 {w['population']}) | {w['pct']} % | - | - |")
        L += ['', '### 지표 2 — 4단계 분포', '', '「4a 중 위험 사건」 = 드러낸 실행에서 생산 사건(I-3)을 뺀 사건 이름별 개수가 원본과 다른 변종. '
              '나머지 4a 는 생산 사건 개수나 최종 상태(I-2)만 다르다.', '',
              '| 셀 | 묶음 | ' + ' | '.join(STAGE_NAME[x] for x in STAGES) + ' | 4a 중 위험 사건 |',
              '| --- | --- |' + ' --- |' * (len(STAGES) + 1)]
        for c, gs in s['metric2'].items():
            for g in GROUPS + ['전체']:
                if g in gs:
                    L.append(f"| {CELL_NAME[c]} | {g} | " + ' | '.join(str(gs[g][x]) for x in STAGES) + f" | {gs[g]['4a_위험사건']} |")
        L += ['', '### 지표 3 — 처음 드러낸 시나리오(§4 표 순서) · 한 시나리오만 잡은 변종', '',
              '| 셀 | 처음 드러낸 시나리오: 변종 수 | 한 시나리오만 잡은 변종 | 드러낸 시나리오 수 분포 |', '| --- | --- | --- | --- |']
        for c, x in s['metric3'].items():
            first = ' · '.join(f'{k}: {n}' for k, n in x['first_revealed'].items()) or '-'
            hist = ' · '.join(f'{k}개: {n}' for k, n in x['revealed_scenario_count_hist'].items()) or '-'
            L.append(f"| {CELL_NAME[c]} | {first} | {x['only_one_scenario']} | {hist} |")
        po = s['predictions_outcome_first']
        L += ['', f"I-1 민감도(참고 — 미활성인데 출력이 달라진 변종 {len(s['inactive_but_q_changed'])} 개를 실행 결과대로 다시 분류): "
              f"P1 {po['P1']['verdict']} 차이 {po['P1']['diff_pp']} %p · P2 {po['P2']['verdict']} {po['P2']['pct']} %"]
        rep = s['representatives']
        L += ['', f"대표 사례(§10, 범주별 가장 작은 번호): 드러남 {rep['드러남']} · 미활성 {rep['1']} · "
              f"미활성인데 출력이 달라진 변종(I-1 한계 표시) {len(s['inactive_but_q_changed'])} 개 {s['inactive_but_q_changed'][:10]}"]
    L += ['', '## 기록만 — 시각 차이 열(§5 「시각 차이는 별도 열」)', '',
          '변종별 실행 결과(단계·Q 첫 차이 틱·사건 첫 발생 틱 이동·전체 상태 해시 일치)는 JSON `run_levels` 에 있다. '
          '아래는 3단계 실행 중 사건 개수는 같고 첫 발생 틱만 달라진 실행 수.', '']
    shifted = sum(1 for d in r['run_levels'].values() for x in d.values()
                  if isinstance(x, dict) and x['level'] == '3' and x['event_first_tick_shift'])
    L += [f'- 3단계이면서 사건 시각만 달라진 실행: {shifted}', '']
    return '\n'.join(L)
