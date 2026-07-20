"""Suite 예약·트리거 경로 browser_mode 회귀 — 오염된 suite_systems 도 Suite 선택값을 따른다."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_registry, get_schedule_repository, get_schedule_service
from app.api.routes_schedules import router as schedules_router
from app.contexts.identity.dependencies import get_current_user
from app.contexts.identity.models import User
from app.contexts.run.application.planner import RunPlanner
from app.contexts.scheduling.infrastructure.schedule_repository import InMemoryScheduleRepository
from app.contexts.scheduling.scheduler import SchedulerService
from app.contexts.suite.application.service import SuiteService
from app.contexts.suite.infrastructure.in_memory_suite_control_store import (
    InMemorySuiteControlStore,
)
from app.contexts.suite.infrastructure.in_memory_suite_input_store import InMemorySuiteInputStore
from app.contexts.suite.infrastructure.sqlite_suite_write_repository import (
    SqliteSuiteWriteRepository,
)
from app.core.enums import RunStatus
from app.core.requests import CreateSuiteScheduleRequest
from app.core.run_models import Run, RunModule
from app.core.schedule_models import (
    SUITE_SCHEDULE_SYSTEM_CODE,
    SUITE_SCHEDULE_SYSTEM_NAME,
    Schedule,
)
from app.platform.eventing.bus import EventBus
from app.platform.eventing.support import SqliteDatabase, ensure_schema
from app.registry.loader import ModuleRegistry

ADMIN = User(
    user_id="admin_1",
    email="admin@test.local",
    name="Admin",
    role="admin",
    hashed_password="x",
    is_active=True,
    created_at=datetime.now(UTC),
)


def _hom_phone_input(*, browser_mode: str = "headed") -> dict[str, str]:
    return {
        "browser_mode": browser_mode,
        "auth_method": "phone",
        "name": "홍길동",
        "birthdate": "19900101",
        "gender": "male",
        "residency": "domestic",
        "carrier": "skt",
        "phone_number": "01012345678",
    }


class _CapturingRunCommands:
    """start_run 호출의 input_data 를 기록하는 RunCommandPort 대역."""

    def __init__(self, registry: ModuleRegistry) -> None:
        self._registry = registry
        self._planner = RunPlanner()
        self.start_run_calls: list[dict[str, Any]] = []
        self._runs: dict[str, Run] = {}

    def get_system(self, system_code: str):
        return self._registry.get_system(system_code)

    def validate_run_request(self, system_code, input_data=None, selected_module_ids=None):
        system = self._registry.get_system(system_code)
        return self._planner.prepare(system, input_data, selected_module_ids)

    async def get_run(self, run_id: str) -> Run:
        return self._runs[run_id]

    async def start_run(
        self,
        system_code: str,
        input_data: dict[str, str] | None = None,
        selected_module_ids: list[str] | None = None,
        **kwargs: Any,
    ) -> Run:
        self.start_run_calls.append(
            {
                "system_code": system_code,
                "input_data": dict(input_data or {}),
                "kwargs": dict(kwargs),
            }
        )
        run_id = f"run_capture_{len(self.start_run_calls)}"
        run = Run(
            run_id=run_id,
            system_code=system_code,
            system_name=self._registry.get_system(system_code).name,
            status=RunStatus.PENDING,
            requested_at=datetime.now(UTC),
            modules=[
                RunModule(
                    module_id="hom.main.access",
                    name="access",
                    group="access",
                    order=0,
                )
            ],
            selected_module_ids=["hom.main.access"],
            **{key: value for key, value in kwargs.items() if key in Run.model_fields},
        )
        self._runs[run_id] = run
        return run


class _NoopSuiteRealtime:
    async def publish(self, event) -> None:  # noqa: ANN001
        return None

    async def subscribe(self, suite_id: str):  # noqa: ARG002
        return asyncio.Queue()

    async def unsubscribe(self, suite_id: str, queue) -> None:  # noqa: ANN001, ARG002
        return None


class _EmptySuiteSummaryQuery:
    async def list_summaries(self, *args, **kwargs):  # noqa: ANN001, ANN002
        return []


class _EmptyRunQueries:
    async def list_schedule_runs(self, schedule_id: str, limit: int = 30):  # noqa: ARG002
        return []

    async def list_schedule_tagged_runs(self):
        return []

    async def last_finished_at_by_system(self) -> dict:
        return {}


async def _build_stack(tmp_path: Path) -> dict[str, Any]:
    registry = ModuleRegistry()
    run_commands = _CapturingRunCommands(registry)
    db = SqliteDatabase(tmp_path / "schedule_suite_browser_mode.db")
    await ensure_schema(db)
    write_repo = SqliteSuiteWriteRepository(db)
    event_bus = EventBus()
    suite_service = SuiteService(
        registry=registry,
        run_commands=run_commands,
        write_repo=write_repo,
        read_repo=write_repo,
        realtime=_NoopSuiteRealtime(),
        event_bus=event_bus,
        cancel_store=InMemorySuiteControlStore(),
        input_store=InMemorySuiteInputStore(),
        summary_query=_EmptySuiteSummaryQuery(),
    )
    suite_service.register(event_bus)
    schedule_repo = InMemoryScheduleRepository()
    scheduler = SchedulerService(
        run_commands=run_commands,
        suite_service=suite_service,
        repository=schedule_repo,
        run_queries=_EmptyRunQueries(),
    )
    return {
        "registry": registry,
        "run_commands": run_commands,
        "suite_service": suite_service,
        "schedule_repo": schedule_repo,
        "scheduler": scheduler,
    }


def _legacy_suite_schedule(
    *, browser_mode: str, suite_systems: dict[str, dict[str, str]]
) -> Schedule:
    return Schedule(
        schedule_id="sch_legacy_suite",
        schedule_kind="suite",
        system_code=SUITE_SCHEDULE_SYSTEM_CODE,
        system_name=SUITE_SCHEDULE_SYSTEM_NAME,
        name="레거시 Suite 예약",
        cron="0 7 * * 1-5",
        timezone="Asia/Seoul",
        browser_mode=browser_mode,
        suite_systems=suite_systems,
        selected_system_codes=["hom"],
        step_total=1,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def stack(tmp_path: Path) -> dict[str, Any]:
    return asyncio.run(_build_stack(tmp_path))


async def test_create_suite_schedule_strips_browser_mode_from_suite_systems(
    stack: dict[str, Any],
) -> None:
    scheduler: SchedulerService = stack["scheduler"]
    polluted = {"hom": _hom_phone_input(browser_mode="headed")}

    schedule = await scheduler.create_suite_schedule(
        CreateSuiteScheduleRequest(
            cron="0 7 * * 1-5",
            name="아침 전체 점검",
            browser_mode="headless",
            systems=polluted,
            selected_system_codes=["hom"],
        )
    )

    assert schedule.browser_mode == "headless"
    assert schedule.suite_systems is not None
    assert "browser_mode" not in schedule.suite_systems["hom"]
    assert schedule.suite_systems["hom"]["phone_number"] == "01012345678"


async def test_trigger_suite_uses_schedule_browser_mode_despite_polluted_suite_systems(
    stack: dict[str, Any],
) -> None:
    scheduler: SchedulerService = stack["scheduler"]
    run_commands: _CapturingRunCommands = stack["run_commands"]
    schedule_repo: InMemoryScheduleRepository = stack["schedule_repo"]

    schedule = _legacy_suite_schedule(
        browser_mode="headless",
        suite_systems={"hom": _hom_phone_input(browser_mode="headed")},
    )
    await schedule_repo.save(schedule)

    await scheduler._trigger_suite(schedule)

    assert len(run_commands.start_run_calls) == 1
    call = run_commands.start_run_calls[0]
    assert call["system_code"] == "hom"
    assert call["input_data"]["browser_mode"] == "headless"
    assert call["kwargs"].get("triggered_by") == "suite"
    assert call["kwargs"].get("suite_id")


async def test_run_now_suite_schedule_passes_headless_to_start_run(stack: dict[str, Any]) -> None:
    scheduler: SchedulerService = stack["scheduler"]
    run_commands: _CapturingRunCommands = stack["run_commands"]

    schedule = await scheduler.create_suite_schedule(
        CreateSuiteScheduleRequest(
            cron="0 8 * * *",
            browser_mode="headless",
            systems={"hom": _hom_phone_input(browser_mode="headed")},
            selected_system_codes=["hom"],
        )
    )

    await scheduler.run_now(schedule.schedule_id)

    assert run_commands.start_run_calls
    assert run_commands.start_run_calls[0]["input_data"]["browser_mode"] == "headless"


def test_api_create_suite_schedule_and_run_now_preserves_browser_mode(
    stack: dict[str, Any],
) -> None:
    run_commands: _CapturingRunCommands = stack["run_commands"]
    scheduler: SchedulerService = stack["scheduler"]
    schedule_repo: InMemoryScheduleRepository = stack["schedule_repo"]

    app = FastAPI()
    app.include_router(schedules_router)
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    app.dependency_overrides[get_schedule_service] = lambda: scheduler
    app.dependency_overrides[get_schedule_repository] = lambda: schedule_repo
    app.dependency_overrides[get_registry] = lambda: stack["registry"]

    with TestClient(app) as client:
        create_response = client.post(
            "/api/schedules/suites",
            json={
                "cron": "0 9 * * *",
                "name": "API Suite 예약",
                "browser_mode": "headless",
                "systems": {"hom": _hom_phone_input(browser_mode="headed")},
                "selected_system_codes": ["hom"],
            },
        )
        assert create_response.status_code == 200
        schedule_id = create_response.json()["schedule_id"]

        stored = asyncio.run(schedule_repo.get(schedule_id))
        assert stored.browser_mode == "headless"
        assert "browser_mode" not in (stored.suite_systems or {})["hom"]

        run_now_response = client.post(f"/api/schedules/{schedule_id}/run-now")
        assert run_now_response.status_code == 200

    assert run_commands.start_run_calls
    assert run_commands.start_run_calls[-1]["input_data"]["browser_mode"] == "headless"
