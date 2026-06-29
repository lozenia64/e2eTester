from __future__ import annotations

import asyncio
import functools
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from app.core.enums import ModuleStatus, RunStatus
from app.core.logging import get_logger, log_context
from app.core.models import Run, RunModule
from app.domain.run_aggregate import RunAggregate
from app.domain.run_state_machine import (
    BlockModule,
    CancelRemaining,
    CompleteStep,
    ExecuteModule,
    PauseForInput,
    RejectUnexpectedInput,
    RunStateMachine,
)
from app.events.bus import EventBus, RunFinished, RunResumed, RunWaitingInput
from app.execution.gateway import ExecutionGateway, ExecutionHandle
from app.orchestrator.run_comparator import RunComparator
from app.orchestrator.run_event_publisher import RunEventPublisher
from app.orchestrator.run_planner import RunPlanner
from app.orchestrator.run_summary import summarize_run
from app.registry.loader import ModuleRegistry
from app.runner.artifact_manager import ArtifactManager
from app.scheduling.scheduler import schedule_today_start_utc
from app.storage.ports import (
    RunControlStorePort,
    RunInputStorePort,
    RunLogStorePort,
    RunRepositoryPort,
)

if TYPE_CHECKING:
    from app.execution.run_queue import JobQueue
    from app.orchestrator.run_actor import ActorContext

logger = get_logger(__name__)


