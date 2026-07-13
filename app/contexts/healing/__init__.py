"""자가 치유 센터(Self-Healing Center) — 셀렉터 자가 치유 도메인 패키지.

무인 실행 중 특정 스텝의 셀렉터가 깨지면, 라이브 DOM 을 스캔해 대체 셀렉터 후보를
점수화(신뢰도)하고, 정책(시스템별 auto-heal on/off + 신뢰도 임계치)이 허가하면 런타임
한정으로 대체 셀렉터를 적용해 스텝을 1회 재시도한다. 모든 시도는 치유 이벤트로 기록되고,
성공한 치유는 실제 소스 반영을 위한 **승인 대기 패치**(before/after diff)로 제안된다
(런타임 복구는 일회성 — 코드 반영은 사람 승인 게이트를 통과해야 한다).

순수 로직(파싱·스코어링·집계·정적 스캔)과 I/O(브라우저·SQLite·파일)는 다른 도메인과
같은 규칙으로 분리한다: 순수 모듈은 ``selector_healer``/``metrics``/``durability``/
``patch_builder``, I/O 는 ``engine``(브라우저)과 ``app/orchestrator/healing_service.py``
(저장·파일)가 담당한다.
"""
