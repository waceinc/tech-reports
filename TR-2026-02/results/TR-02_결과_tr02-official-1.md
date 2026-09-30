# TR-2026-02 결과 — tr02-official-1

사전 등록 v0.3 §5 지표와 §3-2 예측을 정의 그대로 집계했다. 생성: `실행/TR-02_분석.py` (결정적 — 시각 값 없음).

| 입력 | sha256 |
| --- | --- |
| ledger.jsonl | `80de3ea71eb82f76388a47f03122830e97eee0b0adcfd0d4a1ae7d5496ea79e6` |
| 연결 조건 어댑터 | `f5241b5f5d5286ff6366bdff33da8ec599e343d67ba6fd1ebaf129f1a7d10c40` |
| 분석 스크립트 · 표 생성부 | `b1ca7dcda0fe502a0c4149f47805e553e1c33777f3c25c808ea06b5ea3ca148b` · `82a431311eb6f0eb241ac057de3fcdf369d501a6ae1ea8f3d9d1b28ed02dd6fd` |

## 0. 무효 기준 재확인 (§6)

| 항목 | 값 |
| --- | --- |
| ledger 행 · 번호 | 816 · 816 |
| rc 0 이 아닌 실행 | 0 |
| processes [PASS] 아닌 실행 | 0 |
| 어댑터 sha256 불일치(실행별 기록) | 0 · 파일 대조 [PASS] |
| summary·어댑터 기록·ledger 해시 불일치 | 0 |
| 조합 수 · 반복 1·2 trace_hash 불일치(무효) | 408 · 0 |
| 입력 복원 예외(분석 때 재실행, 지표 2 대상) | 0 |

## 1. 예측 판정 (§3-2)

| 예측 | 판정 | 틀린 곳 |
| --- | --- | --- |
| P1 | [맞음] | - |
| P2 | [맞음] | - |
| P3 | [맞음] | - |
| P4 | [맞음] | - |

## 2. 지표 1 — 판정 변화 (분모 20 미만, 분자/분모)

- 정답 래더 거짓 경보([PASS]→[FAIL]): **0/1**
- 음성 래더 놓침(검출→미검출): **0/2**

| 래더 | 이력 복원 (실행·판정) | 경계 표본화 (실행·판정) |
| --- | --- | --- |
| correct | 1 [PASS] | 3 [PASS] |
| late-reverse | 5 [FAIL] | 7 [FAIL] |
| swapped-sensors | 9 [FAIL] | 11 [FAIL] |

## 3. 지표 2 — 놓친 BOOL 에지

세는 규칙: 각 틱 행의 `I_start`(직전 입력)·`edges`·`I` 로 응답을 다시 만들고 고정 어댑터 `make_reconstruct(mode, None)` 로 스캔별 입력 5 개를 복원했다(원래 브리지 검사 포함). 표본 시각은 이력 복원 = 틱 시작 + 10·20·30·40·50 ms, 경계 표본화 = 틱 시작(5 스캔 모두), 기준점 0 ms = 적재 때 입력. 공장 에지 시각 = 틱 시작 + round(t_s×1000). 이웃한 두 표본 사이(앞 표본 초과 ~ 뒤 표본 이하)의 공장 에지 수 c 중 c − (c mod 2) 개는 스캔 입력에 보이지 않으므로 그 절반을 「놓친 에지 쌍」으로 센다. 마지막 표본 뒤 에지(경계 표본화의 마지막 틱)는 쌍으로 세지 않고 「런 끝 미표본」으로 따로 적는다. 검산: 복원 값 = 그 표본 시각의 공장 값(불일치 수), 공장 에지 − 런 끝 − 놓친 에지 = 스캔 입력 전이 수.

| 실행 | 태그 | 공장 에지 | 스캔 입력 전이 | 놓친 에지 쌍 | 런 끝 미표본 | 검산 |
| --- | --- | --- | --- | --- | --- | --- |
| 3 correct/boundary | A.PB.estop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 3 correct/boundary | A.PB.start | 6 | 2 | 2 | 0 | [PASS] |
| 3 correct/boundary | A.PB.stop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 3 correct/boundary | A.Sen.left | 5 | 5 | 0 | 0 | [PASS] |
| 3 correct/boundary | A.Sen.right | 6 | 6 | 0 | 0 | [PASS] |
| 1 correct/history | A.PB.estop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 1 correct/history | A.PB.start | 6 | 2 | 2 | 0 | [PASS] |
| 1 correct/history | A.PB.stop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 1 correct/history | A.Sen.left | 5 | 5 | 0 | 0 | [PASS] |
| 1 correct/history | A.Sen.right | 6 | 6 | 0 | 0 | [PASS] |
| 7 late-reverse/boundary | A.PB.estop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 7 late-reverse/boundary | A.PB.start | 6 | 2 | 2 | 0 | [PASS] |
| 7 late-reverse/boundary | A.PB.stop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 7 late-reverse/boundary | A.Sen.left | 0 | 0 | 0 | 0 | [PASS] |
| 7 late-reverse/boundary | A.Sen.right | 2 | 2 | 0 | 0 | [PASS] |
| 5 late-reverse/history | A.PB.estop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 5 late-reverse/history | A.PB.start | 6 | 2 | 2 | 0 | [PASS] |
| 5 late-reverse/history | A.PB.stop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 5 late-reverse/history | A.Sen.left | 0 | 0 | 0 | 0 | [PASS] |
| 5 late-reverse/history | A.Sen.right | 2 | 2 | 0 | 0 | [PASS] |
| 11 swapped-sensors/boundary | A.PB.estop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 11 swapped-sensors/boundary | A.PB.start | 6 | 2 | 2 | 0 | [PASS] |
| 11 swapped-sensors/boundary | A.PB.stop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 11 swapped-sensors/boundary | A.Sen.left | 0 | 0 | 0 | 0 | [PASS] |
| 11 swapped-sensors/boundary | A.Sen.right | 2 | 2 | 0 | 0 | [PASS] |
| 9 swapped-sensors/history | A.PB.estop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 9 swapped-sensors/history | A.PB.start | 6 | 2 | 2 | 0 | [PASS] |
| 9 swapped-sensors/history | A.PB.stop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 9 swapped-sensors/history | A.Sen.left | 0 | 0 | 0 | 0 | [PASS] |
| 9 swapped-sensors/history | A.Sen.right | 2 | 2 | 0 | 0 | [PASS] |
| 15 baseline/boundary | A.PB.estop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 15 baseline/boundary | A.PB.start | 6 | 2 | 2 | 0 | [PASS] |
| 15 baseline/boundary | A.PB.stop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 15 baseline/boundary | A.Sen.left | 4 | 4 | 0 | 0 | [PASS] |
| 15 baseline/boundary | A.Sen.right | 4 | 4 | 0 | 0 | [PASS] |
| 13 baseline/history | A.PB.estop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 13 baseline/history | A.PB.start | 6 | 2 | 2 | 0 | [PASS] |
| 13 baseline/history | A.PB.stop_nc | 0 | 0 | 0 | 0 | [PASS] |
| 13 baseline/history | A.Sen.left | 4 | 4 | 0 | 0 | [PASS] |
| 13 baseline/history | A.Sen.right | 4 | 4 | 0 | 0 | [PASS] |

