from __future__ import annotations

import asyncio
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.logging import get_logger
from app.core.models import (
    SUITE_SCHEDULE_SYSTEM_CODE,
    SUITE_SCHEDULE_SYSTEM_NAME,
    CreateScheduleRequest,
    CreateSuiteScheduleRequest,
    Run,
    Schedule,
    StartSuiteRequest,
    SuiteRun,
    UpdateScheduleRequest,
)
from app.core.settings import get_settings
from app.scheduling.cron import next_run_after, parse_cron
from app.scheduling.schedule_center import (
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


def _new_trigger_token() -> str:
    """모바일 즉시 점검 URL 용 예약별 비밀 토큰(URL-safe, 추측 불가)."""
    return secrets.token_urlsafe(24)


def _ensure_utc(moment: datetime | None) -> datetime | None:
    """레거시(naive) 저장 값을 UTC aware 로 강제한다 — 비교/차이 계산 안전장치."""
    if moment is None:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def schedule_today_start_utc() -> datetime:
    """스케줄 타임존 기준 '오늘' 00:00:00 을 UTC 로 반환한다."""
    tz, _ = _resolve_timezone()
    now_local = datetime.now(tz)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return today_start_local.astimezone(UTC)


def schedule_today_label() -> str:
    """스케줄 타임존 기준 '오늘' 날짜 라벨(YYYY-MM-DD)."""
    tz, _ = _resolve_timezone()
    return datetime.now(tz).strftime("%Y-%m-%d")


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
            trigger_token=_new_trigger_token(),
            input_data=sanitized_input,
            selected_module_ids=resolved_module_ids,
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

    async def create_suite_schedule(
        self,
        request: CreateSuiteScheduleRequest,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> Schedule:
        parse_cron(request.cron)  # ValueError -> 400
        browser_mode, normalized_systems, resolved_system_codes = (
            self._suite_service.validate_suite_request(
                request.browser_mode,
                request.systems,
                request.selected_system_codes,
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
            suite_systems=normalized_systems,
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
        return self._augment_summary(schedule.to_detail(), schedule)

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
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        changed: list[str] = []

        if request.name is not None and request.name.strip() != schedule.name:
            schedule.name = request.name.strip()
            changed.append("이름")

        if request.cron is not None and request.cron.strip() != schedule.cron:
            parse_cron(request.cron)  # ValueError -> 400
            schedule.cron = request.cron.strip()
            changed.append(f"주기({cron_to_label(schedule.cron)})")

        if schedule.schedule_kind == "suite":
            if request.browser_mode is not None or request.selected_system_codes is not None:
                browser_mode, normalized_systems, resolved_system_codes = (
                    self._suite_service.validate_suite_request(
                        request.browser_mode or schedule.browser_mode or "headed",
                        dict(schedule.suite_systems or {}),
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
                schedule.suite_systems = normalized_systems
                schedule.selected_system_codes = resolved_system_codes
                schedule.step_total = len(resolved_system_codes)
        else:
            input_changed = bool(
                request.input_data and any(value.strip() for value in request.input_data.values())
            )
            modules_changed = (
                request.selected_module_ids is not None
                and request.selected_module_ids != (schedule.selected_module_ids or [])
            )
            if input_changed or modules_changed:
                merged_input = dict(schedule.input_data)
                if request.input_data:
                    merged_input.update(
                        {
                            key: value.strip()
                            for key, value in request.input_data.items()
                            if value.strip()
                        }
                    )
                sanitized_input, resolved_module_ids = self._run_service.validate_run_request(
                    schedule.system_code,
                    merged_input,
                    request.selected_module_ids
                    if request.selected_module_ids is not None
                    else schedule.selected_module_ids,
                )
                schedule.input_data = sanitized_input
                schedule.selected_module_ids = resolved_module_ids
                if input_changed:
                    changed.append("인증값")
                if modules_changed:
                    changed.append("모듈 선택")

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
        copy = source.model_copy(
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
                "change_log": [],
            }
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
    def _run_point(run: Run) -> ExecutionPoint:
        return ExecutionPoint(
            execution_id=run.run_id,
            kind="run",
            status=run.status.value,
            requested_at=_ensure_utc(run.requested_at),
            started_at=_ensure_utc(run.started_at),
            ended_at=_ensure_utc(run.ended_at),
        )

    @staticmethod
    def _suite_point(suite: SuiteRun) -> ExecutionPoint:
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
        runs = await self._run_service.list_runs_by_schedule(schedule.schedule_id, limit=limit)
        return [self._run_point(run) for run in runs]

    async def _grouped_execution_points(
        self,
    ) -> tuple[dict[str, list[ExecutionPoint]], dict[str, list[ExecutionPoint]]]:
        """Run/Suite 저장소를 각각 1회만 스캔해 ``schedule_id`` 별 실행 포인트(최신순)로
        그룹핑한다 — 보드/캘린더가 예약마다 전체 스캔을 반복(O(#예약 × #Run))하지 않도록
        하는 공용 프리페치."""
        runs_by: dict[str, list[ExecutionPoint]] = {}
        for run in await self._run_service.list_schedule_tagged_runs():
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

        systems = sorted(self._run_service.list_systems(), key=lambda s: (s.display_order, s.name))
        if allowed_system_codes is not None:
            allowed = set(allowed_system_codes)
            systems = [s for s in systems if s.system_code in allowed]
        coverage = build_coverage(
            [(s.system_code, s.name) for s in systems],
            await self._run_service.last_finished_at_by_system(),
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

    async def trigger_now(self, schedule_id: str) -> dict:
        """모바일 트리거 진입점: 즉시 실행하되, 직전 실행이 아직 진행 중이면 **새로 만들지
        않고** 그 실행에 합류한다(페이지 새로고침/중복 탭이 실 사이트 점검을 이중 발사하지
        않게 하는 멱등 가드 — cron 루프의 overlap 스킵과 같은 정책)."""
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        if await self._last_execution_active(schedule):
            payload = await self.trigger_status(schedule_id)
            payload["already_running"] = True
            return payload
        if schedule.schedule_kind == "suite":
            await self._trigger_suite(schedule)
        else:
            await self._trigger_run(schedule)
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
            return payload
        if not schedule.last_run_id:
            return payload
        try:
            run = await self._run_service.get_run(schedule.last_run_id)
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
        return payload

    async def submit_trigger_otp(self, schedule_id: str, otp_code: str) -> dict:
        """모바일 트리거 페이지에서 입력한 OTP 를 예약의 최근 실행(Run/Suite)에 전달한다."""
        schedule = await self._repository.get(schedule_id)  # KeyError -> 404
        if schedule.schedule_kind == "suite":
            if not schedule.last_suite_id:
                raise KeyError("이 예약으로 실행된 Suite 가 없습니다.")
            await self._suite_service.submit_otp(schedule.last_suite_id, otp_code)
        else:
            if not schedule.last_run_id:
                raise KeyError("이 예약으로 실행된 Run 이 없습니다.")
            await self._run_service.submit_otp(schedule.last_run_id, otp_code)
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
        run = await self._run_service.start_run(
            schedule.system_code,
            dict(schedule.input_data),
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
            triggered_by="schedule",
            schedule_id=schedule.schedule_id,
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
