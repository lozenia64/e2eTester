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
