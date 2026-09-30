# TR-2026-02 리드 독립 검산 — tr02-official-1

- 스크립트: `TR-02_리드독립검산.py` sha256 `0c20628e02a017fda060a41a303b1d8ba36d2db8e2a962ecd0f3d93211eecfe0` — 분석 스크립트를 쓰지 않고 trace·summary 를 직접 읽음. 두 번 실행 출력 동일.
- 결과: P1~P4 분석 결과와 일치. 펄스·기준 804 실행 요약 [FAIL] 내역 = 왕복 2 (524: 기준 4·미검출 펄스 520) + 왕복 1 (280: 정지·비상정지 펄스 검출로 래더 정지), 공장 사건 0.

```
# P1·P2 — 공장 연결 반복 1
correct: 판정 [PASS]/[PASS] · 사건 같음 True · Q 변화 12/12 · 순서 같음 True · 틱 차이 [1]
late-reverse: 판정 [FAIL]/[FAIL] · 사건 같음 True · Q 변화 3/3 · 순서 같음 True · 틱 차이 [1]
swapped-sensors: 판정 [FAIL]/[FAIL] · 사건 같음 True · Q 변화 1/1 · 순서 같음 True · 틱 차이 [1]

# P3·P4 — 짧은 펄스 검출 수(위상 10 점 중), 폭 5·15·25·35·45 ms
A.PB.stop_nc boundary: [1, 3, 5, 7, 9]
A.PB.stop_nc history: [5, 10, 10, 10, 10]
A.PB.estop_nc boundary: [1, 3, 5, 7, 9]
A.PB.estop_nc history: [5, 10, 10, 10, 10]
A.Sen.left boundary: [0, 0, 0, 0, 0]
A.Sen.left history: [0, 0, 0, 0, 0]
A.Sen.right boundary: [0, 0, 0, 0, 0]
A.Sen.right history: [0, 0, 0, 0, 0]

# 기록만 — 펄스·기준 실행 요약 판정 내역(반복 1·2 전부)
baseline · 판정 [FAIL] · 왕복 2 · 펄스 미검출 · 공장 사건 0 → 4 실행
pulse · 판정 [FAIL] · 왕복 1 · 펄스 검출 · 공장 사건 0 → 280 실행
pulse · 판정 [FAIL] · 왕복 2 · 펄스 미검출 · 공장 사건 0 → 520 실행
합계 804
```
