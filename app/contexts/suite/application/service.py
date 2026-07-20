from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from app.contexts.run.application.command_port import RunCommandPort
from app.contexts.scheduling.scheduler import schedule_today_start_utc
from app.contexts.suite.domain.aggregate import SuiteAggregate
from app.contexts.suite.domain.state_machine import (
    CancelSuite,
    FinalizeSuite,
    RecordAndCancel,
    StartStep,
    SuiteStateMachine,
)
from app.core.enums import SuiteStatus
from app.core.logging import get_logger
from app.core.requests import StartSuiteRequest
from app.core.run_models import Run
from app.core.status_labels import (
    SUITE_ANOMALY_STATUSES,
    SUITE_ERROR_STATUSES,
)
from app.core.suite_models import SuiteRun, SuiteStep
from app.core.system_models import SystemDefinition
from app.platform.eventing.bus import EventBus, RunFinished, RunResumed, RunWaitingInput
from app.realtime.ports import SuiteRealtimeNotificationPort
from app.registry.loader import ModuleRegistry
from app.storage.ports import (
    SuiteControlStorePort,
    SuiteInputStorePort,
    SuiteReadRepositoryPort,
    SuiteSummaryQueryPort,
    SuiteWriteRepositoryPort,
)
from app.storage.query_rows import SuiteSummaryRow

logger = get_logger(__name__)

ACTIVE_SUITE_STATUSES = frozenset(
    {SuiteStatus.PENDING, SuiteStatus.RUNNING, SuiteStatus.WAITING_INPUT}
)


def _suite_finished_statuses() -> frozenset[SuiteStatus]:
    return frozenset(status for status in SuiteStatus if status not in ACTIVE_SUITE_STATUSES)


