from __future__ import annotations

import asyncio
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.contexts.preset.infrastructure.ports import PresetRepositoryPort
from app.contexts.run.contracts.query_rows import RunSummaryRow
from app.contexts.scheduling.command_port import ScheduleCommandPort, ScheduleRunQueryPort
from app.contexts.scheduling.cron import next_run_after, parse_cron
from app.contexts.scheduling.infrastructure.ports import ScheduleRepositoryPort
from app.contexts.scheduling.preset_bindings import (
    SchedulePresetBindings,
    auth_input,
    normalize_codes,
)
from app.contexts.scheduling.schedule_center import (
    MATCH_BEFORE,
    ExecutionPoint,
    build_coverage,
    build_history_stats,
    classify_issues,
    cluster_warnings,
    count_today_planned,
    cron_to_label,
    expand_occurrences,
    match_occurrences,
)
from app.contexts.suite.contracts.query_rows import SuiteSummaryRow
from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.logging import get_logger
from app.core.requests import (
    CreateScheduleRequest,
    CreateSuiteScheduleRequest,
    StartSuiteRequest,
    UpdateScheduleRequest,
)
from app.core.run_models import Run
from app.core.schedule_models import (
    SUITE_SCHEDULE_SYSTEM_CODE,
    SUITE_SCHEDULE_SYSTEM_NAME,
    Schedule,
)
from app.core.schedule_time import resolve_schedule_timezone as _resolve_timezone
from app.core.suite_models import SuiteRun

DEFAULT_SCHEDULE_TIMEZONE = "Asia/Seoul"
DEFAULT_TICK_SECONDS = 20
_ACTIVE_RUN_STATUSES = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT}
_ACTIVE_SUITE_STATUSES = {SuiteStatus.PENDING, SuiteStatus.RUNNING, SuiteStatus.WAITING_INPUT}

logger = get_logger(__name__)


def _new_trigger_token() -> str:
    """모바일 즉시 점검 URL 용 예약별 비밀 토큰(URL-safe, 추측 불가)."""
    return secrets.token_urlsafe(24)


def _ensure_utc(moment: datetime | None) -> datetime | None:
    """레거시(naive) 저장 값을 UTC aware 로 강제한다 — 비교/차이 계산 안전장치."""
    if moment is None:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def schedule_day_start_utc(date_label: str) -> datetime:
    """스케줄 타임존 기준 ``date_label``(YYYY-MM-DD) 00:00:00 을 UTC 로 반환한다.

    일간 집계가 임의 날짜를 조회할 때 쓴다(P3-3 일간 리포트는 어제를 본다).
    """
    tz, _ = _resolve_timezone()
    day = datetime.strptime(date_label, "%Y-%m-%d")
    return day.replace(tzinfo=tz).astimezone(UTC)


def schedule_today_label() -> str:
    """스케줄 타임존 기준 '오늘' 날짜 라벨(YYYY-MM-DD)."""
    tz, _ = _resolve_timezone()
    return datetime.now(tz).strftime("%Y-%m-%d")


def schedule_today_start_utc() -> datetime:
    """스케줄 타임존 기준 '오늘' 00:00:00 을 UTC 로 반환한다."""
    return schedule_day_start_utc(schedule_today_label())


def schedule_month_start_utc() -> datetime:
    """스케줄 타임존 기준 '이번 달' 1일 00:00:00 을 UTC 로 반환한다."""
    tz, _ = _resolve_timezone()
    now_local = datetime.now(tz)
    month_start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_start_local.astimezone(UTC)


