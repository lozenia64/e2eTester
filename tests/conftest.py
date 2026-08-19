"""SDD Spec ↔ pytest 추적성 (conftest)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contexts.insights.contracts.query_rows import DailyRunSummaryRow, DailyStatusRow
from app.core.enums import ModuleStatus, RunStatus


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "spec(spec_id, ac_id): SDD Spec 수용 기준과 테스트 연결 (예: SPEC-RUN-001, AC-002)",
    )


def make_status_row(
    *,
    system_code: str,
    module_id: str,
    last_status: ModuleStatus,
    day_key: str = "2026-08-15",
    last_run_id: str | None = "run-1",
    duration_ms: int | None = 1000,
    recovered: bool = False,
) -> DailyStatusRow:
    """일간 프로젝션 행 픽스처. Run 객체 대신 이걸 쓴다(프로덕션 경로와 동일)."""
    return DailyStatusRow(
        day_key=day_key,
        system_code=system_code,
        module_id=module_id,
        last_status=last_status,
        last_run_id=last_run_id,
        duration_ms=duration_ms,
        updated_at=datetime(2026, 8, 15, 9, 0, tzinfo=UTC),
        recovered=recovered,
    )


def make_run_summary_row(
    *,
    system_code: str,
    run_id: str = "run-1",
    status: RunStatus = RunStatus.PASSED,
    triggered_by: str = "tester",
    requested_at: datetime | None = None,
) -> DailyRunSummaryRow:
    return DailyRunSummaryRow(
        run_id=run_id,
        system_code=system_code,
        status=status,
        requested_at=requested_at or datetime(2026, 8, 15, 9, 0, tzinfo=UTC),
        triggered_by=triggered_by,
    )
