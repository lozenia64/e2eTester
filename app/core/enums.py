from __future__ import annotations

from enum import StrEnum


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