class SchedulerService:
    """예약(Schedule) CRUD 와, cron 기준으로 Run/Suite 를 자동 트리거하는 백그라운드 루프.

    예약 실행은 무인 실행이므로, 휴대폰/카카오 인증처럼 사람 개입이 필요한 단계가
    선택되어 있으면 해당 Run/Suite 은 OTP 대기(WAITING_INPUT)에서 멈출 수 있다.
    """

    def __init__(
        self,
        run_commands: ScheduleCommandPort,
        suite_service,
        repository: ScheduleRepositoryPort,
        run_queries: ScheduleRunQueryPort,
        tick_seconds: int = DEFAULT_TICK_SECONDS,
        preset_repository: PresetRepositoryPort | None = None,
    ) -> None:
        self._run_commands = run_commands
        self._suite_service = suite_service
        self._repository = repository
        # Run 이력은 blob 이 아니라 요약 인덱스 행으로만 읽는다(관제 보드/캘린더/상세 이력).
        self._run_queries = run_queries
        self._tick_seconds = tick_seconds
        self._timezone, self._timezone_name = _resolve_timezone()
        self._running = False
        self._presets = SchedulePresetBindings(preset_repository)

    # --- CRUD -------------------------------------------------------------

    async def create_schedule(
        self,
        system_code: str,
        request: CreateScheduleRequest,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> Schedule:
        system = self._run_commands.get_system(system_code)  # KeyError -> 404
        parse_cron(request.cron)  # ValueError -> 400
        if request.preset_id and auth_input(request.input_data):
            raise ValueError("프리셋 참조와 인증 입력값을 함께 저장할 수 없습니다.")
        mode = request.browser_mode or request.input_data.get("browser_mode")
        if mode and mode not in {"headed", "headless"}:
            raise ValueError("브라우저 모드는 headed 또는 headless여야 합니다.")
        schedule = Schedule(
            schedule_id=f"sch_{uuid4().hex[:8]}",
            schedule_kind="system",
            system_code=system.system_code,
            system_name=system.name,
            name=request.name.strip(),
            cron=request.cron.strip(),
            timezone=self._timezone_name,
            enabled=request.enabled,
            trigger_token=_new_trigger_token(),
            input_data=dict(request.input_data),
            preset_id=request.preset_id,
            browser_mode=mode,
            selected_module_ids=request.selected_module_ids,
            created_at=datetime.now(UTC),
            created_by_user_id=user_id,
            created_by_user_name=user_name,
            next_run_at=self._next_run_from_now(request.cron) if request.enabled else None,
        )
        inputs = await self._presets.resolve(schedule)
        sanitized_input, resolved_module_ids = self._run_commands.validate_run_request(
            system_code, inputs[system_code], request.selected_module_ids
        )
        schedule.input_data = {} if schedule.preset_id else dict(request.input_data)
        if not schedule.preset_id:
            schedule.input_data.update(sanitized_input)
        schedule.selected_module_ids = resolved_module_ids
        schedule.record_change(
            "created", f"예약 등록({cron_to_label(schedule.cron)})", user_name=user_name
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
        if any(request.systems.get(code) for code in request.preset_ids):
            raise ValueError("프리셋 참조와 같은 시스템의 인증 입력값을 함께 저장할 수 없습니다.")
        selected = request.selected_system_codes
        if selected is None:
            selected = [s.system_code for s in self._run_commands.list_systems()]
        candidate = Schedule(
            schedule_id="검증",
            system_code="suite",
            system_name="전체 점검",
            schedule_kind="suite",
            cron=request.cron,
            timezone=self._timezone_name,
            created_at=datetime.now(UTC),
            created_by_user_id=user_id,
            preset_ids=request.preset_ids,
            selected_system_codes=selected,
            suite_systems=request.systems,
        )
        inputs = await self._presets.resolve(candidate)
        browser_mode, normalized_systems, resolved_system_codes = (
            self._suite_service.validate_suite_request(
                request.browser_mode,
                inputs,
                selected,
            )
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
            trigger_token=_new_trigger_token(),
            browser_mode=browser_mode,
            suite_systems={
                code: values
                for code, values in normalized_systems.items()
                if code not in request.preset_ids
            },
            preset_ids=dict(request.preset_ids),
            selected_system_codes=resolved_system_codes,
            scope_system_codes=request.scope_system_codes,
            step_total=len(resolved_system_codes),
            created_at=datetime.now(UTC),
            created_by_user_id=user_id,
            created_by_user_name=user_name,
            next_run_at=self._next_run_from_now(request.cron) if request.enabled else None,
        )
        schedule.record_change(
            "created", f"예약 등록({cron_to_label(schedule.cron)})", user_name=user_name
        )
        await self._repository.save(schedule)
        return schedule

    async def list_schedules(self, user_id: str | None = None) -> list[dict]:
        schedules = sorted(
            await self._repository.list(), key=lambda item: item.created_at, reverse=True
        )
        if user_id is not None:
            schedules = [
                schedule for schedule in schedules if schedule.created_by_user_id == user_id
            ]
        summaries: list[dict] = []
        for schedule in schedules:
            await self._ensure_trigger_token(schedule)
            await self._refresh_last_execution_status(schedule)
            summaries.append(self._augment_summary(schedule.to_summary(), schedule))
        return summaries

    def _augment_summary(self, summary: dict, schedule: Schedule) -> dict:
        """요약에 표시용 파생 필드(cron 한글 라벨, 일시 중지 여부)를 얹는다."""
        now = datetime.now(UTC)
        paused_until = _ensure_utc(schedule.paused_until)
        summary["cron_label"] = cron_to_label(schedule.cron)
        summary["paused"] = paused_until is not None and paused_until > now
        return summary

    async def _ensure_trigger_token(self, schedule: Schedule) -> None:
        """토큰 도입 이전에 만든 예약(레거시 행)에 트리거 토큰을 지연 발급한다."""
        if schedule.trigger_token:
            return
        schedule.trigger_token = _new_trigger_token()
        await self._repository.save(schedule)

    async def delete_schedule(self, schedule_id: str) -> None:
        await self._repository.get(schedule_id)  # KeyError -> 404
        await self._repository.delete(schedule_id)

    async def set_enabled(
        self, schedule_id: str, enabled: bool, user_name: str | None = None
    ) -> Schedule:
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        schedule.enabled = enabled
        schedule.next_run_at = self._next_run_from_now(schedule.cron) if enabled else None
        schedule.disabled_at = None if enabled else datetime.now(UTC)
        schedule.record_change(
            "enabled" if enabled else "disabled",
            "예약 켬" if enabled else "예약 끔",
            user_name=user_name,
        )
        await self._repository.save(schedule)
        return schedule

    async def toggle(self, schedule_id: str, user_name: str | None = None) -> Schedule:
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        return await self.set_enabled(schedule_id, not schedule.enabled, user_name=user_name)

    async def get_detail(self, schedule_id: str) -> dict:
        """상세 드로어용 — 요약 + 변경 이력(+ 저장된 입력값 키 목록, 값은 미노출)."""
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        await self._ensure_trigger_token(schedule)
        await self._refresh_last_execution_status(schedule)
        await self._migrate_presets(schedule)
        payload = self._augment_summary(schedule.to_detail(), schedule)
        payload.update(await self._presets.describe(schedule))
        return payload

    async def update_schedule(
        self,
        schedule_id: str,
        request: UpdateScheduleRequest,
        user_name: str | None = None,
    ) -> Schedule:
        """예약 in-place 수정 — 삭제 후 재생성 없이 이름/주기/모듈 선택/인증값을 바꾼다.

        ``input_data`` 는 제공된 비어있지 않은 키만 기존 값 위에 병합한다(저장된 PII 를
        화면에 되돌려주지 않고 교체 가능). 검증은 생성 경로와 동일한 규칙을 통과해야 한다.
        """
        schedule = (await self._repository.get(schedule_id)).model_copy(deep=True)
        schedule.browser_mode = schedule.browser_mode or schedule.input_data.get("browser_mode")
        changed: list[str] = []

        if request.name is not None and request.name.strip() != schedule.name:
            schedule.name = request.name.strip()
            changed.append("이름")

        if request.cron is not None and request.cron.strip() != schedule.cron:
            parse_cron(request.cron)  # ValueError -> 400
            schedule.cron = request.cron.strip()
            changed.append(f"주기({cron_to_label(schedule.cron)})")

        if schedule.schedule_kind == "suite":
            if request.preset_id is not None:
                raise ValueError("전체 예약은 시스템별 프리셋을 선택해 주세요.")
            if request.preset_ids is not None:
                schedule.preset_ids.update(request.preset_ids)
                for code in request.preset_ids:
                    if schedule.suite_systems:
                        schedule.suite_systems.pop(code, None)
                changed.append("프리셋 연결")
            if request.selected_system_codes is not None:
                selected_codes = normalize_codes(request.selected_system_codes)
                schedule.preset_ids = {
                    code: pid for code, pid in schedule.preset_ids.items() if code in selected_codes
                }
                if schedule.selected_system_codes != selected_codes:
                    changed.append("시스템 선택")
                schedule.selected_system_codes = selected_codes
            if (
                request.browser_mode is not None
                or request.selected_system_codes is not None
                or request.preset_ids is not None
            ):
                inputs = await self._presets.resolve(schedule)
                browser_mode, normalized_systems, resolved_system_codes = (
                    self._suite_service.validate_suite_request(
                        request.browser_mode or schedule.browser_mode or "headed",
                        inputs,
                        request.selected_system_codes
                        if request.selected_system_codes is not None
                        else schedule.selected_system_codes,
                    )
                )
                if request.browser_mode is not None and browser_mode != schedule.browser_mode:
                    changed.append("브라우저 모드")
                if (
                    request.selected_system_codes is not None
                    and resolved_system_codes != schedule.selected_system_codes
                ):
                    changed.append("시스템 선택")
                schedule.browser_mode = browser_mode
                schedule.suite_systems = {
                    code: values
                    for code, values in normalized_systems.items()
                    if code not in schedule.preset_ids
                }
                schedule.selected_system_codes = resolved_system_codes
                schedule.step_total = len(resolved_system_codes)
        else:
            if request.preset_ids is not None:
                raise ValueError("단일 예약은 프리셋 하나를 선택해 주세요.")
            if request.preset_id is not None:
                if not request.preset_id.strip():
                    raise ValueError("연결할 프리셋을 선택해 주세요.")
                schedule.preset_id = request.preset_id
                schedule.browser_mode = schedule.browser_mode or schedule.input_data.get(
                    "browser_mode"
                )
                schedule.input_data = {}
                await self._presets.resolve(schedule)
                changed.append("프리셋 연결")
            if schedule.preset_id and auth_input(request.input_data or {}):
                raise ValueError("연결된 프리셋의 인증값은 프리셋 관리에서 수정해 주세요.")
            legacy_mode = (request.input_data or {}).get("browser_mode", "").strip()
            if legacy_mode and request.browser_mode and legacy_mode != request.browser_mode:
                raise ValueError("브라우저 모드를 하나로 지정해 주세요.")
            mode = request.browser_mode if request.browser_mode is not None else legacy_mode
            if mode:
                if mode not in {"headed", "headless"}:
                    raise ValueError("브라우저 모드는 headed 또는 headless여야 합니다.")
                if mode != schedule.browser_mode:
                    schedule.browser_mode = mode
                    changed.append("브라우저 모드")
            input_changed = bool(
                request.input_data and any(auth_input(request.input_data).values())
            )
            modules_changed = (
                request.selected_module_ids is not None
                and request.selected_module_ids != (schedule.selected_module_ids or [])
            )
            if input_changed or modules_changed:
                merged_input = (await self._presets.resolve(schedule))[schedule.system_code]
                if request.input_data:
                    merged_input.update(
                        {
                            key: value.strip()
                            for key, value in request.input_data.items()
                            if value.strip()
                        }
                    )
                sanitized_input, resolved_module_ids = self._run_commands.validate_run_request(
                    schedule.system_code,
                    merged_input,
                    request.selected_module_ids
                    if request.selected_module_ids is not None
                    else schedule.selected_module_ids,
                )
                schedule.input_data = {} if schedule.preset_id else sanitized_input
                schedule.selected_module_ids = resolved_module_ids
                if input_changed:
                    changed.append("인증값")
                if modules_changed:
                    changed.append("모듈 선택")

        if "프리셋 연결" in changed:
            schedule.preparation_error = None
        if not changed:
            return schedule

        if schedule.enabled:
            schedule.next_run_at = self._next_run_from_now(schedule.cron)
        schedule.updated_at = datetime.now(UTC)
        schedule.record_change("updated", " · ".join(changed), user_name=user_name)
        await self._repository.save(schedule)
        return schedule

    async def pause_until(
        self,
        schedule_id: str,
        until: datetime | None,
        user_name: str | None = None,
    ) -> Schedule:
        """일시 중지(~시각까지) 설정/해제. 기한이 지나면 tick 이 자동 재개한다."""
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        if until is None:
            schedule.paused_until = None
            schedule.record_change(
                "pause_cleared", "일시 중지 해제(수동 재개)", user_name=user_name
            )
        else:
            if until.tzinfo is None:
                until = until.replace(tzinfo=self._timezone)
            until_utc = until.astimezone(UTC)
            if until_utc <= datetime.now(UTC):
                raise ValueError("일시 중지 종료 시각은 미래여야 합니다.")
            schedule.paused_until = until_utc
            local_label = until_utc.astimezone(self._timezone).strftime("%Y-%m-%d %H:%M")
            schedule.record_change("paused", f"{local_label} 까지 일시 중지", user_name=user_name)
        await self._repository.save(schedule)
        return schedule

    async def duplicate_schedule(
        self,
        schedule_id: str,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> Schedule:
        """예약 복제 — 같은 대상/주기/입력으로 새 예약을 만든다(검토 후 켜도록 비활성 상태)."""
        source = await self._repository.get(schedule_id)  # KeyError -> 404
        if (
            user_id
            and user_id != source.created_by_user_id
            and (source.preset_id or source.preset_ids)
        ):
            raise ValueError("다른 사용자의 프리셋을 참조하는 예약은 복제할 수 없습니다.")
        copy = source.model_copy(
            deep=True,
            update={
                "schedule_id": f"sch_{uuid4().hex[:8]}",
                "name": f"{source.name or source.system_name} (복사본)".strip(),
                "enabled": False,
                "trigger_token": _new_trigger_token(),
                "input_data": dict(source.input_data),
                "selected_module_ids": list(source.selected_module_ids)
                if source.selected_module_ids is not None
                else None,
                "suite_systems": {
                    code: dict(values) for code, values in source.suite_systems.items()
                }
                if source.suite_systems is not None
                else None,
                "selected_system_codes": list(source.selected_system_codes)
                if source.selected_system_codes is not None
                else None,
                "scope_system_codes": list(source.scope_system_codes)
                if source.scope_system_codes is not None
                else None,
                "created_at": datetime.now(UTC),
                "created_by_user_id": user_id or source.created_by_user_id,
                "created_by_user_name": user_name or source.created_by_user_name,
                "next_run_at": None,
                "last_run_at": None,
                "last_run_id": None,
                "last_run_status": None,
                "last_suite_id": None,
                "last_suite_status": None,
                "last_skipped_at": None,
                "paused_until": None,
                "disabled_at": datetime.now(UTC),
                "updated_at": None,
                "preparation_error": None,
                "change_log": [],
            },
        )
        copy.record_change(
            "duplicated",
            f"'{source.name or source.system_name}' 예약을 복제해 생성(비활성 상태)",
            user_name=user_name,
        )
        await self._repository.save(copy)
        return copy

    # --- 예약 점검 관리 센터 읽기 모델 (관제 보드 / 캘린더 / 이력) ------------

    @staticmethod
    def _run_point(run: RunSummaryRow) -> ExecutionPoint:
        return ExecutionPoint(
            execution_id=run.run_id,
            kind="run",
            status=run.status.value,
            requested_at=_ensure_utc(run.requested_at),
            started_at=_ensure_utc(run.started_at),
            ended_at=_ensure_utc(run.ended_at),
        )

    @staticmethod
    def _suite_point(suite: SuiteSummaryRow) -> ExecutionPoint:
        return ExecutionPoint(
            execution_id=suite.suite_id,
            kind="suite",
            status=suite.status.value,
            requested_at=_ensure_utc(suite.requested_at),
            started_at=_ensure_utc(suite.started_at),
            ended_at=_ensure_utc(suite.ended_at),
        )

    async def _recent_execution_points(
        self, schedule: Schedule, limit: int
    ) -> list[ExecutionPoint]:
        """예약 **하나**의 실행(Run/Suite)을 ``ExecutionPoint`` 로 투영한다(최신순, 상세 이력용)."""
        if schedule.schedule_kind == "suite":
            suites = await self._suite_service.list_suites_by_schedule(
                schedule.schedule_id, limit=limit
            )
            return [self._suite_point(suite) for suite in suites]
        runs = await self._run_queries.list_schedule_runs(schedule.schedule_id, limit=limit)
        return [self._run_point(run) for run in runs]

    async def _grouped_execution_points(
        self,
    ) -> tuple[dict[str, list[ExecutionPoint]], dict[str, list[ExecutionPoint]]]:
        """Run/Suite 저장소를 각각 1회만 스캔해 ``schedule_id`` 별 실행 포인트(최신순)로
        그룹핑한다 — 보드/캘린더가 예약마다 전체 스캔을 반복(O(#예약 × #Run))하지 않도록
        하는 공용 프리페치."""
        runs_by: dict[str, list[ExecutionPoint]] = {}
        for run in await self._run_queries.list_schedule_tagged_runs():
            runs_by.setdefault(run.schedule_id, []).append(self._run_point(run))
        suites_by: dict[str, list[ExecutionPoint]] = {}
        for suite in await self._suite_service.list_schedule_tagged_suites():
            suites_by.setdefault(suite.schedule_id, []).append(self._suite_point(suite))
        for points in runs_by.values():
            points.sort(key=lambda point: point.requested_at, reverse=True)
        for points in suites_by.values():
            points.sort(key=lambda point: point.requested_at, reverse=True)
        return runs_by, suites_by

    @staticmethod
    def _points_for(
        schedule: Schedule,
        runs_by: dict[str, list[ExecutionPoint]],
        suites_by: dict[str, list[ExecutionPoint]],
        limit: int | None = None,
    ) -> list[ExecutionPoint]:
        source = suites_by if schedule.schedule_kind == "suite" else runs_by
        points = source.get(schedule.schedule_id, [])
        return points[:limit] if limit is not None else points

    def _last_status_value(self, schedule: Schedule) -> str | None:
        if schedule.schedule_kind == "suite":
            return schedule.last_suite_status.value if schedule.last_suite_status else None
        return schedule.last_run_status.value if schedule.last_run_status else None

    async def board(self, user_id: str | None = None) -> dict:
        """관제 보드 — 전체 예약 요약 + 문제 예약 자동 승격(management by exception)."""
        now = datetime.now(UTC)
        day_start_local = datetime.now(self._timezone).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_end_local = day_start_local + timedelta(days=1)

        schedules = sorted(
            await self._repository.list(), key=lambda item: item.created_at, reverse=True
        )
        if user_id is not None:
            schedules = [s for s in schedules if s.created_by_user_id == user_id]

        runs_by, suites_by = await self._grouped_execution_points()
        entries: list[dict] = []
        attention: list[dict] = []
        active_count = 0
        today_planned = 0
        for schedule in schedules:
            await self._ensure_trigger_token(schedule)
            await self._refresh_last_execution_status(schedule)
            summary = self._augment_summary(schedule.to_summary(), schedule)
            recent = self._points_for(schedule, runs_by, suites_by, limit=5)
            issues = classify_issues(
                enabled=schedule.enabled,
                paused_until=_ensure_utc(schedule.paused_until),
                last_status=self._last_status_value(schedule),
                last_skipped_at=_ensure_utc(schedule.last_skipped_at),
                disabled_at=_ensure_utc(schedule.disabled_at),
                created_at=_ensure_utc(schedule.created_at),
                last_run_at=_ensure_utc(schedule.last_run_at),
                recent_executions=recent,
                now=now,
            )
            summary["issues"] = issues
            if schedule.enabled and not summary["paused"]:
                active_count += 1
                today_planned += count_today_planned(schedule.cron, day_start_local, day_end_local)
            if issues:
                attention.append(summary)
            entries.append(summary)

        return {
            "generated_at": now.isoformat(),
            "timezone": self._timezone_name,
            "kpi": {
                "total": len(entries),
                "active": active_count,
                "today_planned": today_planned,
                "attention": len(attention),
            },
            "attention": attention,
            "schedules": entries,
        }

    async def history(self, schedule_id: str, limit: int = 30) -> dict:
        """예약 단위 실행 이력(점 스트립 + 성공률/평균 소요/연속 성공)."""
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        points = await self._recent_execution_points(schedule, limit=limit)
        return {
            "schedule_id": schedule.schedule_id,
            "schedule_kind": schedule.schedule_kind,
            "name": schedule.name,
            "stats": build_history_stats(points),
        }

    async def calendar(
        self,
        start: datetime,
        end: datetime,
        user_id: str | None = None,
        allowed_system_codes: list[str] | None = None,
    ) -> dict:
        """점검 시간표 — cron 미래 전개(계획) + schedule-triggered 실행 매칭(실적/누락).

        기간은 최대 14일. 비활성 예약은 계획을 펼치지 않되 실적(unplanned 포함)은 남는다.
        """
        if end <= start:
            raise ValueError("조회 종료 시각은 시작 시각 이후여야 합니다.")
        if end - start > timedelta(days=14):
            raise ValueError("캘린더 조회 기간은 최대 14일입니다.")

        now = datetime.now(UTC)
        start_local = start.astimezone(self._timezone)
        end_local = end.astimezone(self._timezone)

        schedules = await self._repository.list()
        if user_id is not None:
            schedules = [s for s in schedules if s.created_by_user_id == user_id]

        runs_by, suites_by = await self._grouped_execution_points()
        blocks: list[dict] = []
        planned_pairs: list[tuple[str, datetime]] = []
        for schedule in schedules:
            # 예약이 생기기 전 슬롯을 '누락'으로 오인하지 않도록 전개 시작을 생성 시각으로 클램프.
            created_local = _ensure_utc(schedule.created_at).astimezone(self._timezone)
            occurrence_start = max(start_local, created_local)
            occurrences = (
                expand_occurrences(schedule.cron, occurrence_start, end_local)
                if schedule.enabled and occurrence_start < end_local
                else []
            )
            points = [
                point
                for point in self._points_for(schedule, runs_by, suites_by)
                if start - MATCH_BEFORE <= point.requested_at <= end
            ]
            for block in match_occurrences(occurrences, points, now):
                if not block.get("unplanned"):
                    planned_pairs.append((schedule.schedule_id, block["at"]))
                blocks.append(
                    {
                        "schedule_id": schedule.schedule_id,
                        "schedule_kind": schedule.schedule_kind,
                        "name": schedule.name or schedule.system_name,
                        "system_code": schedule.system_code,
                        "system_name": schedule.system_name,
                        "at": block["at"].isoformat(),
                        "state": block["state"],
                        "execution_id": block.get("execution_id"),
                        "link": block.get("link"),
                        "unplanned": bool(block.get("unplanned")),
                    }
                )
        blocks.sort(key=lambda block: block["at"])

        systems = sorted(self._run_commands.list_systems(), key=lambda s: (s.display_order, s.name))
        if allowed_system_codes is not None:
            allowed = set(allowed_system_codes)
            systems = [s for s in systems if s.system_code in allowed]
        coverage = build_coverage(
            [(s.system_code, s.name) for s in systems],
            await self._run_queries.last_finished_at_by_system(),
            now,
        )

        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "timezone": self._timezone_name,
            "generated_at": now.isoformat(),
            "blocks": blocks,
            "coverage": coverage,
            "cluster_warnings": cluster_warnings(planned_pairs),
        }

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

    # --- 모바일 즉시 점검 트리거 (예약별 비밀 토큰 인증) ---------------------

    async def find_by_trigger_token(self, token: str) -> Schedule | None:
        """트리거 토큰으로 예약을 찾는다(상수 시간 비교; 없으면 None)."""
        if not token:
            return None
        found: Schedule | None = None
        for schedule in await self._repository.list():
            if schedule.trigger_token and hmac.compare_digest(schedule.trigger_token, token):
                found = schedule
        return found

    async def trigger_now(
        self,
        schedule_id: str,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> dict:
        """모바일 트리거 진입점: 즉시 실행하되, 직전 실행이 아직 진행 중이면 **새로 만들지
        않고** 그 실행에 합류한다(페이지 새로고침/중복 탭이 실 사이트 점검을 이중 발사하지
        않게 하는 멱등 가드 — cron 루프의 overlap 스킵과 같은 정책)."""
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        if await self._last_execution_active(schedule):
            payload = await self.trigger_status(schedule_id)
            payload["already_running"] = True
            return payload
        if schedule.schedule_kind == "suite":
            await self._trigger_suite(schedule, user_id=user_id, user_name=user_name)
        else:
            await self._trigger_run(schedule, user_id=user_id, user_name=user_name)
        await self._repository.save(schedule)
        payload = await self.trigger_status(schedule_id)
        payload["already_running"] = False
        return payload

    async def trigger_status(self, schedule_id: str) -> dict:
        """모바일 트리거 페이지가 폴링하는 최근 실행 상태 요약(입력값/전체 blob 미노출)."""
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        await self._refresh_last_execution_status(schedule)
        payload: dict = {
            "schedule_id": schedule.schedule_id,
            "schedule_kind": schedule.schedule_kind,
            "name": schedule.name,
            "system_code": schedule.system_code,
            "system_name": schedule.system_name,
            "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
            "status": None,
            "waiting_input": False,
            "progress": None,
            "preparation_error": schedule.preparation_error,
            "execution_id": (
                schedule.last_suite_id
                if schedule.schedule_kind == "suite"
                else schedule.last_run_id
            ),
            "otp_run_id": None,
            "otp_request_id": None,
        }
        if schedule.schedule_kind == "suite":
            if not schedule.last_suite_id:
                return payload
            try:
                suite = await self._suite_service.get_suite(schedule.last_suite_id)
            except KeyError:
                return payload
            terminal_steps = sum(
                1 for step in suite.steps if step.status not in _ACTIVE_SUITE_STATUSES
            )
            payload.update(
                {
                    "status": suite.status.value,
                    "waiting_input": suite.status == SuiteStatus.WAITING_INPUT,
                    "progress": f"{terminal_steps}/{len(suite.steps)}",
                }
            )
            if suite.status == SuiteStatus.WAITING_INPUT and suite.awaiting_input_run_id:
                payload["otp_run_id"] = suite.awaiting_input_run_id
                payload["otp_request_id"] = await self._run_commands.get_otp_request_id(
                    suite.awaiting_input_run_id
                )
            return payload
        if not schedule.last_run_id:
            return payload
        try:
            run = await self._run_commands.get_run(schedule.last_run_id)
        except KeyError:
            return payload
        countable = [m for m in run.modules if m.status != ModuleStatus.SKIPPED]
        passed = sum(1 for m in countable if m.status == ModuleStatus.PASSED)
        payload.update(
            {
                "status": run.status.value,
                "waiting_input": run.status == RunStatus.WAITING_INPUT,
                "awaiting_prompt": run.awaiting_input_prompt,
                "progress": f"{passed}/{len(countable)}",
            }
        )
        if run.status == RunStatus.WAITING_INPUT:
            payload["otp_run_id"] = run.run_id
            payload["otp_request_id"] = await self._run_commands.get_otp_request_id(run.run_id)
        return payload

    async def submit_trigger_otp(
        self,
        schedule_id: str,
        otp_code: str,
        *,
        expected_execution_id: str | None = None,
        expected_otp_run_id: str | None = None,
        expected_otp_request_id: str | None = None,
    ) -> dict:
        """모바일 트리거 페이지에서 입력한 OTP 를 예약의 최근 실행(Run/Suite)에 전달한다."""
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        execution_id = (
            schedule.last_suite_id if schedule.schedule_kind == "suite" else schedule.last_run_id
        )
        if expected_execution_id is not None and execution_id != expected_execution_id:
            raise ValueError("인증번호를 요청한 실행이 바뀌었습니다.")
        if expected_otp_request_id is not None:
            if not expected_otp_run_id:
                raise ValueError("인증번호 대상이 없습니다.")
            if schedule.schedule_kind == "suite":
                suite = await self._suite_service.get_suite(execution_id)
                if suite.awaiting_input_run_id != expected_otp_run_id:
                    raise ValueError("인증번호를 요청한 Suite 단계가 바뀌었습니다.")
            elif execution_id != expected_otp_run_id:
                raise ValueError("인증번호를 요청한 Run이 바뀌었습니다.")
            await self._run_commands.submit_otp(
                expected_otp_run_id, otp_code, expected_request_id=expected_otp_request_id
            )
            return await self.trigger_status(schedule_id)
        if schedule.schedule_kind == "suite":
            if not schedule.last_suite_id:
                raise KeyError("이 예약으로 실행된 Suite 가 없습니다.")
            await self._suite_service.submit_otp(schedule.last_suite_id, otp_code)
        else:
            if not schedule.last_run_id:
                raise KeyError("이 예약으로 실행된 Run 이 없습니다.")
            await self._run_commands.submit_otp(schedule.last_run_id, otp_code)
        return await self.trigger_status(schedule_id)

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
                logger.exception(
                    "스케줄러 tick 오류", log_event="schedule.tick_error", error=str(exc)
                )
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
            await self._migrate_presets(schedule)
            if (
                schedule.enabled
                and schedule.next_run_at is not None
                and schedule.next_run_at <= now
            ):
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
            paused_until = _ensure_utc(schedule.paused_until)
            if paused_until is not None and paused_until <= now:
                # 일시 중지 기한 경과 → 자동 재개(기획안 C: 사이트 정기점검 후 자동 복귀).
                schedule.paused_until = None
                schedule.record_change("auto_resumed", "일시 중지 기한 경과 — 자동 재개")
                await self._repository.save(schedule)
                paused_until = None
            if not schedule.enabled or schedule.next_run_at is None:
                continue
            if schedule.next_run_at > now:
                continue
            if paused_until is not None:
                # 일시 중지 중에는 발사하지 않고 다음 주기로 미룬다(누락 신호도 남기지 않는다
                # — 의도된 침묵이므로 관제 보드의 '실행 누락'과 구분).
                schedule.next_run_at = self._next_run_from_now(schedule.cron)
                await self._repository.save(schedule)
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
            # 로그에만 있던 skipped_overlap 을 관제 보드('실행 누락/건너뜀')로 노출한다.
            schedule.last_skipped_at = now
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
        systems = await self._prepare_inputs(schedule)
        input_data = systems[schedule.system_code]
        mode = schedule.browser_mode or schedule.input_data.get("browser_mode")
        if mode:
            input_data["browser_mode"] = mode
        run = await self._run_commands.start_run(
            schedule.system_code,
            input_data,
            list(schedule.selected_module_ids)
            if schedule.selected_module_ids is not None
            else None,
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
        systems = await self._prepare_inputs(schedule)
        suite = await self._suite_service.start_suite(
            StartSuiteRequest(
                browser_mode=schedule.browser_mode or "headed",
                systems=systems,
                selected_system_codes=list(schedule.selected_system_codes)
                if schedule.selected_system_codes is not None
                else None,
                scope_system_codes=list(schedule.scope_system_codes)
                if schedule.scope_system_codes is not None
                else None,
            ),
            user_id=actor_id,
            user_name=actor_name,
            triggered_by="schedule",
            schedule_id=schedule.schedule_id,
        )
        schedule.last_suite_id = suite.suite_id
        schedule.last_run_at = datetime.now(UTC)
        schedule.last_suite_status = suite.status
        return suite

    async def _migrate_presets(self, schedule: Schedule) -> None:
        if await self._presets.migrate(schedule):
            await self._repository.save(schedule)

    async def _prepare_inputs(self, schedule: Schedule) -> dict[str, dict[str, str]]:
        await self._migrate_presets(schedule)
        try:
            inputs = await self._presets.resolve(schedule)
            if schedule.schedule_kind == "suite":
                self._suite_service.validate_suite_request(
                    schedule.browser_mode or "headed", inputs, schedule.selected_system_codes
                )
            else:
                self._run_commands.validate_run_request(
                    schedule.system_code, inputs[schedule.system_code], schedule.selected_module_ids
                )
        except ValueError as exc:
            schedule.preparation_error = str(exc)
            await self._repository.save(schedule)
            raise
        if schedule.preparation_error:
            schedule.preparation_error = None
            await self._repository.save(schedule)
        return inputs

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
            run = await self._run_commands.get_run(run_id)
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
            run = await self._run_commands.get_run(schedule.last_run_id)
        except KeyError:
            return
        if schedule.last_run_status != run.status:
            schedule.last_run_status = run.status
            await self._repository.save(schedule)

    def _next_run_from_now(self, cron: str) -> datetime:
        return next_run_after(cron, datetime.now(self._timezone))
