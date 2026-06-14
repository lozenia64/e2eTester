from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.enums import RunStatus
from app.core.env_utils import DEFAULT_ENV_FILE_PATH, load_dotenv_file, resolve_env_value
from app.core.models import CreateScheduleRequest, Run, Schedule
from app.scheduling.cron import next_run_after, parse_cron
from app.storage.schedule_repository import InMemoryScheduleRepository

DEFAULT_SCHEDULE_TIMEZONE = "Asia/Seoul"
DEFAULT_TICK_SECONDS = 20
_ACTIVE_RUN_STATUSES = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT}


def _resolve_timezone() -> tuple[ZoneInfo, str]:
    dotenv_values = load_dotenv_file(DEFAULT_ENV_FILE_PATH)
    name = (resolve_env_value("E2E_SCHEDULE_TZ", dotenv_values) or "").strip() or DEFAULT_SCHEDULE_TIMEZONE
    try:
        return ZoneInfo(name), name
    except (ZoneInfoNotFoundError, ValueError):
        print(f"[scheduler] 알 수 없는 타임존 '{name}', UTC 로 대체합니다.")
        return ZoneInfo("UTC"), "UTC"


class SchedulerService:
    """예약(Schedule) CRUD 와, cron 기준으로 Run 을 자동 트리거하는 백그라운드 루프.

    메모리 기반이라 서버 재시작 시 예약이 사라진다(영구 저장소 도입 시 함께 개선 예정).
    예약 실행은 무인 실행이므로, 휴대폰/카카오 인증처럼 사람 개입이 필요한 단계가
    선택되어 있으면 해당 Run 은 OTP 대기(WAITING_INPUT)에서 멈출 수 있다.
    """

    def __init__(
        self,
        run_service,
        repository: InMemoryScheduleRepository,
        tick_seconds: int = DEFAULT_TICK_SECONDS,
    ) -> None:
        self._run_service = run_service
        self._repository = repository
        self._tick_seconds = tick_seconds
        self._timezone, self._timezone_name = _resolve_timezone()
        self._running = False

    # --- CRUD -------------------------------------------------------------

    async def create_schedule(self, system_code: str, request: CreateScheduleRequest) -> Schedule:
        system = self._run_service.get_system(system_code)  # KeyError -> 404
        parse_cron(request.cron)  # ValueError -> 400
        sanitized_input, resolved_module_ids = self._run_service.validate_run_request(
            system_code, request.input_data, request.selected_module_ids
        )
        schedule = Schedule(
            schedule_id=f"sch_{uuid4().hex[:8]}",
            system_code=system.system_code,
            system_name=system.name,
            name=request.name.strip(),
            cron=request.cron.strip(),
            timezone=self._timezone_name,
            enabled=request.enabled,
            input_data=sanitized_input,
            selected_module_ids=resolved_module_ids,
            created_at=datetime.now(UTC),
            next_run_at=self._next_run_from_now(request.cron) if request.enabled else None,
        )
        await self._repository.save(schedule)
        return schedule

    async def list_schedules(self) -> list[dict]:
        schedules = sorted(await self._repository.list(), key=lambda item: item.created_at, reverse=True)
        summaries: list[dict] = []
        for schedule in schedules:
            await self._refresh_last_run_status(schedule)
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

    async def run_now(self, schedule_id: str) -> Run:
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        run = await self._trigger(schedule)
        await self._repository.save(schedule)
        return run

    # --- 백그라운드 루프 --------------------------------------------------

    async def run_forever(self) -> None:
        self._running = True
        print(f"[scheduler] 시작 (tz={self._timezone_name}, tick={self._tick_seconds}s)")
        while self._running:
            try:
                await self._tick()
            except Exception as exc:  # 루프는 어떤 경우에도 죽지 않아야 한다
                print(f"[scheduler] tick 오류: {exc}")
            try:
                await asyncio.sleep(self._tick_seconds)
            except asyncio.CancelledError:
                break
        print("[scheduler] 종료")

    def stop(self) -> None:
        self._running = False

    async def _tick(self) -> None:
        now = datetime.now(UTC)
        for schedule in await self._repository.list():
            if not schedule.enabled or schedule.next_run_at is None:
                continue
            if schedule.next_run_at > now:
                continue
            await self._fire(schedule, now)

    async def _fire(self, schedule: Schedule, now: datetime) -> None:
        # 직전 실행이 아직 진행 중이면 중복 실행을 피하고 다음 주기로 미룬다.
        if schedule.last_run_id and await self._last_run_active(schedule.last_run_id):
            print(f"[scheduler] {schedule.schedule_id} 직전 Run 진행 중 -> 이번 주기 건너뜀")
            schedule.next_run_at = self._next_run_from_now(schedule.cron)
            await self._repository.save(schedule)
            return
        try:
            await self._trigger(schedule)
        except Exception as exc:
            print(f"[scheduler] {schedule.schedule_id} 예약 실행 실패: {exc}")
        schedule.next_run_at = self._next_run_from_now(schedule.cron)
        await self._repository.save(schedule)

    async def _trigger(self, schedule: Schedule) -> Run:
        run = await self._run_service.start_run(
            schedule.system_code,
            dict(schedule.input_data),
            list(schedule.selected_module_ids) if schedule.selected_module_ids is not None else None,
            triggered_by="schedule",
            schedule_id=schedule.schedule_id,
        )
        schedule.last_run_id = run.run_id
        schedule.last_run_at = datetime.now(UTC)
        schedule.last_run_status = run.status
        return run

    async def _last_run_active(self, run_id: str) -> bool:
        try:
            run = await self._run_service.get_run(run_id)
        except KeyError:
            return False
        return run.status in _ACTIVE_RUN_STATUSES

    async def _refresh_last_run_status(self, schedule: Schedule) -> None:
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
