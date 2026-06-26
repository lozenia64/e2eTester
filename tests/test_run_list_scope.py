"""list_run_summaries scope(today/before_today) 필터 단위 테스트."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.enums import RunStatus
from app.core.models import Run, RunModule
from app.orchestrator.run_service import RunService
from app.registry.loader import ModuleRegistry
from app.runner.artifact_manager import ArtifactManager
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


def test_list_run_summaries_scope_today_and_before_today(tmp_path):
    asyncio.run(_assert_scope_filters(tmp_path))


async def _assert_scope_filters(tmp_path: Path) -> None:
    service = _service(tmp_path)
    tz = ZoneInfo("Asia/Seoul")
    today_start = (
        datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    )
    yesterday = today_start - timedelta(hours=1)
    today_afternoon = today_start + timedelta(hours=10)

    runs = [
        _run("run_yesterday_passed", status=RunStatus.PASSED, requested_at=yesterday),
        _run("run_today_passed", status=RunStatus.PASSED, requested_at=today_afternoon),
        _run("run_yesterday_waiting", status=RunStatus.WAITING_INPUT, requested_at=yesterday),
    ]
    for run in runs:
        await service._repository.save_run(run)

    today_ids = {item["run_id"] for item in await service.list_run_summaries(scope="today")}
    assert today_ids == {"run_today_passed", "run_yesterday_waiting"}

    before_ids = {item["run_id"] for item in await service.list_run_summaries(scope="before_today")}
    assert before_ids == {"run_yesterday_passed"}

    all_ids = {item["run_id"] for item in await service.list_run_summaries()}
    assert all_ids == {"run_today_passed", "run_yesterday_passed", "run_yesterday_waiting"}


def test_scope_today_always_includes_active_runs_even_at_limit(tmp_path):
    asyncio.run(_assert_active_runs_not_dropped_at_limit(tmp_path))


async def _assert_active_runs_not_dropped_at_limit(tmp_path: Path) -> None:
    service = _service(tmp_path)
    tz = ZoneInfo("Asia/Seoul")
    today_start = (
        datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    )
    yesterday = today_start - timedelta(hours=1)

    runs = [
        _run("run_yesterday_waiting", status=RunStatus.WAITING_INPUT, requested_at=yesterday),
    ]
    for index in range(5):
        runs.append(
            _run(
                f"run_today_{index}",
                status=RunStatus.PASSED,
                requested_at=today_start + timedelta(hours=index + 1),
            )
        )
    for run in runs:
        await service._repository.save_run(run)

    today_ids = {
        item["run_id"] for item in await service.list_run_summaries(scope="today", limit=3)
    }
    assert "run_yesterday_waiting" in today_ids
    assert len(today_ids) == 3
