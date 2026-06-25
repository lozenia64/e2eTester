from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.enums import RunStatus, SuiteStatus
from app.core.logging import get_logger
from app.core.settings import get_settings
from app.core.models import (
    SUITE_SCHEDULE_SYSTEM_CODE,
    SUITE_SCHEDULE_SYSTEM_NAME,
    CreateScheduleRequest,
    CreateSuiteScheduleRequest,
    Run,
    Schedule,
    StartSuiteRequest,
    SuiteRun,
)
from app.scheduling.cron import next_run_after, parse_cron
from app.storage.ports import ScheduleRepositoryPort

DEFAULT_SCHEDULE_TIMEZONE = "Asia/Seoul"
DEFAULT_TICK_SECONDS = 20
_ACTIVE_RUN_STATUSES = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT}
_ACTIVE_SUITE_STATUSES = {SuiteStatus.PENDING, SuiteStatus.RUNNING, SuiteStatus.WAITING_INPUT}

logger = get_logger(__name__)


def _resolve_timezone() -> tuple[ZoneInfo, str]:
    settings = get_settings()
    name = (settings.schedule_tz or "").strip() or DEFAULT_SCHEDULE_TIMEZONE
    try:
        return ZoneInfo(name), name
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(
            "알 수 없는 타임존, UTC 로 대체",
            log_event="schedule.timezone_fallback",
            timezone=name,
        )
        return ZoneInfo("UTC"), "UTC"