class SuiteService:
    """전체 시스템 순차 점검(Suite)을 **이벤트 기반 Saga(프로세스 매니저)** 로 진행한다.

    이 클래스는 *순서*(스텝 시작 → ``RunFinished`` 대기 → 다음 스텝)와 *부작용*(영속·WebSocket
    이벤트 발행·하위 Run 명령)만 책임진다. "무엇이 합법한 상태 전이인가"라는 **결정 규칙** 은
    순수 ``SuiteStateMachine`` 에, **상태 변경·불변식** 은 도메인 애그리거트 ``SuiteAggregate``
    에 위임한다 — 둘 다 I/O 없이 단독으로 단위 테스트된다(``RunStateMachine``/``RunAggregate``
    와 동형). 과거 이 서비스 곳곳에 흩어져 있던 ``suite.status = ...`` / ``step.status = ...``
    인라인 변이는 모두 애그리거트로 옮겨졌다.

    하위 Run 의 종료/일시정지/재개는 ``EventBus`` 의 도메인 이벤트
    (``RunFinished``/``RunWaitingInput``/``RunResumed``)로 감지한다 — 폴링도, 프레젠테이션(WS)
    큐 구독도 없다. 하위 Run 을 구동하는 의존성은 구체 ``RunService`` 가 아니라 **명령 포트**
    (``RunCommandPort``)다 — 사가가 애플리케이션 서비스에 용접되지 않는다. Suite 취소 의도는
    영속 ``SuiteControlStorePort`` 가, 시스템별 입력값은 ``SuiteInputStorePort`` 가 소유한다.
    """

    def __init__(
        self,
        registry: ModuleRegistry,
        run_commands: RunCommandPort,
        write_repo: SuiteWriteRepositoryPort,
        read_repo: SuiteReadRepositoryPort,
        realtime: SuiteRealtimeNotificationPort,
        event_bus: EventBus,
        cancel_store: SuiteControlStorePort,
        input_store: SuiteInputStorePort,
        summary_query: SuiteSummaryQueryPort,
    ) -> None:
        self._registry = registry
        self._run_commands = run_commands
        self._write_repo = write_repo
        self._read_repo = read_repo
        self._realtime = realtime
        self._event_bus = event_bus
        self._cancel_store = cancel_store
        self._input_store = input_store
        # 목록/보드 질의는 blob 스캔이 아니라 suite_history_index 프로젝션 행으로만 답한다.
        self._summary_query = summary_query
        # Suite 단위 임계영역 직렬화(이벤트 핸들러/advance 가 같은 Suite 를 동시에 만지지 않게).
        self._locks: dict[str, asyncio.Lock] = {}

    def register(self, event_bus: EventBus) -> None:
        """Saga 가 의존하는 도메인 이벤트 구독을 등록한다(컴포지션 루트에서 호출)."""
        event_bus.subscribe(RunFinished, self.on_run_finished)
        event_bus.subscribe(RunWaitingInput, self.on_run_waiting_input)
        event_bus.subscribe(RunResumed, self.on_run_resumed)

    # --- 조회 -------------------------------------------------------------

    async def get_suite(self, suite_id: str) -> SuiteRun:
        return await self._read_repo.get_suite(suite_id)

    async def list_suite_summaries(
        self,
        *,
        limit: int = 20,
        scope: Literal["today", "before_today"] | None = None,
    ) -> list[dict]:
        rows = await self._summary_rows_for_scope(scope=scope, limit=limit)
        return [self._summarize_suite_row(row) for row in rows]

    async def _summary_rows_for_scope(
        self,
        *,
        scope: Literal["today", "before_today"] | None,
        limit: int,
    ) -> list[SuiteSummaryRow]:
        if scope == "today":
            today_start = schedule_today_start_utc()
            active_rows = await self._summary_query.list_summaries(
                limit=limit,
                statuses=ACTIVE_SUITE_STATUSES,
            )
            remaining = max(0, limit - len(active_rows))
            finished_rows: list[SuiteSummaryRow] = []
            if remaining:
                finished_rows = await self._summary_query.list_summaries(
                    limit=remaining,
                    requested_since=today_start,
                    statuses=_suite_finished_statuses(),
                )
            return active_rows + finished_rows

        if scope == "before_today":
            return await self._summary_query.list_summaries(
                limit=limit,
                requested_before=schedule_today_start_utc(),
                statuses=_suite_finished_statuses(),
            )

        return await self._summary_query.list_summaries(limit=limit)

    async def list_suites_by_schedule(
        self, schedule_id: str, limit: int = 30
    ) -> list[SuiteSummaryRow]:
        """특정 예약이 트리거한 Suite 를 최근순으로 돌려준다(예약 상세 이력용)."""
        rows = await self._summary_query.list_summaries()
        return [row for row in rows if row.schedule_id == schedule_id][:limit]

    async def list_schedule_tagged_suites(self) -> list[SuiteSummaryRow]:
        """schedule_id 태깅된 Suite 전체 — 관제 보드/캘린더의 1회 조회·그룹핑용."""
        rows = await self._summary_query.list_summaries()
        return [row for row in rows if row.schedule_id]

    async def reconcile_interrupted_suites(self) -> int:
        """재기동 시 비종료 상태로 남은 Suite 를 CANCELLED 로 정리한다.

        ``RunService.reconcile_interrupted_runs`` 와 같은 이유로, 영속 저장소에서 복원된
        진행 중 Suite 는 이어받을 수 없으므로 종료로 봉인한다. 후보는 요약 인덱스에서
        진행 중 상태만 골라내고, 봉인 자체는 단건 애그리거트 로드(쓰기 경로)로 수행한다.
        봉인 규칙(어떤 상태가 '진행 중'인가)은 도메인 애그리거트가 가진다.
        """
        active = {SuiteStatus.PENDING, SuiteStatus.RUNNING, SuiteStatus.WAITING_INPUT}
        count = 0
        for row in await self._summary_query.list_summaries():
            if row.status not in active:
                continue
            suite = await self._read_repo.get_suite(row.suite_id)
            aggregate = SuiteAggregate(suite)
            if not aggregate.seal_interrupted():
                continue
            await self._persist(suite, aggregate)
            await self._cancel_store.delete(suite.suite_id)
            await self._input_store.delete(suite.suite_id)
            count += 1
        return count

    @staticmethod
    def _summarize_suite_row(row: SuiteSummaryRow) -> dict:
        passed = sum(1 for step in row.steps if step.status == SuiteStatus.PASSED)
        anomaly = sum(1 for step in row.steps if step.status in SUITE_ANOMALY_STATUSES)
        error = sum(1 for step in row.steps if step.status in SUITE_ERROR_STATUSES)
        skipped = sum(1 for step in row.steps if step.status == SuiteStatus.SKIPPED)
        selected_total = len(row.steps) - skipped
        return {
            "suite_id": row.suite_id,
            "status": row.status,
            "requested_at": row.requested_at.isoformat(),
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
            "step_total": row.step_total,
            "step_selected_total": selected_total,
            "step_passed": passed,
            "step_failed": anomaly,
            "step_error": error,
            "step_skipped": skipped,
            "current_step_index": row.current_step_index,
            "active_run_id": row.active_run_id,
            "awaiting_input_run_id": row.awaiting_input_run_id,
        }

    async def subscribe(self, suite_id: str):
        return await self._realtime.subscribe(suite_id)

    async def unsubscribe(self, suite_id: str, queue):
        await self._realtime.unsubscribe(suite_id, queue)

    async def load_suite_finished_payload(self, suite_id: str) -> tuple[SuiteRun, list[Run]]:
        suite = await self._read_repo.get_suite(suite_id)
        runs = await self._collect_step_runs(suite)
        return suite.model_copy(deep=True), runs

    # --- 검증 / 입력 병합 -------------------------------------------------

    @staticmethod
    def _normalize_systems_input(
        systems: dict[str, dict[str, str]] | None,
    ) -> dict[str, dict[str, str]]:
        """시스템별 입력에서 browser_mode 를 제거한다.

        브라우저 모드는 Suite 수준(suite.browser_mode)에서만 결정한다. 프리셋·레거시
        예약 데이터에 남아 있는 per-system browser_mode 가 Run 입력을 덮어쓰지 않게 한다.
        """
        normalized = {key: dict(value) for key, value in (systems or {}).items()}
        for per_system in normalized.values():
            per_system.pop("browser_mode", None)
        return normalized

    def _merge_input(
        self, browser_mode: str, system_code: str, systems_input: dict[str, dict[str, str]]
    ) -> dict[str, str]:
        merged = dict(systems_input.get(system_code, {}))
        merged.pop("browser_mode", None)
        merged["browser_mode"] = browser_mode
        return merged

    @staticmethod
    def _resolve_selected_system_codes(
        systems: list[SystemDefinition],
        selected_system_codes: list[str] | None,
    ) -> list[str]:
        ordered_codes = [system.system_code for system in systems]
        if selected_system_codes is None:
            return ordered_codes

        selected_values: list[str] = []
        seen_codes: set[str] = set()
        for raw_code in selected_system_codes:
            code = raw_code.strip().lower()
            if not code or code in seen_codes:
                continue
            selected_values.append(code)
            seen_codes.add(code)

        if not selected_values:
            raise ValueError("최소 1개 시스템을 선택해야 합니다.")

        known_codes = set(ordered_codes)
        unknown_codes = [code for code in selected_values if code not in known_codes]
        if unknown_codes:
            joined = ", ".join(unknown_codes)
            raise ValueError(f"알 수 없는 시스템이 선택되었습니다: {joined}")

        selected_set = set(selected_values)
        return [code for code in ordered_codes if code in selected_set]

    @staticmethod
    def _resolve_scope_system_codes(
        systems: list[SystemDefinition],
        scope_system_codes: list[str] | None,
    ) -> list[str]:
        ordered_codes = [system.system_code for system in systems]
        if scope_system_codes is None:
            return ordered_codes

        scope_set: set[str] = set()
        for raw_code in scope_system_codes:
            code = raw_code.strip().lower()
            if code:
                scope_set.add(code)

        known_codes = set(ordered_codes)
        unknown_codes = [code for code in scope_set if code not in known_codes]
        if unknown_codes:
            joined = ", ".join(unknown_codes)
            raise ValueError(f"알 수 없는 시스템이 범위에 포함되었습니다: {joined}")

        return [code for code in ordered_codes if code in scope_set]

    def validate_suite_request(
        self,
        browser_mode: str,
        systems: dict[str, dict[str, str]],
        selected_system_codes: list[str] | None = None,
    ) -> tuple[str, dict[str, dict[str, str]], list[str]]:
        registered = self._registry.list_systems()
        if not registered:
            raise ValueError("등록된 시스템이 없습니다.")

        normalized_mode = (browser_mode or "headed").strip()
        if normalized_mode not in {"headed", "headless"}:
            raise ValueError("browser_mode는 headed 또는 headless 여야 합니다.")

        normalized_systems = self._normalize_systems_input(systems)
        resolved_system_codes = self._resolve_selected_system_codes(
            registered, selected_system_codes
        )
        selected_set = set(resolved_system_codes)
        for system in registered:
            if system.system_code not in selected_set:
                continue
            merged_input = self._merge_input(
                normalized_mode, system.system_code, normalized_systems
            )
            self._run_commands.validate_run_request(
                system.system_code, merged_input, selected_module_ids=None
            )
        return normalized_mode, normalized_systems, resolved_system_codes

    # --- 명령 ------------------------------------------------------------

    async def start_suite(
        self,
        request: StartSuiteRequest,
        user_id: str | None = None,
        user_name: str | None = None,
        triggered_by: str = "manual",
        schedule_id: str | None = None,
    ) -> SuiteRun:
        systems = self._registry.list_systems()
        if not systems:
            raise ValueError("등록된 시스템이 없습니다.")

        browser_mode, normalized_systems, resolved_system_codes = self.validate_suite_request(
            request.browser_mode,
            request.systems,
            request.selected_system_codes,
        )
        selected_set = set(resolved_system_codes)
        scope_codes = self._resolve_scope_system_codes(systems, request.scope_system_codes)
        system_by_code = {system.system_code: system for system in systems}

        steps: list[SuiteStep] = []
        for index, code in enumerate(scope_codes):
            system = system_by_code[code]
            is_selected = code in selected_set
            steps.append(
                SuiteStep(
                    system_code=system.system_code,
                    system_name=system.name,
                    order=index,
                    module_total=len(system.modules),
                    status=SuiteStatus.PENDING if is_selected else SuiteStatus.SKIPPED,
                )
            )

        suite_id = f"suite_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        suite = SuiteRun(
            suite_id=suite_id,
            status=SuiteStatus.PENDING,
            steps=steps,
            requested_at=datetime.now(UTC),
            browser_mode=browser_mode,
            selected_system_codes=resolved_system_codes,
            created_by_user_id=user_id,
            created_by_user_name=user_name,
            triggered_by=triggered_by,
            schedule_id=schedule_id,
        )
        aggregate = SuiteAggregate.for_new_suite(suite)
        await self._write_repo.create_suite(suite, events=aggregate.pull_events())
        # 시스템별 입력값(PII 가능)은 Suite blob 이 아니라 전용 스토어에 보관한다.
        await self._input_store.put(suite_id, normalized_systems)
        logger.info(
            "Suite 생성",
            log_event="suite.created",
            suite_id=suite.suite_id,
            selected_systems=resolved_system_codes,
            user_name=user_name,
        )

        # RUNNING 으로 전이하고 첫 스텝부터 Saga 를 시작한다(이후 진행은 RunFinished 구동).
        begin_aggregate = SuiteAggregate(suite)
        begin_aggregate.begin()
        await self._persist(suite, begin_aggregate)
        logger.info("Suite 시작", log_event="suite.started", suite_id=suite.suite_id)
        await self._advance(suite_id)
        return await self._read_repo.get_suite(suite_id)

    async def cancel_suite(self, suite_id: str) -> SuiteRun:
        suite = await self._read_repo.get_suite(suite_id)
        if SuiteAggregate(suite).is_terminal():
            raise ValueError("이미 종료된 전체 점검은 취소할 수 없습니다.")
        # 취소 의도를 영속한다 — 활성 Run 취소가 비동기로 마무리되거나, 다음 스텝 진입 직전
        # advance 가 이 플래그를 읽어 협력적으로 중단한다.
        await self._cancel_store.set_cancel_requested(suite_id)
        logger.info(
            "Suite 취소 요청",
            log_event="suite.cancel_requested",
            suite_id=suite_id,
            status=suite.status.value,
        )
        active_run_id = suite.active_run_id
        if active_run_id:
            try:
                await self._run_commands.cancel_run(active_run_id)
            except (KeyError, ValueError):
                pass
            # 활성 Run 취소 → RunFinished(CANCELLED) → on_run_finished 가 Suite 를 마무리한다.
        else:
            # 활성 Run 이 없으면(스텝 사이) 여기서 바로 취소 마무리.
            await self._finalize_cancelled(suite_id)
        return suite

    async def submit_otp(self, suite_id: str, otp_code: str) -> SuiteRun:
        suite = await self._read_repo.get_suite(suite_id)
        if suite.awaiting_input_run_id is None:
            raise KeyError(f"Suite is not waiting for OTP: {suite_id}")
        await self._run_commands.submit_otp(suite.awaiting_input_run_id, otp_code)
        return await self._read_repo.get_suite(suite_id)

    # --- 이벤트 핸들러(Saga) ---------------------------------------------

    async def on_run_finished(self, event: RunFinished) -> None:
        run = event.run
        if not run.suite_id:
            return
        cancelled = False
        async with self._lock_for(run.suite_id):
            try:
                suite = await self._read_repo.get_suite(run.suite_id)
            except KeyError:
                return
            aggregate = SuiteAggregate(suite)
            if aggregate.is_terminal():
                return
            index, step = aggregate.find_step(run.run_id)
            if step is None or aggregate.is_step_terminal(step):
                return
            # 결정(스텝 상태 매핑 + 전진/취소)은 순수 상태머신이, 변경은 애그리거트가 한다.
            decision = SuiteStateMachine.decide_after_run_finished(
                run_status=run.status,
                cancel_requested=await self._cancel_store.is_cancel_requested(run.suite_id),
            )
            aggregate.record_step_result(step, decision.step_status, step_index=index)
            await self._persist(suite, aggregate)
            cancelled = isinstance(decision, RecordAndCancel)
        if cancelled:
            await self._finalize_cancelled(run.suite_id)
        else:
            await self._advance(run.suite_id)

    async def on_run_waiting_input(self, event: RunWaitingInput) -> None:
        run = event.run
        if not run.suite_id:
            return
        async with self._lock_for(run.suite_id):
            try:
                suite = await self._read_repo.get_suite(run.suite_id)
            except KeyError:
                return
            aggregate = SuiteAggregate(suite)
            if aggregate.is_terminal():
                return
            aggregate.mark_waiting_input(run.run_id, run.awaiting_input_prompt)
            await self._persist(suite, aggregate)
            logger.info(
                "Suite OTP 대기",
                log_event="suite.waiting_input",
                suite_id=suite.suite_id,
                run_id=run.run_id,
            )

    async def on_run_resumed(self, event: RunResumed) -> None:
        run = event.run
        if not run.suite_id:
            return
        async with self._lock_for(run.suite_id):
            try:
                suite = await self._read_repo.get_suite(run.suite_id)
            except KeyError:
                return
            aggregate = SuiteAggregate(suite)
            if aggregate.is_terminal():
                return
            aggregate.mark_resumed()
            await self._persist(suite, aggregate)
            logger.info(
                "Suite 재개", log_event="suite.resumed", suite_id=suite.suite_id, run_id=run.run_id
            )

    # --- 진행 / 종료 ------------------------------------------------------

    async def _advance(self, suite_id: str) -> None:
        """다음 PENDING 스텝의 Run 을 시작한다. 남은 스텝이 없으면 Suite 를 종료한다."""
        finalized: SuiteStatus | None = None
        while True:
            async with self._lock_for(suite_id):
                suite = await self._read_repo.get_suite(suite_id)
                aggregate = SuiteAggregate(suite)
                if aggregate.is_terminal():
                    return
                # 결정(취소/종료/다음 스텝)은 순수 상태머신이, 변경은 애그리거트가 한다.
                decision = SuiteStateMachine.decide_advance(
                    cancel_requested=await self._cancel_store.is_cancel_requested(suite_id),
                    next_pending_index=aggregate.next_pending_index(),
                )
                if isinstance(decision, CancelSuite):
                    await self._finalize_locked(
                        aggregate, SuiteStatus.CANCELLED, cancel_remaining=True
                    )
                    finalized = SuiteStatus.CANCELLED
                    break
                if isinstance(decision, FinalizeSuite):
                    final_status = aggregate.compute_final_status()
                    await self._finalize_locked(aggregate, final_status)
                    finalized = final_status
                    break
                assert isinstance(decision, StartStep)

                step = aggregate.start_step(decision.index)
                await self._persist(suite, aggregate)

                systems_input = await self._input_store.get(suite_id) or {}
                merged_input = self._merge_input(
                    suite.browser_mode, step.system_code, systems_input
                )
                try:
                    run = await self._run_commands.start_run(
                        step.system_code,
                        merged_input,
                        selected_module_ids=None,
                        triggered_by="suite",
                        suite_id=suite_id,
                        user_id=suite.created_by_user_id,
                        user_name=suite.created_by_user_name,
                    )
                except (KeyError, ValueError) as exc:
                    aggregate.mark_step_error(step, step_index=decision.index, error=str(exc))
                    await self._persist(suite, aggregate)
                    continue  # 다음 PENDING 스텝으로(락 재획득)

                aggregate.link_run(step, run.run_id)
                await self._persist(suite, aggregate)
                return  # RunFinished 를 기다린다

        # SuiteFinished 도메인 이벤트 → OutboxRelay → EventBus(통합 메일) 가 처리한다.
        _ = finalized

    async def _finalize_cancelled(self, suite_id: str) -> None:
        async with self._lock_for(suite_id):
            try:
                suite = await self._read_repo.get_suite(suite_id)
            except KeyError:
                return
            aggregate = SuiteAggregate(suite)
            if aggregate.is_terminal():
                return
            await self._finalize_locked(aggregate, SuiteStatus.CANCELLED, cancel_remaining=True)
        # CANCELLED 는 통합 메일 대상이 아니므로 SuiteFinished 도메인 이벤트를 발행하지 않는다.

    async def _finalize_locked(
        self,
        aggregate: SuiteAggregate,
        status: SuiteStatus,
        cancel_remaining: bool = False,
    ) -> None:
        """락을 쥔 상태에서 Suite 를 종료로 봉인한다(SuiteFinished 발행은 호출자 책임)."""
        aggregate.finalize(status, cancel_remaining=cancel_remaining)
        suite = aggregate.persistable_state()
        await self._persist(suite, aggregate)
        await self._cancel_store.delete(suite.suite_id)
        await self._input_store.delete(suite.suite_id)
        logger.info(
            "Suite 종료",
            log_event="suite.finished",
            suite_id=suite.suite_id,
            status=status.value,
        )

    async def _collect_step_runs(self, suite: SuiteRun) -> list[Run]:
        runs: list[Run] = []
        for step in suite.steps:
            if not step.run_id:
                continue
            try:
                runs.append(await self._run_commands.get_run(step.run_id))
            except KeyError:
                continue
        return runs

    # --- 내부 헬퍼 --------------------------------------------------------

    async def _persist(self, suite: SuiteRun, aggregate: SuiteAggregate | None = None) -> None:
        events = aggregate.pull_events() if aggregate is not None else []
        await self._write_repo.save_suite(suite, events=events)

    def _lock_for(self, suite_id: str) -> asyncio.Lock:
        lock = self._locks.get(suite_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[suite_id] = lock
        return lock
