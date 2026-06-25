"""Run 보존 정리(점검실패·취소 Run 일일 삭제) 단위 테스트."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.enums import RunStatus
from app.core.models import Run, RunModule
from app.core.status_labels import RUN_DAILY_PURGE_STATUSES
from app.orchestrator.run_service import RunService
from app.registry.loader import ModuleRegistry
from app.runner.artifact_manager import ArtifactManager
from app.scheduling.run_retention import RunRetentionScheduler, RunRetentionService
from app.storage.run_control_store import InMemoryRunControlStore
from app.storage.run_input_store import InMemoryRunInputStore
from app.storage.run_log_store import InMemoryRunLogStore
from app.storage.run_repository import InMemoryRunRepository


class _NoopGateway:
    pass


class _NoopEventBus:
    pass


class _NoopQueue:
    def submit(self, *_args, **_kwargs) -> None:
        pass


def _run(
    run_id: str,
    *,
    status: RunStatus,
    requested_at: datetime,
) -> Run:
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=status,
        requested_at=requested_at,
        modules=[
            RunModule(
                module_id="hom.login",
                name="login",
                group="auth",
                order=0,
                status=status,
            ),
        ],
        selected_module_ids=["hom.login"],
    )


def _service(tmp_path: Path) -> RunService:
    return RunService(
        registry=ModuleRegistry(),
        repository=InMemoryRunRepository(),
        log_store=InMemoryRunLogStore(),
        execution_gateway=_NoopGateway(),
        event_bus=_NoopEventBus(),
        control_store=InMemoryRunControlStore(),
        input_store=InMemoryRunInputStore(),
        run_queue=_NoopQueue(),
        artifact_manager=ArtifactManager(root_dir=tmp_path / "artifacts"),
    )


def test_purge_runs_deletes_only_error_and_cancelled_before_cutoff(tmp_path):
    service = _service(tmp_path)
    tz = ZoneInfo("Asia/Seoul")
    today_start = (
        datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    )
    yesterday = today_start - timedelta(hours=1)
    today = today_start + timedelta(hours=1)

    runs = [
        _run("run_passed_old", status=RunStatus.PASSED, requested_at=yesterday),
        _run("run_anomaly_old", status=RunStatus.ANOMALY, requested_at=yesterday),
        _run("run_error_old", status=RunStatus.ERROR, requested_at=yesterday),
        _run("run_cancel_old", status=RunStatus.CANCELLED, requested_at=yesterday),
        _run("run_error_today", status=RunStatus.ERROR, requested_at=today),
    ]
    for run in runs:
        asyncio.run(service._repository.create_run(run))

    deleted = asyncio.run(
        service.purge_runs(
            statuses=RUN_DAILY_PURGE_STATUSES,
            requested_before=today_start,
        )
    )

    assert set(deleted) == {"run_error_old", "run_cancel_old"}
    remaining = {run.run_id: run.status for run in asyncio.run(service._repository.list_runs())}
    assert remaining == {
        "run_passed_old": RunStatus.PASSED,
        "run_anomaly_old": RunStatus.ANOMALY,
        "run_error_today": RunStatus.ERROR,
    }
    assert not (tmp_path / "artifacts" / "run_error_old").exists()


def test_retention_scheduler_purge_now_uses_timezone_midnight(tmp_path):
    service = _service(tmp_path)
    tz = ZoneInfo("Asia/Seoul")
    today_start = (
        datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    )
    yesterday = today_start - timedelta(hours=2)

    asyncio.run(
        service._repository.create_run(
            _run("run_error_yesterday", status=RunStatus.ERROR, requested_at=yesterday),
        )
    )

    scheduler = RunRetentionScheduler(
        RunRetentionService(service),
        cron="0 3 * * *",
        timezone=tz,
        timezone_name="Asia/Seoul",
    )
    result = asyncio.run(scheduler.purge_now())

    assert result.deleted_run_ids == ["run_error_yesterday"]
    assert asyncio.run(service._repository.list_runs()) == []
