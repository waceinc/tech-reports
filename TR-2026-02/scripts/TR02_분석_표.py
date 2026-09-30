"""TR-02_분석.py 의 결과 md 표 생성부(파일 300줄 제한으로 분리). 계산은 하지 않고 결과 dict 를 표로만 옮긴다."""

WIDTHS = [5, 15, 25, 35, 45]
LADDERS = ['correct', 'late-reverse', 'swapped-sensors']
TAGS_UNFILTERED, TAGS_FILTERED = ['A.PB.stop_nc', 'A.PB.estop_nc'], ['A.Sen.left', 'A.Sen.right']


def frac(x):
    return f'{x[0]}/{x[1]}'


def render(r):
    v, p = r['validity'], r['predictions']
    L = [f"# TR-2026-02 결과 — {r['round']}", '',
         '사전 등록 v0.3 §5 지표와 §3-2 예측을 정의 그대로 집계했다. 생성: `실행/TR-02_분석.py` (결정적 — 시각 값 없음).', '',
         '| 입력 | sha256 |', '| --- | --- |',
         f"| ledger.jsonl | `{r['ledger_sha256']}` |", f"| 연결 조건 어댑터 | `{r['adapter_sha256']}` |",
         f"| 분석 스크립트 · 표 생성부 | `{r['analysis_sha256']}` · `{r['render_sha256']}` |", '',
         '## 0. 무효 기준 재확인 (§6)', '',
         '| 항목 | 값 |', '| --- | --- |',
         f"| ledger 행 · 번호 | {v['ledger_rows']} · {v['distinct_no']} |",
         f"| rc 0 이 아닌 실행 | {len(v['rc_nonzero'])} |",
         f"| processes [PASS] 아닌 실행 | {len(v['processes_not_pass'])} |",
         f"| 어댑터 sha256 불일치(실행별 기록) | {len(v['adapter_sha_mismatch'])} · 파일 대조 {'[PASS]' if v['adapter_file_sha_ok'] else '[FAIL]'} |",
         f"| summary·어댑터 기록·ledger 해시 불일치 | {len(v['summary_hash_mismatch'])} |",
         f"| 조합 수 · 반복 1·2 trace_hash 불일치(무효) | {v['combos']} · {v['invalid_combos']} |",
         f"| 입력 복원 예외(분석 때 재실행, 지표 2 대상) | {sum(x['reconstruct_exceptions'] for x in r['metric2'].values())} |", '',
         '## 1. 예측 판정 (§3-2)', '',
         '| 예측 | 판정 | 틀린 곳 |', '| --- | --- | --- |']
    for k in ('P1', 'P2', 'P3', 'P4'):
        f = p[k]['failing']
        if not f:
            where = '-'
        elif k == 'P1':
            where = ', '.join(f)
        elif k == 'P2':
            x = f[0]; q = r['metric4'][x['ladder']]
            where = (f"{len(f)}개 래더. 대표 {x['ladder']} (실행 {x['runs'][0]}·{x['runs'][1]}): 첫 불일치 변화 #{q['first_mismatch_index']} "
                     f"이력 {q['first_mismatch']['history'] if q['first_mismatch'] else '-'} / 경계 {q['first_mismatch']['boundary'] if q['first_mismatch'] else '-'}, "
                     f"변화 수 {q['changes_history']}/{q['changes_boundary']}, 사건 +1 아님 {x['events_not_plus1'] or '-'}")
        else:
            x = f[0]
            where = (f"{len(f)}칸. 대표(실행 {x['first_run']}~) {x['tag']} 폭 {x['width']} ms {x['mode']}: "
                     f"예측 {x['predicted']}/10, 관측 {x['observed']['1']}/10 (반복 2 {x['observed']['2']}/10), 검출 위상 {x['detected_phases']}")
        L.append(f"| {k} | {p[k]['verdict']} | {where} |")
    m1 = r['metric1']
    L += ['', '## 2. 지표 1 — 판정 변화 (분모 20 미만, 분자/분모)', '',
          f"- 정답 래더 거짓 경보([PASS]→[FAIL]): **{frac(m1['false_alarm'])}**",
          f"- 음성 래더 놓침(검출→미검출): **{frac(m1['missed_negative'])}**", '',
          '| 래더 | 이력 복원 (실행·판정) | 경계 표본화 (실행·판정) |', '| --- | --- | --- |']
    for lad, d in m1['detail'].items():
        L.append(f"| {lad} | {d['history'][0]} {d['history'][1]} | {d['boundary'][0]} {d['boundary'][1]} |")
    L += ['', '## 3. 지표 2 — 놓친 BOOL 에지', '',
          '세는 규칙: 각 틱 행의 `I_start`(직전 입력)·`edges`·`I` 로 응답을 다시 만들고 고정 어댑터 `make_reconstruct(mode, None)` 로 '
          '스캔별 입력 5 개를 복원했다(원래 브리지 검사 포함). 표본 시각은 이력 복원 = 틱 시작 + 10·20·30·40·50 ms, 경계 표본화 = 틱 시작(5 스캔 모두), '
          '기준점 0 ms = 적재 때 입력. 공장 에지 시각 = 틱 시작 + round(t_s×1000). 이웃한 두 표본 사이(앞 표본 초과 ~ 뒤 표본 이하)의 공장 에지 수 c 중 '
          'c − (c mod 2) 개는 스캔 입력에 보이지 않으므로 그 절반을 「놓친 에지 쌍」으로 센다. 마지막 표본 뒤 에지(경계 표본화의 마지막 틱)는 쌍으로 세지 않고 '
          '「런 끝 미표본」으로 따로 적는다. 검산: 복원 값 = 그 표본 시각의 공장 값(불일치 수), 공장 에지 − 런 끝 − 놓친 에지 = 스캔 입력 전이 수.', '',
          '| 실행 | 태그 | 공장 에지 | 스캔 입력 전이 | 놓친 에지 쌍 | 런 끝 미표본 | 검산 |', '| --- | --- | --- | --- | --- | --- | --- |']
    for k, d in r['metric2'].items():
        for tag, x in sorted(d['per_tag'].items()):
            ok = x['identity_ok'] and d['reconstructed_value_mismatches'] == 0 and d['I_start_chain_breaks'] == 0 and d['reconstruct_exceptions'] == 0
            L.append(f"| {d['run']} {k} | {tag} | {x['factory_edges']} | {x['plc_transitions']} | {x['missed_pairs']} | {x['trailing_unsampled']} | {'[PASS]' if ok else '[FAIL]'} |")
    L += ['', '## 4. 지표 3 — 공장 사건 (반복 1)', '', '| 래더 | 사건 | 개수 이력/경계 (차) | 첫 발생 틱 이력/경계 (차) |', '| --- | --- | --- | --- |']
    for lad in LADDERS:
        if not r['metric3'][lad]:
            L.append(f'| {lad} | (사건 없음) | 0/0 (0) | - |')
        for n, x in r['metric3'][lad].items():
            L.append(f"| {lad} | {n} | {x['count_history']}/{x['count_boundary']} ({x['count_diff']:+d}) | "
                     f"{x['first_tick_history']}/{x['first_tick_boundary']} ({x['first_tick_diff'] if x['first_tick_diff'] is None else format(x['first_tick_diff'], '+d')}) |")
    L += ['', '## 5. 지표 4 — 적용 Q 변화 (반복 1, 틱은 0 부터)', '', '| 래더 | 실행 | 변화 수 이력/경계 | 태그·값 순서 같음 | 틱 차이 분포(경계 − 이력, 순서대로 짝) |', '| --- | --- | --- | --- | --- |']
    for lad in LADDERS:
        q = r['metric4'][lad]
        hist = ' · '.join(f'{k}: {c}' for k, c in q['tick_diff_hist'].items()) or '-'
        L.append(f"| {lad} | {q['runs'][0]}·{q['runs'][1]} | {q['changes_history']}/{q['changes_boundary']} | {'예' if q['same_tag_value_order'] else '아니오'} | {hist} |")
    L += ['', '## 6. 지표 5 — 짧은 펄스 검출 수/10 (반복 1 · 반복 2)', '',
          '검출 = 주입 틱 100~140(0 부터) 의 적용 Q 가 같은 조건·같은 반복 번호의 펄스 없는 기준 실행과 한 틱이라도 다름. '
          f"기준 실행 반복 1·2 창 Q 동일: 이력 {r['baseline_reps_equal']['history']} · 경계 {r['baseline_reps_equal']['boundary']}.", '',
          '| 입력 | 조건 | ' + ' | '.join(f'{w} ms' for w in WIDTHS) + ' |', '| --- | --- |' + ' --- |' * len(WIDTHS)]
    m5 = r['metric5']
    for tag in TAGS_UNFILTERED + TAGS_FILTERED:
        for mode in ('history', 'boundary'):
            cells = [m5[f'{tag}|{w}|{mode}']['count'] for w in WIDTHS]
            L.append(f'| {tag} | {mode} | ' + ' | '.join(f"{c['1']} · {c['2']}" for c in cells) + ' |')
    L += ['', '## 7. 공장 연결 시험 에지 위상 분포 (§4, 반복 1, 틱 시작 뒤 ms: 건수)', '', '| 실행 | 태그 | 분포 |', '| --- | --- | --- |']
    for k, d in r['edge_phase_ms'].items():
        for tag, h in d.items():
            L.append(f"| {k} | {tag} | {' · '.join(f'{a}: {b}' for a, b in h.items())} |")
    L += ['', '## 8. 기록만 — 사전 등록 지표 밖', '', '기준·짧은 펄스 실행의 summary 판정 집계(예측·지표 대상 아님): ' +
          ' · '.join(f'{k} {c}' for k, c in r['other_status_tally'].items()), '']
    return '\n'.join(L)
