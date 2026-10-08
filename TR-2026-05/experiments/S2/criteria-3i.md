# S2-3 3i·4a 사전 판정 기준

등록: 2026-09-29, 연결 실행 전 고정. 조건: plc-simulator 실제 10ms 엔진, 지정 extctl 3i/4a 모형, 실물 대조 0.

- F1: 기존 부록 A 주소 보존, bindings+extensions 전량, X22/X23 및 포장 INT 선언. A 1000틱 3왕복, B 시드1/2/3 5000틱 20개, pack 시드1/2/3 6000틱 60개. 각 ID class/route와 공급 고정 결과 일치. 정상 물리 위험 사건·제어 판정 위반 0. 포장 PART_PACKED/REJECT_COLLECTED는 정상 생산 사건으로 별도 집계한다.
- 안전·재기동: 커튼 감지 스캔 구동 Q OFF, B 정지 지연 ≤0.265s. 이탈·리셋만으로 기동 금지. 불확실 추적은 잠김→리셋 뗌→격리→원점 홀드(후진/마무리밀기/재후진)→격리 배출→17초 이상 및 센서3초 비움→초기화→별도 기동. 브레이크·압력·검사 준비·도착 확인·배출 만재 인터록 검사.
- 결정성: 각 셀 정상 시드(분류/포장 1,2,3)의 독립2회 틱 해시 전량 일치. 참조는 같은 입력의 매스캔 Q 및 폐루프 틱별 Q 비교, 차이는 최초 위치·이유·범위 기록. 차이0을 전제하거나 보정하지 않는다.
- 음성8종: A swapped-sensors/late-reverse → PART_DROP; B push-timing-off → 오분류/밀기 사건, ignore-curtain → 감지 스캔 PLC_CURTAIN_IGNORED, no-sort-check → 유량저하 고장에서 도착 누락을 잠그지 않은 SORT_CHECK_MISSING; pack no-handshake → HANDSHAKE_TIMEOUT 또는 완료 ACK 누락, ignore-box-full → CONTAINER_FULL_IGNORED 또는 만재 중 로봇 요청, ignore-reject-full → CONTAINER_FULL_IGNORED 또는 만재/예약4개 중 배출. 공정 [FAIL]과 음성 검출 [PASS] 분리.
- F2: 브리지가 실행하는 같은 엔진에서 스캔 번호·I/Q/M·FB 현재/설정값 및 렁 통전 관찰. NO/NC/OUT/SET/RESET/박스·주석·태그/부록 A 주소·현재값·스캔/공장시간·렁 이동/확대·I/O 요약·최근 신호→물체→동작. 쓰기/강제 API 없음. 엔진 표본과 DOM/표시 데이터 매스캔 자동 대조.
- F3: run-gui.sh 기존 인자/외부 HMI 유지, 전용 독립 창 추가, 공장틱 마지막 스캔 표시. 신호 변화 highlight, 래더 클릭 focus, 실제 3D 선택 sequence→해당 렁 이동. --no-ladder 대조는 같은 입력·프로그램·실행 파일에서 기존 Vision 창과 모든 틱 해시 동일. 구3f 증거의 실행 파일/모형 변경에 따른 차이는 별도 보고.
- F4: 모든 구현 수정 완료 후 전체 시드·결정성·최종 캡처 묶음을 한 번 수행한다. 정상 분류·커튼 정지·잠김·복귀 캡처 직접 열어 통전색/수치 확인. 자체 시험 통과, 결과 문서 갱신. 실패 증거 보존, 수정 후 해당 범위 재검.
- vendor/외부 레포/git 쓰기 없음, 원시 trace/monitor JSONL ignore, 모든 출력/캐시 작업 폴더 내부. 직접 띄운 프로세스만 종료·회수. GX Simulator2·실물·다른 플랫폼 [NOT_RUN].