## 4. 지표 3 — 공장 사건 (반복 1)

| 래더 | 사건 | 개수 이력/경계 (차) | 첫 발생 틱 이력/경계 (차) |
| --- | --- | --- | --- |
| correct | (사건 없음) | 0/0 (0) | - |
| late-reverse | PART_DROP | 1/1 (+0) | 37/38 (+1) |
| swapped-sensors | PART_DROP | 1/1 (+0) | 37/38 (+1) |

## 5. 지표 4 — 적용 Q 변화 (반복 1, 틱은 0 부터)

| 래더 | 실행 | 변화 수 이력/경계 | 태그·값 순서 같음 | 틱 차이 분포(경계 − 이력, 순서대로 짝) |
| --- | --- | --- | --- | --- |
| correct | 1·3 | 12/12 | 예 | 1: 12 |
| late-reverse | 5·7 | 3/3 | 예 | 1: 3 |
| swapped-sensors | 9·11 | 1/1 | 예 | 1: 1 |

## 6. 지표 5 — 짧은 펄스 검출 수/10 (반복 1 · 반복 2)

검출 = 주입 틱 100~140(0 부터) 의 적용 Q 가 같은 조건·같은 반복 번호의 펄스 없는 기준 실행과 한 틱이라도 다름. 기준 실행 반복 1·2 창 Q 동일: 이력 True · 경계 True.

| 입력 | 조건 | 5 ms | 15 ms | 25 ms | 35 ms | 45 ms |
| --- | --- | --- | --- | --- | --- | --- |
| A.PB.stop_nc | history | 5 · 5 | 10 · 10 | 10 · 10 | 10 · 10 | 10 · 10 |
| A.PB.stop_nc | boundary | 1 · 1 | 3 · 3 | 5 · 5 | 7 · 7 | 9 · 9 |
| A.PB.estop_nc | history | 5 · 5 | 10 · 10 | 10 · 10 | 10 · 10 | 10 · 10 |
| A.PB.estop_nc | boundary | 1 · 1 | 3 · 3 | 5 · 5 | 7 · 7 | 9 · 9 |
| A.Sen.left | history | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 |
| A.Sen.left | boundary | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 |
| A.Sen.right | history | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 |
| A.Sen.right | boundary | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 | 0 · 0 |

## 7. 공장 연결 시험 에지 위상 분포 (§4, 반복 1, 틱 시작 뒤 ms: 건수)

| 실행 | 태그 | 분포 |
| --- | --- | --- |
| correct/boundary | A.PB.start | 1: 2 · 2: 2 · 3: 2 |
| correct/boundary | A.Sen.left | 22: 2 · 32: 3 |
| correct/boundary | A.Sen.right | 22: 3 · 32: 3 |
| correct/history | A.PB.start | 1: 2 · 2: 2 · 3: 2 |
| correct/history | A.Sen.left | 22: 2 · 32: 3 |
| correct/history | A.Sen.right | 22: 3 · 32: 3 |
| late-reverse/boundary | A.PB.start | 1: 2 · 2: 2 · 3: 2 |
| late-reverse/boundary | A.Sen.right | 5: 1 · 32: 1 |
| late-reverse/history | A.PB.start | 1: 2 · 2: 2 · 3: 2 |
| late-reverse/history | A.Sen.right | 5: 1 · 32: 1 |
| swapped-sensors/boundary | A.PB.start | 1: 2 · 2: 2 · 3: 2 |
| swapped-sensors/boundary | A.Sen.right | 5: 1 · 32: 1 |
| swapped-sensors/history | A.PB.start | 1: 2 · 2: 2 · 3: 2 |
| swapped-sensors/history | A.Sen.right | 5: 1 · 32: 1 |

## 8. 기록만 — 사전 등록 지표 밖

기준·짧은 펄스 실행의 summary 판정 집계(예측·지표 대상 아님): baseline/boundary/[FAIL] 2 · baseline/history/[FAIL] 2 · pulse/boundary/[FAIL] 400 · pulse/history/[FAIL] 400
