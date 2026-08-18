from __future__ import annotations

from enum import IntEnum, StrEnum


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_INPUT = "WAITING_INPUT"
    PASSED = "PASSED"
    ANOMALY = "ANOMALY"
    ERROR = "ERROR"
    FAILED = "FAILED"  # 레거시 SQLite 호환; 신규 기록에는 사용하지 않음
    CANCELLED = "CANCELLED"


class SuiteStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_INPUT = "WAITING_INPUT"
    PASSED = "PASSED"
    ANOMALY = "ANOMALY"
    ERROR = "ERROR"
    FAILED = "FAILED"  # 레거시 호환
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class ModuleStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_INPUT = "WAITING_INPUT"
    PASSED = "PASSED"
    ANOMALY = "ANOMALY"
    ERROR = "ERROR"
    FAILED = "FAILED"  # 레거시 호환
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class AnomalyState(StrEnum):
    """이상징후 인박스에서 한 이상건(ANOMALY/ERROR 모듈)의 **처리 진행 상태**.

    점검의 본질은 '발견'이 아니라 '조치'이므로, Run 이력과 별개로 이상건마다 이 상태를
    미확인→확인함→처리완료 로 끌고 간다(``AnomalyHandling`` 에 영속). 스토어에 행이 없는
    이상건은 기본 ``UNRESOLVED`` 로 간주한다.
    """

    UNRESOLVED = "UNRESOLVED"  # 미확인
    ACKNOWLEDGED = "ACKNOWLEDGED"  # 확인함
    RESOLVED = "RESOLVED"  # 처리완료


class FailureSignal(StrEnum):
    """모듈 실패의 성격. 복구 등급(RecoveryTier) 선택의 유일한 입력이다.

    분류는 실행 평면(``app/runner/failure_signal.py``)에서만 수행하고, 도메인은 이 enum 만
    관찰한다. 도메인이 예외 메시지 문자열을 들여다보는 일(``StepOutcome`` 도입으로 걷어낸
    안티패턴)이 재발하지 않도록 하는 경계다.
    """

    TIMEOUT = "TIMEOUT"  # 대기 시간 초과
    SELECTOR_MISS = "SELECTOR_MISS"  # 요소를 찾지 못함
    NAVIGATION = "NAVIGATION"  # 페이지 이동·로드 실패
    SESSION_LOST = "SESSION_LOST"  # 세션·컨텍스트 소실, 로그인 만료
    DIALOG = "DIALOG"  # 예기치 않은 다이얼로그·팝업
    SITE = "SITE"  # 사이트 이상(page object 의 의도적 RuntimeError) — 자동 복구 대상 아님
    UNKNOWN = "UNKNOWN"  # 미분류


class RecoveryTier(IntEnum):
    """모듈 재시도 전에 **세션을 어디까지 되감을지**. 값의 크기가 곧 비용·파괴력이다.

    ``IntEnum`` 인 이유: 등급 상승(escalation)을 산술로 표현하기 위함이다.
    """

    RETRY_IN_PLACE = 0  # 되감기 없음 — backoff 후 같은 페이지에서 재시도(현행 동작)
    RESET_TO_MODULE_ENTRY = 1  # 다이얼로그 정리 후 모듈 진입 URL 로 재이동
    # 설계 의도는 "세션 폐기·재개설 후 로그인 모듈부터 주행"이지만, 현행 구현
    # (worker/session_server.py::_reopen_session)은 런타임 재구축까지만 한다 — 로그인 재주행은
    # 아직 없다(SPEC-RUN-006 FR-004 '현행 구현 한계'). 이름은 목표 상태를 가리킨다.
    REPLAY_FROM_LOGIN = 2
