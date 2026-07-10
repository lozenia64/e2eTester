from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from app.core.enums import SuiteStatus
from app.core.logging import get_logger
from app.core.models import (
    Run,
    StartSuiteRequest,
    SuiteEvent,
    SuiteRun,
    SuiteStep,
    SystemDefinition,
)
from app.core.status_labels import (
    SUITE_ANOMALY_STATUSES,
    SUITE_ERROR_STATUSES,
    SUITE_TERMINAL_OUTCOME_STATUSES,
)
from app.domain.suite_aggregate import SuiteAggregate
from app.domain.suite_state_machine import (
    CancelSuite,
    FinalizeSuite,
    RecordAndCancel,
    StartStep,
    SuiteStateMachine,
)
from app.events.bus import EventBus, RunFinished, RunResumed, RunWaitingInput, SuiteFinished
from app.orchestrator.run_command_port import RunCommandPort
from app.orchestrator.suite_view import SuiteView
from app.registry.loader import ModuleRegistry
from app.storage.ports import SuiteControlStorePort, SuiteInputStorePort, SuiteRepositoryPort

logger = get_logger(__name__)


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
        repository: SuiteRepositoryPort,
        event_bus: EventBus,
        cancel_store: SuiteControlStorePort,
        input_store: SuiteInputStorePort,
    ) -> None:
        self._registry = registry
        self._run_commands = run_commands
        self._repository = repository
        self._event_bus = event_bus
        self._cancel_store = cancel_store
        self._input_store = input_store
        # Suite 단위 임계영역 직렬화(이벤트 핸들러/advance 가 같은 Suite 를 동시에 만지지 않게).
        self._locks: dict[str, asyncio.Lock] = {}

    def register(self, event_bus: EventBus) -> None:
        """Saga 가 의존하는 도메인 이벤트 구독을 등록한다(컴포지션 루트에서 호출)."""
        event_bus.subscribe(RunFinished, self.on_run_finished)
        event_bus.subscribe(RunWaitingInput, self.on_run_waiting_input)
        event_bus.subscribe(RunResumed, self.on_run_resumed)

    # --- 조회 -------------------------------------------------------------

    async def get_suite(self, suite_id: str) -> SuiteRun:
        return await self._repository.get_suite(suite_id)

    async def list_suite_summaries(self, limit: int = 20) -> list[dict]:
        suites = await self._repository.list_suites()
        suites.sort(key=lambda suite: suite.requested_at, reverse=True)
        return [self._summarize_suite(suite) for suite in suites[:limit]]

    async def list_suites_by_schedule(self, schedule_id: str, limit: int = 30) -> list[SuiteRun]:
        """특정 예약이 트리거한 Suite 를 최근순으로 돌려준다(예약 상세 이력용)."""
        suites = [
            suite
            for suite in await self._repository.list_suites()
            if suite.schedule_id == schedule_id
        ]
        suites.sort(key=lambda suite: suite.requested_at, reverse=True)
        return suites[:limit]

    async def list_schedule_tagged_suites(self) -> list[SuiteRun]:
        """schedule_id 태깅된 Suite 전체 — 관제 보드/캘린더의 1회 스캔·그룹핑용."""
        return [suite for suite in await self._repository.list_suites() if suite.schedule_id]

    async def reconcile_interrupted_suites(self) -> int:
        """재기동 시 비종료 상태로 남은 Suite 를 CANCELLED 로 정리한다.

        ``RunService.reconcile_interrupted_runs`` 와 같은 이유로, 영속 저장소에서 복원된
        진행 중 Suite 는 이어받을 수 없으므로 종료로 봉인한다(인메모리에서는 no-op).
        봉인 규칙(어떤 상태가 '진행 중'인가)은 도메인 애그리거트가 가진다.
        """
        count = 0
        for suite in await self._repository.list_suites():
            if not SuiteAggregate(suite).seal_interrupted():
                continue
            await self._repository.save_suite(suite)
            await self._cancel_store.delete(suite.suite_id)
            await self._input_store.delete(suite.suite_id)
            count += 1
        return count

    @staticmethod
    def _summarize_suite(suite: SuiteRun) -> dict:
        passed = sum(1 for step in suite.steps if step.status == SuiteStatus.PASSED)
        anomaly = sum(1 for step in suite.steps if step.status in SUITE_ANOMALY_STATUSES)
        error = sum(1 for step in suite.steps if step.status in SUITE_ERROR_STATUSES)
        skipped = sum(1 for step in suite.steps if step.status == SuiteStatus.SKIPPED)
        selected_total = len(suite.steps) - skipped
        return {
            "suite_id": suite.suite_id,
            "status": suite.status,
            "requested_at": suite.requested_at.isoformat(),
            "started_at": suite.started_at.isoformat() if suite.started_at else None,
            "ended_at": suite.ended_at.isoformat() if suite.ended_at else None,
            "step_total": len(suite.steps),
            "step_selected_total": selected_total,
            "step_passed": passed,
            "step_failed": anomaly,
            "step_error": error,
            "step_skipped": skipped,
            "current_step_index": suite.current_step_index,
            "active_run_id": suite.active_run_id,
            "awaiting_input_run_id": suite.awaiting_input_run_id,
        }

    async def subscribe(self, suite_id: str):
        return await self._repository.subscribe(suite_id)

    async def unsubscribe(self, suite_id: str, queue):
        await self._repository.unsubscribe(suite_id, queue)

    # --- 검증 / 입력 병합 -------------------------------------------------

    def _merge_input(
        self, browser_mode: str, system_code: str, systems_input: dict[str, dict[str, str]]
    ) -> dict[str, str]:
        merged = {"browser_mode": browser_mode}
        merged.update(systems_input.get(system_code, {}))
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

        normalized_systems = {key: dict(value) for key, value in (systems or {}).items()}
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
        await self._repository.create_suite(suite)
        # 시스템별 입력값(PII 가능)은 Suite blob 이 아니라 전용 스토어에 보관한다.
        await self._input_store.put(suite_id, normalized_systems)
        await self._publish_event("suite_created", suite)
        logger.info(
            "Suite 생성",
            log_event="suite.created",
            suite_id=suite.suite_id,
            selected_systems=resolved_system_codes,
            user_name=user_name,
        )

        # RUNNING 으로 전이하고 첫 스텝부터 Saga 를 시작한다(이후 진행은 RunFinished 구동).
        SuiteAggregate(suite).begin()
        await self._repository.save_suite(suite)
        await self._publish_event("suite_started", suite)
        logger.info("Suite 시작", log_event="suite.started", suite_id=suite.suite_id)
        await self._advance(suite_id)
        return await self._repository.get_suite(suite_id)

    async def cancel_suite(self, suite_id: str) -> SuiteRun:
        suite = await self._repository.get_suite(suite_id)
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
        suite = await self._repository.get_suite(suite_id)
        if suite.awaiting_input_run_id is None:
            raise KeyError(f"Suite is not waiting for OTP: {suite_id}")
        await self._run_commands.submit_otp(suite.awaiting_input_run_id, otp_code)
        return await self._repository.get_suite(suite_id)

    # --- 이벤트 핸들러(Saga) ---------------------------------------------

    async def on_run_finished(self, event: RunFinished) -> None:
        run = event.run
        if not run.suite_id:
            return
        cancelled = False
        async with self._lock_for(run.suite_id):
            try:
                suite = await self._repository.get_suite(run.suite_id)
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
            aggregate.record_step_result(step, decision.step_status)
            await self._repository.save_suite(suite)
            await self._publish_event("suite_step_finished", suite, {"step_index": index})
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
                suite = await self._repository.get_suite(run.suite_id)
            except KeyError:
                return
            aggregate = SuiteAggregate(suite)
            if aggregate.is_terminal():
                return
            aggregate.mark_waiting_input(run.run_id, run.awaiting_input_prompt)
            await self._repository.save_suite(suite)
            await self._publish_event("suite_waiting_input", suite, {"run_id": run.run_id})
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
                suite = await self._repository.get_suite(run.suite_id)
            except KeyError:
                return
            aggregate = SuiteAggregate(suite)
            if aggregate.is_terminal():
                return
            aggregate.mark_resumed()
            await self._repository.save_suite(suite)
            await self._publish_event("suite_resumed", suite)
            logger.info(
                "Suite 재개", log_event="suite.resumed", suite_id=suite.suite_id, run_id=run.run_id
            )

    # --- 진행 / 종료 ------------------------------------------------------

    async def _advance(self, suite_id: str) -> None:
        """다음 PENDING 스텝의 Run 을 시작한다. 남은 스텝이 없으면 Suite 를 종료한다."""
        finalized: tuple[SuiteRun, SuiteStatus] | None = None
        while True:
            async with self._lock_for(suite_id):
                suite = await self._repository.get_suite(suite_id)
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
                    finalized = (suite, SuiteStatus.CANCELLED)
                    break
                if isinstance(decision, FinalizeSuite):
                    final_status = aggregate.compute_final_status()
                    await self._finalize_locked(aggregate, final_status)
                    finalized = (suite, final_status)
                    break
                assert isinstance(decision, StartStep)

                step = aggregate.start_step(decision.index)
                await self._repository.save_suite(suite)
                await self._publish_event(
                    "suite_step_started", suite, {"step_index": decision.index}
                )

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
                    aggregate.mark_step_error(step)
                    await self._repository.save_suite(suite)
                    await self._publish_event(
                        "suite_step_finished",
                        suite,
                        {"step_index": decision.index, "error": str(exc)},
                    )
                    continue  # 다음 PENDING 스텝으로(락 재획득)

                aggregate.link_run(step, run.run_id)
                await self._repository.save_suite(suite)
                await self._publish_event(
                    "suite_step_run_linked",
                    suite,
                    {"step_index": decision.index, "run_id": run.run_id},
                )
                return  # RunFinished 를 기다린다

        # 종료(락 밖에서 통합 메일용 도메인 이벤트 발행)
        suite, status = finalized
        if status in SUITE_TERMINAL_OUTCOME_STATUSES:
            runs = await self._collect_step_runs(suite)
            await self._event_bus.publish(
                SuiteFinished(suite=suite.model_copy(deep=True), runs=runs)
            )

    async def _finalize_cancelled(self, suite_id: str) -> None:
        async with self._lock_for(suite_id):
            try:
                suite = await self._repository.get_suite(suite_id)
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
        suite = aggregate.suite
        await self._repository.save_suite(suite)
        await self._publish_event("suite_finished", suite)
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

    def _lock_for(self, suite_id: str) -> asyncio.Lock:
        lock = self._locks.get(suite_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[suite_id] = lock
        return lock

    async def _publish_event(
        self, event_type: str, suite: SuiteRun, extra: dict | None = None
    ) -> None:
        # 엔티티를 직접 직렬화하지 않고 읽기 모델 프로젝션을 거친다(RunView 와 동일 규율).
        payload = SuiteView.dump(suite)
        if extra:
            payload.update(extra)
        await self._repository.publish(
            SuiteEvent(
                event_type=event_type,
                suite_id=suite.suite_id,
                suite_status=suite.status,
                payload=payload,
            )
        )
