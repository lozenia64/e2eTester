"""모바일 즉시 점검 트리거(예약별 비밀 토큰) 단위 테스트.

브라우저/HTTP 서버 없이 ① 토큰 발급·지연 발급(backfill) ② 토큰 조회(find_by_trigger_token)
③ trigger_now 의 멱등 가드(진행 중이면 이중 발사 금지) ④ OTP 전달 라우팅(Run/Suite)
⑤ 라우트 핸들러의 404 매핑을 검증한다. test_otp_inbound.py 와 같은 패턴으로
SchedulerService 에 페이크 저장소/서비스를 주입해 실행한다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes_trigger import fire_trigger, submit_trigger_otp, trigger_status
from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.models import CreateScheduleRequest, Schedule, SubmitOtpRequest
from app.scheduling.scheduler import SchedulerService


# --------------------------------------------------------------------------- #
# 페이크 협력자
# --------------------------------------------------------------------------- #
class _FakeScheduleRepo:
    def __init__(self, schedules: list[Schedule] | None = None) -> None:
        self._items: dict[str, Schedule] = {s.schedule_id: s for s in (schedules or [])}
        self.save_calls = 0

    async def list(self) -> list[Schedule]:
        return list(self._items.values())

    async def get(self, schedule_id: str) -> Schedule:
        return self._items[schedule_id]

    async def save(self, schedule: Schedule) -> None:
        self.save_calls += 1
        self._items[schedule.schedule_id] = schedule

    async def delete(self, schedule_id: str) -> None:
        del self._items[schedule_id]


def _module(status: ModuleStatus) -> SimpleNamespace:
    return SimpleNamespace(status=status)


def _fake_run(run_id: str, status: RunStatus, modules=None) -> SimpleNamespace:
    return SimpleNamespace(
        run_id=run_id,
        status=status,
        modules=modules if modules is not None else [],
        awaiting_input_prompt=None,
    )


class _FakeRunService:
    def __init__(self, runs: dict[str, SimpleNamespace] | None = None) -> None:
        self.runs = runs or {}
        self.started: list[str] = []
        self.otp_calls: list[tuple[str, str]] = []

    def get_system(self, system_code: str) -> SimpleNamespace:
        return SimpleNamespace(system_code=system_code, name="대표홈페이지(PC)")

    def validate_run_request(self, system_code, input_data, selected_module_ids):
        return dict(input_data), list(selected_module_ids or [])

    async def get_run(self, run_id: str):
        return self.runs[run_id]

    async def start_run(self, system_code, input_data, selected_module_ids, **kwargs):
        run = _fake_run(f"run_new_{len(self.started)}", RunStatus.RUNNING)
        self.started.append(system_code)
        self.runs[run.run_id] = run
        return run

    async def submit_otp(self, run_id: str, otp_code: str):
        self.otp_calls.append((run_id, otp_code))
        return self.runs[run_id]


class _FakeSuiteService:
    def __init__(self, suites: dict[str, SimpleNamespace] | None = None) -> None:
        self.suites = suites or {}
        self.otp_calls: list[tuple[str, str]] = []

    async def get_suite(self, suite_id: str):
        return self.suites[suite_id]

    async def submit_otp(self, suite_id: str, otp_code: str):
        self.otp_calls.append((suite_id, otp_code))
        return self.suites[suite_id]


def _schedule(**overrides) -> Schedule:
    defaults = dict(
        schedule_id="sch_test1",
        schedule_kind="system",
        system_code="hom",
        system_name="대표홈페이지(PC)",
        name="아침 점검",
        cron="0 7 * * 1-5",
        timezone="Asia/Seoul",
        trigger_token="tok_secret",
        created_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return Schedule(**defaults)


def _scheduler(repo, run_service=None, suite_service=None) -> SchedulerService:
    return SchedulerService(
        run_service=run_service or _FakeRunService(),
        suite_service=suite_service or _FakeSuiteService(),
        repository=repo,
    )


# --------------------------------------------------------------------------- #
# 1. 토큰 발급 · 지연 발급(backfill)
# --------------------------------------------------------------------------- #
async def test_create_schedule_issues_trigger_token():
    repo = _FakeScheduleRepo()
    service = _scheduler(repo)
    schedule = await service.create_schedule(
        "hom", CreateScheduleRequest(cron="0 7 * * 1-5", input_data={"auth_method": "phone"})
    )
    assert schedule.trigger_token
    assert len(schedule.trigger_token) >= 24


async def test_list_schedules_backfills_missing_token():
    legacy = _schedule(trigger_token=None)
    repo = _FakeScheduleRepo([legacy])
    service = _scheduler(repo)
    summaries = await service.list_schedules()
    assert summaries[0]["trigger_token"]
    stored = await repo.get(legacy.schedule_id)
    assert stored.trigger_token == summaries[0]["trigger_token"]


# --------------------------------------------------------------------------- #
# 2. 토큰 조회
# --------------------------------------------------------------------------- #
async def test_find_by_trigger_token_matches_exact_token():
    schedule = _schedule()
    service = _scheduler(_FakeScheduleRepo([schedule]))
    found = await service.find_by_trigger_token("tok_secret")
    assert found is not None and found.schedule_id == schedule.schedule_id
    assert await service.find_by_trigger_token("tok_wrong") is None
    assert await service.find_by_trigger_token("") is None


# --------------------------------------------------------------------------- #
# 3. trigger_now — 멱등 가드
# --------------------------------------------------------------------------- #
async def test_trigger_now_fires_run_when_idle():
    schedule = _schedule()
    run_service = _FakeRunService()
    service = _scheduler(_FakeScheduleRepo([schedule]), run_service=run_service)
    payload = await service.trigger_now(schedule.schedule_id)
    assert run_service.started == ["hom"]
    assert payload["already_running"] is False
    assert payload["status"] == RunStatus.RUNNING.value


async def test_trigger_now_attaches_to_active_run_instead_of_double_firing():
    active = _fake_run(
        "run_active",
        RunStatus.RUNNING,
        modules=[_module(ModuleStatus.PASSED), _module(ModuleStatus.RUNNING)],
    )
    schedule = _schedule(last_run_id="run_active")
    run_service = _FakeRunService(runs={"run_active": active})
    service = _scheduler(_FakeScheduleRepo([schedule]), run_service=run_service)
    payload = await service.trigger_now(schedule.schedule_id)
    assert run_service.started == []  # 이중 발사 금지
    assert payload["already_running"] is True
    assert payload["status"] == RunStatus.RUNNING.value
    assert payload["progress"] == "1/2"


# --------------------------------------------------------------------------- #
# 4. trigger_status · OTP 라우팅
# --------------------------------------------------------------------------- #
async def test_trigger_status_reports_waiting_input_and_progress():
    run = _fake_run(
        "run_wait",
        RunStatus.WAITING_INPUT,
        modules=[
            _module(ModuleStatus.PASSED),
            _module(ModuleStatus.WAITING_INPUT),
            _module(ModuleStatus.SKIPPED),
        ],
    )
    run.awaiting_input_prompt = "인증번호를 입력하세요"
    schedule = _schedule(last_run_id="run_wait")
    service = _scheduler(
        _FakeScheduleRepo([schedule]), run_service=_FakeRunService(runs={"run_wait": run})
    )
    payload = await service.trigger_status(schedule.schedule_id)
    assert payload["waiting_input"] is True
    assert payload["awaiting_prompt"] == "인증번호를 입력하세요"
    assert payload["progress"] == "1/2"  # SKIPPED 는 분모에서 제외


async def test_submit_trigger_otp_routes_to_run_or_suite():
    run = _fake_run("run_wait", RunStatus.WAITING_INPUT)
    run_schedule = _schedule(last_run_id="run_wait")
    suite = SimpleNamespace(suite_id="suite_1", status=SuiteStatus.WAITING_INPUT, steps=[])
    suite_schedule = _schedule(
        schedule_id="sch_suite",
        schedule_kind="suite",
        trigger_token="tok_suite",
        last_suite_id="suite_1",
    )
    run_service = _FakeRunService(runs={"run_wait": run})
    suite_service = _FakeSuiteService(suites={"suite_1": suite})
    service = _scheduler(
        _FakeScheduleRepo([run_schedule, suite_schedule]),
        run_service=run_service,
        suite_service=suite_service,
    )

    await service.submit_trigger_otp(run_schedule.schedule_id, "123456")
    assert run_service.otp_calls == [("run_wait", "123456")]

    await service.submit_trigger_otp(suite_schedule.schedule_id, "654321")
    assert suite_service.otp_calls == [("suite_1", "654321")]


async def test_submit_trigger_otp_raises_without_last_execution():
    schedule = _schedule(last_run_id=None)
    service = _scheduler(_FakeScheduleRepo([schedule]))
    with pytest.raises(KeyError):
        await service.submit_trigger_otp(schedule.schedule_id, "123456")


# --------------------------------------------------------------------------- #
# 5. 라우트 핸들러 — 토큰 불일치 404 매핑
# --------------------------------------------------------------------------- #
class _FakeSchedulerForRoute:
    def __init__(self, schedule: Schedule | None) -> None:
        self._schedule = schedule
        self.trigger_calls = 0

    async def find_by_trigger_token(self, token: str):
        if self._schedule and self._schedule.trigger_token == token:
            return self._schedule
        return None

    async def trigger_now(self, schedule_id: str) -> dict:
        self.trigger_calls += 1
        return {"schedule_id": schedule_id, "already_running": False}

    async def trigger_status(self, schedule_id: str) -> dict:
        return {"schedule_id": schedule_id}

    async def submit_trigger_otp(self, schedule_id: str, otp_code: str) -> dict:
        raise KeyError("no waiting execution")


async def test_fire_trigger_returns_404_for_unknown_token():
    fake = _FakeSchedulerForRoute(schedule=None)
    with pytest.raises(HTTPException) as exc:
        await fire_trigger(trigger_token="tok_unknown", schedule_service=fake)
    assert exc.value.status_code == 404
    assert fake.trigger_calls == 0


async def test_fire_trigger_executes_for_valid_token():
    fake = _FakeSchedulerForRoute(schedule=_schedule())
    payload = await fire_trigger(trigger_token="tok_secret", schedule_service=fake)
    assert fake.trigger_calls == 1
    assert payload["schedule_id"] == "sch_test1"


async def test_trigger_status_route_returns_404_for_unknown_token():
    fake = _FakeSchedulerForRoute(schedule=None)
    with pytest.raises(HTTPException) as exc:
        await trigger_status(trigger_token="tok_unknown", schedule_service=fake)
    assert exc.value.status_code == 404


async def test_trigger_otp_route_maps_keyerror_to_404():
    fake = _FakeSchedulerForRoute(schedule=_schedule())
    with pytest.raises(HTTPException) as exc:
        await submit_trigger_otp(
            trigger_token="tok_secret",
            payload=SubmitOtpRequest(otp_code="123456"),
            schedule_service=fake,
        )
    assert exc.value.status_code == 404