class RunService:
    """Run 의 생명주기를 관장하는 오케스트레이터(애플리케이션 서비스).

    책임은 *실행 순서*와 *부작용 조율*(영속·이벤트 발행·게이트웨이 호출)로 한정한다. "무엇이
    합법한 상태 전이인가"라는 규칙·불변식·상태 변경은 도메인 애그리거트 ``RunAggregate``
    (``app/domain/run_aggregate.py``)에 위임한다 — 그 결정/변경은 I/O 없이 단독으로 단위
    테스트된다. 실제 브라우저 구동·스레드 모델·런타임 수명은 ``ExecutionGateway`` 포트에,
    검증·계획은 ``RunPlanner`` 에, 이력 비교는 ``RunComparator`` 에, AI 실패 분석·종료 메일
    같은 부수 관심사는 ``EventBus`` 구독자에게 위임한다. 외부로 나가는 Run 본문은 ``RunView``
    프로젝션을 거친다. 이 클래스는 Playwright/스레드/Gemini/SMTP 를 전혀 import 하지 않는다.
    """

    def __init__(
        self,
        registry: ModuleRegistry,
        repository: RunRepositoryPort,
        log_store: RunLogStorePort,
        execution_gateway: ExecutionGateway,
        event_bus: EventBus,
        control_store: RunControlStorePort,
        input_store: RunInputStorePort,
        run_queue: JobQueue,
        comparator: RunComparator | None = None,
        planner: RunPlanner | None = None,
        artifact_manager: ArtifactManager | None = None,
    ) -> None:
        self._registry = registry
        self._repository = repository
        self._log_store = log_store
        self._gateway = execution_gateway
        self._event_bus = event_bus
        # 실행 코루틴은 더 이상 fire-and-forget asyncio.create_task 가 아니라, 감독되는 작업
        # 큐(워커 풀 · 예외 격리 · 동시성 제한 · 수명 관리)에 제출한다.
        self._run_queue = run_queue
        self._comparator = comparator or RunComparator(repository)
        self._planner = planner or RunPlanner()
        self._events = RunEventPublisher(repository)
        self._artifact_manager = artifact_manager or ArtifactManager()
        # 제어 상태(취소 의도·OTP 재개 컨텍스트)는 더 이상 서비스-인스턴스 메모리 dict 가 아니라
        # 영속 스토어(권위 있는 단일 출처)가 소유한다. PII 입력값도 전용 스토어로 분리한다.
        # 둘 다 Run blob 에 들어가지 않아 WebSocket/응답 payload 로 새지 않는다. 두 스토어 모두
        # 포트로만 의존하며 구체 어댑터 선택은 컴포지션 루트(app/main.py)가 독점한다(코어는
        # 어떤 구체 어댑터도 import 하지 않는다).
        self._control_store = control_store
        self._input_store = input_store

    # --- 조회 -------------------------------------------------------------

    def list_systems(self):
        return self._registry.list_systems()

    def get_system(self, system_code: str):
        return self._registry.get_system(system_code)

    async def get_run(self, run_id: str) -> Run:
        """단일 Run 의 **읽기 모델**(상태 + 로그 하이드레이션)을 돌려준다.

        영속 Run blob 에는 로그가 없으므로(별도 로그 스토어 소유), 여기서 ``RunLogStorePort``
        의 로그를 모듈에 채워 넣어 스냅샷/상세 화면/실패 분석이 기대하는 형태로 조립한다.
        내부 쓰기 경로는 이 메서드가 아니라 ``self._repository.get_run`` 을 직접 써서 로그
        하이드레이션 비용을 치르지 않는다(write-model).
        """
        run = await self._repository.get_run(run_id)
        await self._attach_logs(run)
        return run

    async def _attach_logs(self, run: Run) -> None:
        """로그 스토어의 로그를 Run 의 각 모듈에 하이드레이션한다(읽기 모델 조립)."""
        logs_by_module = await self._log_store.get_all(run.run_id)
        for module in run.modules:
            module.logs = logs_by_module.get(module.module_id, [])

    async def list_run_summaries(
        self,
        limit: int = 50,
        user_id: str | None = None,
        system_code: str | None = None,
        user_name_query: str | None = None,
        actor_context: ActorContext | None = None,
        run_status: RunStatus | None = None,
        run_statuses: frozenset[RunStatus] | None = None,
        scope: Literal["today", "before_today"] | None = None,
    ) -> list[dict]:
        if user_id is not None:
            runs = await self._repository.list_runs_by_user(user_id)
        else:
            runs = await self._repository.list_runs()
        runs.sort(key=lambda run: run.requested_at, reverse=True)

        active_statuses = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT}
        today_start_utc = schedule_today_start_utc() if scope is not None else None

        normalized_name_query = (user_name_query or "").strip().casefold()

        def _matches_filters(run: Run, summary: dict) -> bool:
            if run_statuses is not None and run.status not in run_statuses:
                return False
            if run_status is not None and run.status != run_status:
                return False
            if system_code and summary.get("system_code") != system_code:
                return False
            if normalized_name_query:
                actor_name = (summary.get("created_by_user_name") or "").casefold()
                if normalized_name_query not in actor_name:
                    return False
            return True

        def _run_at_utc(run: Run) -> datetime:
            return (
                run.requested_at
                if run.requested_at.tzinfo is not None
                else run.requested_at.replace(tzinfo=UTC)
            )

        if scope == "today":
            active_summaries: list[dict] = []
            today_finished_summaries: list[dict] = []
            for run in runs:
                run_at = _run_at_utc(run)
                is_active = run.status in active_statuses
                if not is_active and run_at < today_start_utc:
                    continue
                summary = summarize_run(run, actor_context=actor_context)
                if not _matches_filters(run, summary):
                    continue
                if is_active:
                    active_summaries.append(summary)
                else:
                    today_finished_summaries.append(summary)
            remaining = max(0, limit - len(active_summaries))
            return active_summaries + today_finished_summaries[:remaining]

        summaries: list[dict] = []
        for run in runs:
            if scope is not None:
                run_at = _run_at_utc(run)
                is_active = run.status in active_statuses
                if scope == "before_today":
                    if is_active or run_at >= today_start_utc:
                        continue
            summary = summarize_run(run, actor_context=actor_context)
            if not _matches_filters(run, summary):
                continue
            summaries.append(summary)
            if len(summaries) >= limit:
                break
        return summaries

    async def delete_run(self, run_id: str) -> None:
        run = await self._repository.get_run(run_id)
        if run.status in {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT}:
            raise ValueError("진행 중인 Run은 삭제할 수 없습니다. 먼저 취소해 주세요.")
        if await self._control_store.get_pending(run_id) is not None:
            raise ValueError("진행 중인 Run은 삭제할 수 없습니다. 먼저 취소해 주세요.")

        await self._log_store.delete_by_run_id(run_id)
        await self._repository.delete_run(run_id)
        self._artifact_manager.delete_run_artifacts(run_id)
        await self._input_store.delete(run_id)
        await self._control_store.delete(run_id)

    async def purge_runs(
        self,
        *,
        statuses: frozenset[RunStatus],
        requested_before: datetime | None = None,
    ) -> list[str]:
        """지정 상태의 종료 Run 을 일괄 삭제한다(보존 정리 배치용).

        ``requested_before`` 가 있으면 해당 시각 이전에 요청된 Run 만 대상으로 한다.
        진행 중(PENDING/RUNNING/WAITING_INPUT) Run 과 OTP 대기 중인 Run 은 건너뛴다.
        """
        deleted: list[str] = []
        active = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT}
        cutoff_utc = None
        if requested_before is not None:
            cutoff_utc = (
                requested_before
                if requested_before.tzinfo is not None
                else requested_before.replace(tzinfo=UTC)
            )
        for run in await self._repository.list_runs():
            if run.status not in statuses or run.status in active:
                continue
            if cutoff_utc is not None:
                run_at = (
                    run.requested_at
                    if run.requested_at.tzinfo is not None
                    else run.requested_at.replace(tzinfo=UTC)
                )
                if run_at >= cutoff_utc:
                    continue
            if await self._control_store.get_pending(run.run_id) is not None:
                continue
            await self._log_store.delete_by_run_id(run.run_id)
            await self._repository.delete_run(run.run_id)
            self._artifact_manager.delete_run_artifacts(run.run_id)
            await self._input_store.delete(run.run_id)
            await self._control_store.delete(run.run_id)
            deleted.append(run.run_id)
        return deleted

    async def reconcile_interrupted_runs(self) -> int:
        """재기동 시 비종료 상태로 남은 Run 을 CANCELLED 로 정리한다.

        영속 저장소(SQLite)를 쓰면 서버가 내려갈 때 RUNNING/WAITING_INPUT 이던 Run 이
        그대로 복원된다. 하지만 그 Run 이 쓰던 브라우저 세션·OTP 대기 핸들은 프로세스와 함께
        사라졌으므로 이어받을 수 없다. 좀비 상태를 막기 위해 종료로 봉인한다(필요하면 사용자가
        ``rerun`` 으로 다시 실행). 인메모리 저장소에서는 복원될 Run 이 없어 no-op 이다.
        """
        count = 0
        for run in await self._repository.list_runs():
            if not RunAggregate(run).seal_interrupted():
                continue
            await self._repository.save_run(run)
            # 재기동으로 죽은 브라우저를 가리키던 dangling 세션 토큰을 정리한다(영속 제어 스토어
            # 사용 시 재기동 후에도 남아 있을 수 있다). 입력값은 보존돼 rerun 에 쓰인다.
            await self._control_store.clear_pending(run.run_id)
            count += 1
        return count

    async def subscribe(self, run_id: str):
        return await self._repository.subscribe(run_id)

    async def unsubscribe(self, run_id: str, queue):
        await self._repository.unsubscribe(run_id, queue)

    # --- 명령(요청 처리) --------------------------------------------------

    def validate_run_request(
        self,
        system_code: str,
        input_data: dict[str, str] | None = None,
        selected_module_ids: list[str] | None = None,
    ) -> tuple[dict[str, str], list[str]]:
        """Run 을 실제로 만들지 않고 입력값·모듈 선택·인증 수단만 검증한다.

        예약(Schedule)/Suite 등록 시 잘못된 조합을 등록 단계에서 거르기 위해 쓴다.
        """
        system = self.get_system(system_code)
        return self._planner.prepare(system, input_data, selected_module_ids)

    async def start_run(
        self,
        system_code: str,
        input_data: dict[str, str] | None = None,
        selected_module_ids: list[str] | None = None,
        triggered_by: str = "manual",
        schedule_id: str | None = None,
        suite_id: str | None = None,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> Run:
        system = self.get_system(system_code)
        run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        sanitized_input, resolved_selected_module_ids = self._planner.prepare(
            system, input_data, selected_module_ids
        )
        run = Run(
            run_id=run_id,
            system_code=system.system_code,
            system_name=system.name,
            status=RunStatus.PENDING,
            requested_at=datetime.now(UTC),
            modules=self._planner.build_run_modules(system, resolved_selected_module_ids),
            selected_module_ids=resolved_selected_module_ids,
            triggered_by=triggered_by,
            schedule_id=schedule_id,
            suite_id=suite_id,
            created_by_user_id=user_id,
            created_by_user_name=user_name,
        )
        await self._input_store.put(run_id, dict(sanitized_input))
        await self._repository.create_run(run)
        await self._events.run_event("run_created", run)
        logger.info(
            "Run 생성",
            log_event="run.created",
            run_id=run.run_id,
            system_code=run.system_code,
            triggered_by=run.triggered_by,
            suite_id=run.suite_id,
            schedule_id=run.schedule_id,
            user_name=run.created_by_user_name,
        )
        await self._run_queue.submit(
            functools.partial(self._execute_run, run.run_id, sanitized_input),
            label=f"run:{run.run_id}",
        )
        return run

    async def submit_otp(self, run_id: str, otp_code: str) -> Run:
        run = await self._repository.get_run(run_id)
        pending = await self._control_store.get_pending(run_id)
        if pending is None:
            raise KeyError(f"Run is not waiting for OTP: {run_id}")
        input_data = await self._input_store.get(run_id)
        if input_data is None:
            # 입력값이 사라진 경우(예: 재기동 후 인메모리 스토어가 비었음). 이어받을 수 없다.
            raise KeyError(f"Run inputs are no longer available: {run_id}")
        # 핸들은 직렬화 토큰이라 pending 컨텍스트로 그대로 복원한다. OTP 는 입력값 dict 에
        # 담지 않고 게이트웨이로 런타임에 직접 주입한다(재개 시 OTP 는 runtime.config 에서 읽힘).
        handle = ExecutionHandle(
            execution_mode=pending.execution_mode, session_id=pending.session_id
        )
        await self._gateway.submit_input(handle, otp_code.strip())
        aggregate = RunAggregate(run)
        waiting_module = aggregate.module(pending.module_id)
        aggregate.resume_after_input(waiting_module)
        await self._repository.save_run(run)
        await self._events.module_event("module_queued", run, waiting_module)
        await self._events.run_event("run_resumed", run)
        await self._event_bus.publish(RunResumed(run=run))
        await self._control_store.clear_pending(run_id)
        logger.info(
            "Run OTP 재개", log_event="run.resumed", run_id=run_id, module_id=pending.module_id
        )
        await self._run_queue.submit(
            functools.partial(self._execute_run, run_id, input_data, pending.resume_index, handle),
            label=f"run:{run_id}:resume",
        )
        return run

    async def submit_otp_to_waiting(self, otp_code: str) -> Run:
        """현재 OTP 입력 대기 중인 Run 을 찾아 OTP 를 제출하고 재개한다.

        SMS 중계기는 ``run_id`` 를 모르고 코드만 보내므로, 서버가 "지금 OTP 를 기다리는 Run"
        을 찾아 기존 ``submit_otp`` 로 위임한다. 제어 스토어의 pending(=OTP 대기)이 권위 있는
        단일 출처이므로, ``WAITING_INPUT`` Run 중 pending 이 살아 있는 것만 후보로 본다(상태와
        제어 스토어가 어긋난 경합 상황을 배제). 무인 자동화는 본래 순차 실행이라 보통 1건이며,
        여러 건이면 가장 최근에 요청된 Run(방금 도착한 SMS 에 대응)을 고른다.
        """
        candidates: list[Run] = []
        for run in await self._repository.list_runs():
            if run.status != RunStatus.WAITING_INPUT:
                continue
            if await self._control_store.get_pending(run.run_id) is None:
                continue
            candidates.append(run)
        if not candidates:
            raise KeyError("OTP 입력을 기다리는 Run이 없습니다.")
        candidates.sort(key=lambda run: run.requested_at, reverse=True)
        target = candidates[0]
        if len(candidates) > 1:
            logger.warning(
                "OTP 대기 Run 다건 — 최근 요청 Run 에 제출",
                log_event="run.otp_relay_ambiguous",
                candidate_count=len(candidates),
                selected_run_id=target.run_id,
            )
        return await self.submit_otp(target.run_id, otp_code)

    async def cancel_run(self, run_id: str) -> Run:
        run = await self._repository.get_run(run_id)
        if run.status in {
            RunStatus.PASSED,
            RunStatus.ANOMALY,
            RunStatus.ERROR,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            raise ValueError("이미 종료된 Run은 취소할 수 없습니다.")
        await self._control_store.set_cancel_requested(run_id)
        logger.info(
            "Run 취소 요청",
            log_event="run.cancel_requested",
            run_id=run_id,
            status=run.status.value,
        )
        pending = await self._control_store.get_pending(run_id)
        if pending is not None:
            # OTP 입력 대기 중에는 실행 루프가 돌고 있지 않으므로 여기서 직접 정리·종료한다.
            await self._control_store.clear_pending(run_id)
            handle = ExecutionHandle(
                execution_mode=pending.execution_mode, session_id=pending.session_id
            )
            await self._cancel_waiting_run(run, handle)
        # 실행 중/대기열 상태에서는 실행 루프가 다음 모듈로 넘어가기 전에 취소 플래그를 확인해
        # 협력적으로 중단한다. (진행 중인 단계는 끝나거나 timeout 된 뒤 중단된다.)
        return run

    async def rerun_run(
        self,
        run_id: str,
        user_id: str | None = None,
        user_name: str | None = None,
    ) -> Run:
        original = await self._repository.get_run(run_id)
        stored_input = await self._input_store.get(run_id)
        if stored_input is None:
            raise ValueError(
                "재실행에 필요한 입력 정보를 찾을 수 없습니다. 홈에서 새로 실행해 주세요."
            )
        selected_module_ids = list(original.selected_module_ids) or None
        return await self.start_run(
            original.system_code,
            dict(stored_input),
            selected_module_ids,
            user_id=user_id or original.created_by_user_id,
            user_name=user_name or original.created_by_user_name,
        )

    # --- 실행 루프(상태머신) ----------------------------------------------

    async def _execute_run(
        self,
        run_id: str,
        input_data: dict[str, str],
        start_index: int = 0,
        handle: ExecutionHandle | None = None,
    ) -> None:
        run = await self._repository.get_run(run_id)
        with log_context(
            run_id=run.run_id,
            system_code=run.system_code,
            suite_id=run.suite_id,
            schedule_id=run.schedule_id,
            triggered_by=run.triggered_by,
        ):
            await self._execute_run_inner(
                run,
                input_data,
                start_index=start_index,
                handle=handle,
            )

    async def _execute_run_inner(
        self,
        run: Run,
        input_data: dict[str, str],
        *,
        start_index: int = 0,
        handle: ExecutionHandle | None = None,
    ) -> None:
        should_finalize = True
        # OTP 입력 대기로 일시정지하며 빠져나갈 때만 True. finally 의 세션 종료를 건너뛰는
        # 판단을 더 이상 메모리 dict(_pending_otp) 멤버십이 아니라 이 로컬 플래그로 한다.
        paused = False
        current_module: RunModule | None = None
        aggregate = RunAggregate(run)
        if start_index == 0:
            aggregate.begin()
            await self._repository.save_run(run)
            await self._events.run_event("run_started", run)
            logger.info(
                "Run 시작", log_event="run.started", run_id=run.run_id, system_code=run.system_code
            )

        system = self._registry.get_system(run.system_code)
        definitions = {module.module_id: module for module in system.modules}
        ordered_modules = self._planner.ordered_selected_run_modules(run)

        forced_status: RunStatus | None = None
        try:
            for index, module in enumerate(ordered_modules[start_index:], start=start_index):
                current_module = module
                # 결정(무엇을 할지)은 순수 상태머신이, 효과(I/O)는 이 루프가 책임진다.
                entry = RunStateMachine.decide_module_entry(
                    cancel_requested=await self._control_store.is_cancel_requested(run.run_id),
                    dependencies_satisfied=aggregate.dependencies_satisfied(module),
                )
                if isinstance(entry, CancelRemaining):
                    forced_status = RunStatus.CANCELLED
                    await self._mark_modules_cancelled(run, ordered_modules[index:])
                    break
                if isinstance(entry, BlockModule):
                    aggregate.block_for_dependencies(module)
                    await self._repository.save_run(run)
                    await self._events.module_event("module_finished", run, module)
                    continue
                assert isinstance(entry, ExecuteModule)

                await self._transition_to_queued(run, module)
                await asyncio.sleep(0.6)
                await self._transition_to_running(run, module)

                definition = definitions[module.module_id]
                # 실행은 전적으로 ExecutionGateway 포트 뒤에서 일어난다. 실제 브라우저
                # 실행과 시뮬레이션의 구분은 더 이상 코어에 없다(합성 게이트웨이가 모드로 라우팅).
                # 지원하지 않는 execution_mode 면 open_session 이 예외를 던져 모듈이 명확히 실패한다.
                if handle is None:
                    try:
                        handle = await self._gateway.open_session(
                            definition.execution_mode,
                            input_data,
                            run.run_id,
                            module.module_id,
                        )
                    except Exception as exc:
                        await self._fail_module(run, module, exc)
                        continue

                async def on_log(line: str, current_module=module, current_run=run) -> None:
                    await self._handle_module_log(current_run, current_module, line)

                execution_result = await self._gateway.run_step(
                    handle, run.run_id, definition, on_log
                )

                # 일시정지로 멈추려는 순간에만 취소를 재확인한다(정상 종료의 취소는 다음 진입에서).
                cancel_requested = (
                    await self._control_store.is_cancel_requested(run.run_id)
                    if execution_result.status == ModuleStatus.WAITING_INPUT
                    else False
                )
                post = RunStateMachine.decide_post_step(
                    step_status=execution_result.status,
                    cancel_requested=cancel_requested,
                    module_requires_user_input=definition.requires_user_input,
                )
                if isinstance(post, CancelRemaining):
                    forced_status = RunStatus.CANCELLED
                    await self._mark_modules_cancelled(run, ordered_modules[index:])
                    break
                if isinstance(post, PauseForInput):
                    await self._pause_for_input(
                        run, module, index, definition, handle, execution_result
                    )
                    should_finalize = False
                    paused = True
                    return
                if isinstance(post, RejectUnexpectedInput):
                    # 매니페스트가 일시정지를 허가하지 않은 모듈이 입력을 요구함 → 정책 위반.
                    await self._fail_module(
                        run,
                        module,
                        RuntimeError(
                            "모듈이 사용자 입력을 요구했으나 매니페스트에 "
                            "requires_user_input 이 선언되지 않았습니다."
                        ),
                    )
                    continue
                assert isinstance(post, CompleteStep)

                self._record_module_result(aggregate, module, execution_result)
                aggregate.finish_timing(module)
                await self._repository.save_run(run)
                await self._events.module_event("module_finished", run, module)
        except Exception as exc:
            forced_status = RunStatus.ERROR
            await self._mark_unexpected_run_failure(run, current_module, ordered_modules, exc)
        finally:
            if handle is not None and not paused:
                try:
                    await self._gateway.close_session(handle)
                except Exception as exc:
                    if forced_status is None:
                        forced_status = RunStatus.ERROR
                        await self._mark_unexpected_run_failure(
                            run, current_module, ordered_modules, exc
                        )
                    else:
                        logger.exception(
                            "Run runtime 정리 오류",
                            log_event="run.cleanup_failed",
                            run_id=run.run_id,
                            error=str(exc),
                        )

        if not should_finalize:
            return
        await self._finalize_run(run, forced_status)

    # --- 모듈 상태 전이 보조 ----------------------------------------------

    async def _transition_to_queued(self, run: Run, module: RunModule) -> None:
        RunAggregate(run).mark_queued(module)
        await self._repository.save_run(run)
        await self._events.module_event("module_queued", run, module)

    async def _transition_to_running(self, run: Run, module: RunModule) -> None:
        RunAggregate(run).mark_running(module)
        await self._repository.save_run(run)
        await self._events.module_event("module_started", run, module)

    def _record_module_result(
        self, aggregate: RunAggregate, module: RunModule, execution_result
    ) -> None:
        # 로그는 별도 스토어가 소유하므로 집합체로 복사하지 않는다(읽기 시 하이드레이션).
        aggregate.record_result(
            module,
            status=execution_result.status,
            message=execution_result.message,
            artifacts=execution_result.artifacts,
            current_url=execution_result.current_url,
            dialog_messages=execution_result.dialog_messages,
        )

    async def _fail_module(self, run: Run, module: RunModule, exc: Exception) -> None:
        """세션 기동 실패 등 단계 진입 전에 난 오류로 모듈을 실패 처리한다."""
        await self._handle_module_log(run, module, f"[error] {exc}")
        RunAggregate(run).fail_module(module, str(exc))
        await self._repository.save_run(run)
        await self._events.module_event("module_finished", run, module)

    async def _pause_for_input(
        self,
        run: Run,
        module: RunModule,
        index: int,
        definition,
        handle: ExecutionHandle,
        execution_result,
    ) -> None:
        RunAggregate(run).mark_waiting_input(
            module, execution_result.message, execution_result.artifacts
        )
        await self._repository.save_run(run)
        await self._events.module_event("module_waiting_input", run, module)
        await self._events.run_event("run_waiting_input", run)
        # Suite Saga 가 하위 Run 의 일시정지를 폴링이 아니라 도메인 이벤트로 감지하도록 발행.
        await self._event_bus.publish(RunWaitingInput(run=run))
        # 재개 컨텍스트(직렬화 토큰 + resume index)는 메모리 dict 가 아니라 제어 스토어가 소유한다.
        # 입력값(PII)은 start_run 에서 이미 input_store 에 보관됐다.
        await self._control_store.set_pending(
            run.run_id,
            session_id=handle.session_id,
            execution_mode=handle.execution_mode,
            resume_index=index,
            module_id=module.module_id,
        )
        logger.info(
            "Run OTP 대기",
            log_event="run.waiting_input",
            run_id=run.run_id,
            module_id=module.module_id,
        )

    # --- 취소 / 종료 ------------------------------------------------------

    async def _cancel_waiting_run(self, run: Run, handle: ExecutionHandle) -> None:
        try:
            await self._gateway.close_session(handle)
        except Exception as exc:
            logger.exception(
                "Run 취소 중 runtime 정리 오류",
                log_event="run.cancel_cleanup_failed",
                run_id=run.run_id,
                error=str(exc),
            )
        await self._mark_modules_cancelled(run, self._planner.ordered_selected_run_modules(run))
        # awaiting_input_* 정리는 _finalize_run → RunAggregate.finalize 가 책임진다(직접 변이 금지).
        await self._finalize_run(run, RunStatus.CANCELLED)

    async def _mark_modules_cancelled(self, run: Run, modules: list[RunModule]) -> None:
        changed = RunAggregate(run).cancel_modules(modules)
        for module in changed:
            await self._repository.save_run(run)
            await self._events.module_event("module_finished", run, module)

    async def _mark_unexpected_run_failure(
        self,
        run: Run,
        current_module: RunModule | None,
        ordered_modules: list[RunModule],
        exc: Exception,
    ) -> None:
        await self._repository.save_run(run)
        aggregate = RunAggregate(run)
        target_module = aggregate.select_failure_target(current_module, ordered_modules)
        if target_module is None:
            logger.error(
                "Run 예상치 못한 실행 오류",
                log_event="run.unexpected_error",
                run_id=run.run_id,
                error=str(exc),
            )
            return

        await self._handle_module_log(run, target_module, f"[fatal] {exc}")
        aggregate.mark_fatal(target_module, f"예상하지 못한 실행 오류: {exc}")
        await self._repository.save_run(run)
        await self._events.module_event("module_finished", run, target_module)

    async def _finalize_run(self, run: Run, forced_status: RunStatus | None = None) -> None:
        final_status = RunAggregate(run).finalize(forced_status)
        if final_status in {RunStatus.PASSED, RunStatus.ANOMALY, RunStatus.ERROR, RunStatus.FAILED}:
            run.comparison = await self._comparator.compute(run)
        await self._repository.save_run(run)
        # 종료된 Run 의 제어 상태(취소 플래그·재개 컨텍스트)는 더 이상 필요 없다. 입력값은
        # input_store 가 따로 보관하므로 rerun 에는 영향이 없다.
        await self._control_store.delete(run.run_id)
        await self._events.run_event("run_finished", run)
        # 부수 관심사(AI 실패 분석·종료 메일)는 이벤트 구독자가 처리한다. 실패 분석이 모듈
        # 로그(`module.logs`)를 참조하므로, 로그가 하이드레이션된 읽기 모델을 이벤트로 싣는다.
        finished = await self.get_run(run.run_id)
        await self._event_bus.publish(RunFinished(run=finished))
        logger.info(
            "Run 종료",
            log_event="run.finished",
            run_id=run.run_id,
            system_code=run.system_code,
            status=final_status.value,
            suite_id=run.suite_id,
            schedule_id=run.schedule_id,
        )

    # --- 로그 기록 --------------------------------------------------------

    async def _handle_module_log(self, run: Run, module: RunModule, line: str) -> None:
        trimmed = line.strip()
        if not trimmed:
            return
        RunAggregate(run).note_module_message(module, trimmed)
        # 로그는 별도 append-only 스토어로 한 줄씩 INSERT(O(1)). Run blob 은 여기서 저장하지
        # 않는다 — 상태 전이 시점에만 save_run 한다(핫패스 full-blob 쓰기 제거). 라이브 전파는
        # WebSocket ``module_log`` 이벤트가 담당하고, 누적 로그는 읽기 시 하이드레이션한다.
        await self._log_store.append(run.run_id, module.module_id, trimmed)
        await self._events.module_log(run, module, trimmed)