class SchedulerService:
    """예약(Schedule) CRUD 와, cron 기준으로 Run/Suite 를 자동 트리거하는 백그라운드 루프.

    메모리 기반이라 서버 재시작 시 예약이 사라진다(영구 저장소 도입 시 함께 개선 예정).
    예약 실행은 무인 실행이므로, 휴대폰/카카오 인증처럼 사람 개입이 필요한 단계가
    선택되어 있으면 해당 Run/Suite 은 OTP 대기(WAITING_INPUT)에서 멈출 수 있다.
    """

    def __init__(
        self,
        run_service,
        suite_service,
        repository: ScheduleRepositoryPort,
        tick_seconds: int = DEFAULT_TICK_SECONDS,
    ) -> None:
        self._run_service = run_service
        self._suite_service = suite_service
        self._repository = repository
        self._tick_seconds = tick_seconds
        self._timezone, self._timezone_name = _resolve_timezone()
        self._running = False

    # --- CRUD -------------------------------------------------------------

    async def create_schedule(
        self,
        system_code: str,
        request: CreateScheduleRequest,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> Schedule:
        system = self._run_service.get_system(system_code)  # KeyError -> 404
        parse_cron(request.cron)  # ValueError -> 400
        sanitized_input, resolved_module_ids = self._run_service.validate_run_request(
            system_code, request.input_data, request.selected_module_ids
        )
        schedule = Schedule(
            schedule_id=f"sch_{uuid4().hex[:8]}",
            schedule_kind="system",
            system_code=system.system_code,
            system_name=system.name,
            name=request.name.strip(),
            cron=request.cron.strip(),
            timezone=self._timezone_name,
            enabled=request.enabled,
            input_data=sanitized_input,
            selected_module_ids=resolved_module_ids,
            created_at=datetime.now(UTC),
            created_by_user_id=user_id,
            created_by_user_name=user_name,
            next_run_at=self._next_run_from_now(request.cron) if request.enabled else None,
        )
        await self._repository.save(schedule)
        return schedule

    async def create_suite_schedule(
        self,
        request: CreateSuiteScheduleRequest,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> Schedule:
        parse_cron(request.cron)  # ValueError -> 400
        browser_mode, normalized_systems, resolved_system_codes = self._suite_service.validate_suite_request(
            request.browser_mode,
            request.systems,
            request.selected_system_codes,
        )
        schedule = Schedule(
            schedule_id=f"sch_{uuid4().hex[:8]}",
            schedule_kind="suite",
            system_code=SUITE_SCHEDULE_SYSTEM_CODE,
            system_name=SUITE_SCHEDULE_SYSTEM_NAME,
            name=request.name.strip(),
            cron=request.cron.strip(),
            timezone=self._timezone_name,
            enabled=request.enabled,
            browser_mode=browser_mode,
            suite_systems=normalized_systems,
            selected_system_codes=resolved_system_codes,
            scope_system_codes=request.scope_system_codes,
            step_total=len(resolved_system_codes),
            created_at=datetime.now(UTC),
            created_by_user_id=user_id,
            created_by_user_name=user_name,
            next_run_at=self._next_run_from_now(request.cron) if request.enabled else None,
        )
        await self._repository.save(schedule)
        return schedule

    async def list_schedules(self, user_id: str | None = None) -> list[dict]:
        schedules = sorted(await self._repository.list(), key=lambda item: item.created_at, reverse=True)
        if user_id is not None:
            schedules = [schedule for schedule in schedules if schedule.created_by_user_id == user_id]
        summaries: list[dict] = []
        for schedule in schedules:
            await self._refresh_last_execution_status(schedule)
            summaries.append(schedule.to_summary())
        return summaries

    async def delete_schedule(self, schedule_id: str) -> None:
        await self._repository.get(schedule_id)  # KeyError -> 404
        await self._repository.delete(schedule_id)

    async def set_enabled(self, schedule_id: str, enabled: bool) -> Schedule:
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        schedule.enabled = enabled
        schedule.next_run_at = self._next_run_from_now(schedule.cron) if enabled else None
        await self._repository.save(schedule)
        return schedule

    async def toggle(self, schedule_id: str) -> Schedule:
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        return await self.set_enabled(schedule_id, not schedule.enabled)

    async def run_now(
        self,
        schedule_id: str,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> dict:
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        if schedule.schedule_kind == "suite":
            suite = await self._trigger_suite(schedule, user_id=user_id, user_name=user_name)
            await self._repository.save(schedule)
            return {
                "schedule_kind": "suite",
                "suite_id": suite.suite_id,
                "status": suite.status.value,
            }
        run = await self._trigger_run(schedule, user_id=user_id, user_name=user_name)
        await self._repository.save(schedule)
        payload = run.model_dump(mode="json")
        payload["schedule_kind"] = "system"
        return payload

    # --- 백그라운드 루프 --------------------------------------------------

    async def run_forever(self) -> None:
        self._running = True
        await self._reconcile_due_schedules_on_start()
        logger.info(
            "스케줄러 시작",
            log_event="schedule.started",
            timezone=self._timezone_name,
            tick_seconds=self._tick_seconds,
        )
        while self._running:
            try:
                await self._tick()
            except Exception as exc:  # 루프는 어떤 경우에도 죽지 않아야 한다
                logger.exception("스케줄러 tick 오류", log_event="schedule.tick_error", error=str(exc))
            try:
                await asyncio.sleep(self._tick_seconds)
            except asyncio.CancelledError:
                break
        logger.info("스케줄러 종료", log_event="schedule.stopped")

    def stop(self) -> None:
        self._running = False

    @property
    def timezone_name(self) -> str:
        return self._timezone_name

    async def _reconcile_due_schedules_on_start(self) -> None:
        """재기동 시 과거(``next_run_at`` ≤ now)로 밀린 활성 예약을 다음 cron 시각으로 재계산한다.

        영속 저장소(SQLite)를 쓰면 서버가 내려가 있는 동안 지나간 예약이 그대로 남아, 시작
        직후 한꺼번에 실행될 수 있다. 무인 예약 실행이 OTP 대기로 쌓이는 것을 막기 위해 누락분은
        catch-up 하지 않고 다음 예정 시각으로 미룬다.
        """
        now = datetime.now(UTC)
        rescheduled = 0
        for schedule in await self._repository.list():
            if schedule.enabled and schedule.next_run_at is not None and schedule.next_run_at <= now:
                schedule.next_run_at = self._next_run_from_now(schedule.cron)
                await self._repository.save(schedule)
                rescheduled += 1
        if rescheduled:
            logger.info(
                "재기동 시 과거 예약 시각 재계산",
                log_event="schedule.reconcile",
                rescheduled_count=rescheduled,
            )

    async def _tick(self) -> None:
        now = datetime.now(UTC)
        for schedule in await self._repository.list():
            if not schedule.enabled or schedule.next_run_at is None:
                continue
            if schedule.next_run_at > now:
                continue
            await self._fire(schedule, now)

    async def _fire(self, schedule: Schedule, now: datetime) -> None:
        if await self._last_execution_active(schedule):
            logger.info(
                "직전 실행 진행 중으로 이번 주기 건너뜀",
                log_event="schedule.skipped_overlap",
                schedule_id=schedule.schedule_id,
                schedule_kind=schedule.schedule_kind,
                system_code=schedule.system_code,
            )
            schedule.next_run_at = self._next_run_from_now(schedule.cron)
            await self._repository.save(schedule)
            return
        fired_id: str | None = None
        try:
            if schedule.schedule_kind == "suite":
                suite = await self._trigger_suite(schedule)
                fired_id = suite.suite_id
            else:
                run = await self._trigger_run(schedule)
                fired_id = run.run_id
        except Exception as exc:
            logger.exception(
                "예약 실행 실패",
                log_event="schedule.fire_failed",
                schedule_id=schedule.schedule_id,
                schedule_kind=schedule.schedule_kind,
                system_code=schedule.system_code,
                error=str(exc),
            )
        else:
            logger.info(
                "예약 실행 트리거",
                log_event="schedule.fired",
                schedule_id=schedule.schedule_id,
                schedule_kind=schedule.schedule_kind,
                system_code=schedule.system_code,
                fired_id=fired_id,
            )
        schedule.next_run_at = self._next_run_from_now(schedule.cron)
        await self._repository.save(schedule)

    async def _trigger_run(
        self,
        schedule: Schedule,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> Run:
        actor_id = user_id or schedule.created_by_user_id
        actor_name = user_name or schedule.created_by_user_name
        run = await self._run_service.start_run(
            schedule.system_code,
            dict(schedule.input_data),
            list(schedule.selected_module_ids) if schedule.selected_module_ids is not None else None,
            triggered_by="schedule",
            schedule_id=schedule.schedule_id,
            user_id=actor_id,
            user_name=actor_name,
        )
        schedule.last_run_id = run.run_id
        schedule.last_run_at = datetime.now(UTC)
        schedule.last_run_status = run.status
        return run

    async def _trigger_suite(
        self,
        schedule: Schedule,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> SuiteRun:
        actor_id = user_id or schedule.created_by_user_id
        actor_name = user_name or schedule.created_by_user_name
        suite = await self._suite_service.start_suite(
            StartSuiteRequest(
                browser_mode=schedule.browser_mode or "headed",
                systems=dict(schedule.suite_systems or {}),
                selected_system_codes=list(schedule.selected_system_codes)
                if schedule.selected_system_codes is not None
                else None,
                scope_system_codes=list(schedule.scope_system_codes)
                if schedule.scope_system_codes is not None
                else None,
            ),
            user_id=actor_id,
            user_name=actor_name,
        )
        schedule.last_suite_id = suite.suite_id
        schedule.last_run_at = datetime.now(UTC)
        schedule.last_suite_status = suite.status
        return suite

    async def _last_execution_active(self, schedule: Schedule) -> bool:
        if schedule.schedule_kind == "suite":
            if not schedule.last_suite_id:
                return False
            return await self._last_suite_active(schedule.last_suite_id)
        if not schedule.last_run_id:
            return False
        return await self._last_run_active(schedule.last_run_id)

    async def _last_run_active(self, run_id: str) -> bool:
        try:
            run = await self._run_service.get_run(run_id)
        except KeyError:
            return False
        return run.status in _ACTIVE_RUN_STATUSES

    async def _last_suite_active(self, suite_id: str) -> bool:
        try:
            suite = await self._suite_service.get_suite(suite_id)
        except KeyError:
            return False
        return suite.status in _ACTIVE_SUITE_STATUSES

    async def _refresh_last_execution_status(self, schedule: Schedule) -> None:
        if schedule.schedule_kind == "suite":
            if not schedule.last_suite_id:
                return
            try:
                suite = await self._suite_service.get_suite(schedule.last_suite_id)
            except KeyError:
                return
            if schedule.last_suite_status != suite.status:
                schedule.last_suite_status = suite.status
                await self._repository.save(schedule)
            return

        if not schedule.last_run_id:
            return
        try:
            run = await self._run_service.get_run(schedule.last_run_id)
        except KeyError:
            return
        if schedule.last_run_status != run.status:
            schedule.last_run_status = run.status
            await self._repository.save(schedule)

    def _next_run_from_now(self, cron: str) -> datetime:
        return next_run_after(cron, datetime.now(self._timezone))
