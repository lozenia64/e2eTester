from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import Run, RunModule
from app.events.bus import EventBus, RunFinished
from app.execution.gateway import ExecutionGateway, ExecutionHandle
from app.orchestrator.run_comparator import RunComparator
from app.orchestrator.run_event_publisher import RunEventPublisher
from app.orchestrator.run_planner import RunPlanner
from app.orchestrator.run_summary import summarize_run
from app.registry.loader import ModuleRegistry
from app.runner.artifact_manager import ArtifactManager
from app.storage.ports import (
    RunControlStorePort,
    RunInputStorePort,
    RunLogStorePort,
    RunRepositoryPort,
)

if TYPE_CHECKING:
    from app.orchestrator.run_actor import ActorContext


class RunService:
    """Run 의 생명주기를 관장하는 오케스트레이터(상태머신).

    책임은 "무엇을, 어떤 순서로, 어떤 상태로" 만으로 한정한다. 실제 브라우저 구동·스레드
    모델·런타임 수명은 ``ExecutionGateway`` 포트에, 검증·계획은 ``RunPlanner`` 에, 이력
    비교는 ``RunComparator`` 에, AI 실패 분석·종료 메일 같은 부수 관심사는 ``EventBus``
    구독자에게 위임한다. 이 클래스는 Playwright/스레드/Gemini/SMTP 를 전혀 import 하지 않는다.
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
        comparator: RunComparator | None = None,
        planner: RunPlanner | None = None,
        artifact_manager: ArtifactManager | None = None,
    ) -> None:
        self._registry = registry
        self._repository = repository
        self._log_store = log_store
        self._gateway = execution_gateway
        self._event_bus = event_bus
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
    ) -> list[dict]:
        if user_id is not None:
            runs = await self._repository.list_runs_by_user(user_id)
        else:
            runs = await self._repository.list_runs()
        runs.sort(key=lambda run: run.requested_at, reverse=True)

        normalized_name_query = (user_name_query or "").strip().casefold()
        summaries: list[dict] = []
        for run in runs:
            summary = summarize_run(run, actor_context=actor_context)
            if system_code and summary.get("system_code") != system_code:
                continue
            if normalized_name_query:
                actor_name = (summary.get("created_by_user_name") or "").casefold()
                if normalized_name_query not in actor_name:
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

    async def reconcile_interrupted_runs(self) -> int:
        """재기동 시 비종료 상태로 남은 Run 을 CANCELLED 로 정리한다.

        영속 저장소(SQLite)를 쓰면 서버가 내려갈 때 RUNNING/WAITING_INPUT 이던 Run 이
        그대로 복원된다. 하지만 그 Run 이 쓰던 브라우저 세션·OTP 대기 핸들은 프로세스와 함께
        사라졌으므로 이어받을 수 없다. 좀비 상태를 막기 위해 종료로 봉인한다(필요하면 사용자가
        ``rerun`` 으로 다시 실행). 인메모리 저장소에서는 복원될 Run 이 없어 no-op 이다.
        """
        active = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_INPUT}
        active_modules = {
            ModuleStatus.PENDING,
            ModuleStatus.QUEUED,
            ModuleStatus.RUNNING,
            ModuleStatus.WAITING_INPUT,
        }
        count = 0
        for run in await self._repository.list_runs():
            if run.status not in active:
                continue
            run.status = RunStatus.CANCELLED
            run.ended_at = run.ended_at or datetime.now(UTC)
            run.awaiting_input_module_id = None
            run.awaiting_input_prompt = None
            for module in run.modules:
                if module.status in active_modules:
                    module.status = ModuleStatus.CANCELLED
                    module.message = "서버 재시작으로 중단됨"
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
        asyncio.create_task(self._execute_run(run.run_id, sanitized_input))
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
        handle = ExecutionHandle(execution_mode=pending.execution_mode, session_id=pending.session_id)
        await self._gateway.submit_input(handle, otp_code.strip())
        run.status = RunStatus.RUNNING
        run.awaiting_input_module_id = None
        run.awaiting_input_prompt = None
        waiting_module = self._find_run_module(run, pending.module_id)
        waiting_module.status = ModuleStatus.QUEUED
        waiting_module.message = "OTP 입력이 접수되어 재개 대기 중"
        await self._repository.save_run(run)
        await self._events.module_event("module_queued", run, waiting_module)
        await self._events.run_event("run_resumed", run)
        await self._control_store.clear_pending(run_id)
        asyncio.create_task(
            self._execute_run(run_id, input_data, pending.resume_index, handle)
        )
        return run

    async def cancel_run(self, run_id: str) -> Run:
        run = await self._repository.get_run(run_id)
        if run.status in {RunStatus.PASSED, RunStatus.FAILED, RunStatus.CANCELLED}:
            raise ValueError("이미 종료된 Run은 취소할 수 없습니다.")
        await self._control_store.set_cancel_requested(run_id)
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
            raise ValueError("재실행에 필요한 입력 정보를 찾을 수 없습니다. 홈에서 새로 실행해 주세요.")
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
        should_finalize = True
        # OTP 입력 대기로 일시정지하며 빠져나갈 때만 True. finally 의 세션 종료를 건너뛰는
        # 판단을 더 이상 메모리 dict(_pending_otp) 멤버십이 아니라 이 로컬 플래그로 한다.
        paused = False
        current_module: RunModule | None = None
        if start_index == 0:
            run.status = RunStatus.RUNNING
            run.started_at = datetime.now(UTC)
            await self._repository.save_run(run)
            await self._events.run_event("run_started", run)

        system = self._registry.get_system(run.system_code)
        definitions = {module.module_id: module for module in system.modules}
        modules_by_id = {module.module_id: module for module in run.modules}
        ordered_modules = self._planner.ordered_selected_run_modules(run)

        forced_status: RunStatus | None = None
        try:
            for index, module in enumerate(ordered_modules[start_index:], start=start_index):
                current_module = module
                if await self._control_store.is_cancel_requested(run.run_id):
                    forced_status = RunStatus.CANCELLED
                    await self._mark_modules_cancelled(run, ordered_modules[index:])
                    break
                if any(modules_by_id[dependency].status != ModuleStatus.PASSED for dependency in module.depends_on):
                    module.status = ModuleStatus.BLOCKED
                    module.message = "선행 모듈 실패로 인해 실행되지 않음"
                    await self._repository.save_run(run)
                    await self._events.module_event("module_finished", run, module)
                    continue

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

                if execution_result.status == ModuleStatus.WAITING_INPUT:
                    if await self._control_store.is_cancel_requested(run.run_id):
                        # OTP 대기로 멈추려는 순간 취소가 요청된 경우, 일시정지하지 않고 바로 중단한다.
                        forced_status = RunStatus.CANCELLED
                        await self._mark_modules_cancelled(run, ordered_modules[index:])
                        break
                    await self._pause_for_input(run, module, index, definition, handle, execution_result)
                    should_finalize = False
                    paused = True
                    return

                await self._record_module_result(run, module, execution_result)

                module.ended_at = datetime.now(UTC)
                module.duration_ms = int((module.ended_at - module.started_at).total_seconds() * 1000)
                await self._repository.save_run(run)
                await self._events.module_event("module_finished", run, module)
        except Exception as exc:
            forced_status = RunStatus.FAILED
            await self._mark_unexpected_run_failure(run, current_module, ordered_modules, exc)
        finally:
            if handle is not None and not paused:
                try:
                    await self._gateway.close_session(handle)
                except Exception as exc:
                    if forced_status is None:
                        forced_status = RunStatus.FAILED
                        await self._mark_unexpected_run_failure(run, current_module, ordered_modules, exc)
                    else:
                        print(f"[run] run={run.run_id} runtime cleanup error: {exc}")

        if not should_finalize:
            return
        await self._finalize_run(run, forced_status)

    # --- 모듈 상태 전이 보조 ----------------------------------------------

    async def _transition_to_queued(self, run: Run, module: RunModule) -> None:
        module.status = ModuleStatus.QUEUED
        module.message = "실행 대기열에 등록됨"
        module.failure_analysis = None
        await self._repository.save_run(run)
        await self._events.module_event("module_queued", run, module)

    async def _transition_to_running(self, run: Run, module: RunModule) -> None:
        module.status = ModuleStatus.RUNNING
        module.started_at = datetime.now(UTC)
        module.message = "실행 준비 중"
        module.failure_analysis = None
        await self._repository.save_run(run)
        await self._events.module_event("module_started", run, module)

    async def _record_module_result(self, run: Run, module: RunModule, execution_result) -> None:
        module.status = execution_result.status
        module.message = execution_result.message
        module.artifacts = execution_result.artifacts
        module.artifact_count = len(execution_result.artifacts)
        # 로그는 별도 스토어가 소유하므로 집합체로 복사하지 않는다(읽기 시 하이드레이션).
        module.current_url = execution_result.current_url
        module.dialog_messages = list(execution_result.dialog_messages)

    async def _fail_module(self, run: Run, module: RunModule, exc: Exception) -> None:
        """세션 기동 실패 등 단계 진입 전에 난 오류로 모듈을 실패 처리한다."""
        await self._handle_module_log(run, module, f"[error] {exc}")
        module.status = ModuleStatus.FAILED
        module.message = str(exc)
        module.ended_at = datetime.now(UTC)
        module.duration_ms = int((module.ended_at - module.started_at).total_seconds() * 1000)
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
        module.status = ModuleStatus.WAITING_INPUT
        module.message = f"{execution_result.message}. 웹 화면에서 OTP를 입력해 제출하세요."
        module.artifacts = execution_result.artifacts
        module.artifact_count = len(execution_result.artifacts)
        module.failure_analysis = None
        run.status = RunStatus.WAITING_INPUT
        run.awaiting_input_module_id = module.module_id
        run.awaiting_input_prompt = "휴대폰으로 받은 OTP를 입력하세요."
        await self._repository.save_run(run)
        await self._events.module_event("module_waiting_input", run, module)
        await self._events.run_event("run_waiting_input", run)
        # 재개 컨텍스트(직렬화 토큰 + resume index)는 메모리 dict 가 아니라 제어 스토어가 소유한다.
        # 입력값(PII)은 start_run 에서 이미 input_store 에 보관됐다.
        await self._control_store.set_pending(
            run.run_id,
            session_id=handle.session_id,
            execution_mode=handle.execution_mode,
            resume_index=index,
            module_id=module.module_id,
        )

    # --- 취소 / 종료 ------------------------------------------------------

    async def _cancel_waiting_run(self, run: Run, handle: ExecutionHandle) -> None:
        try:
            await self._gateway.close_session(handle)
        except Exception as exc:
            print(f"[run] run={run.run_id} 취소 중 runtime 정리 오류: {exc}")
        await self._mark_modules_cancelled(run, self._planner.ordered_selected_run_modules(run))
        run.awaiting_input_module_id = None
        run.awaiting_input_prompt = None
        await self._finalize_run(run, RunStatus.CANCELLED)

    async def _mark_modules_cancelled(self, run: Run, modules: list[RunModule]) -> None:
        terminal_statuses = {
            ModuleStatus.PASSED,
            ModuleStatus.FAILED,
            ModuleStatus.SKIPPED,
            ModuleStatus.BLOCKED,
            ModuleStatus.CANCELLED,
        }
        for module in modules:
            if module.status in terminal_statuses:
                continue
            if module.started_at is not None and module.ended_at is None:
                module.ended_at = datetime.now(UTC)
                module.duration_ms = int((module.ended_at - module.started_at).total_seconds() * 1000)
            module.status = ModuleStatus.CANCELLED
            module.message = "사용자 요청으로 취소됨"
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
        target_module = None
        if current_module is not None and current_module.status in {ModuleStatus.QUEUED, ModuleStatus.RUNNING}:
            target_module = current_module
        else:
            for module in ordered_modules:
                if module.status in {ModuleStatus.PENDING, ModuleStatus.QUEUED, ModuleStatus.RUNNING}:
                    target_module = module
                    break

        if target_module is None:
            print(f"[run] run={run.run_id} unexpected execution error: {exc}")
            return

        if target_module.started_at is None:
            target_module.started_at = datetime.now(UTC)
        await self._handle_module_log(run, target_module, f"[fatal] {exc}")
        target_module.status = ModuleStatus.FAILED
        target_module.message = f"예상하지 못한 실행 오류: {exc}"
        target_module.ended_at = datetime.now(UTC)
        target_module.duration_ms = int((target_module.ended_at - target_module.started_at).total_seconds() * 1000)
        await self._repository.save_run(run)
        await self._events.module_event("module_finished", run, target_module)

    async def _finalize_run(self, run: Run, forced_status: RunStatus | None = None) -> None:
        run.ended_at = datetime.now(UTC)
        run.awaiting_input_module_id = None
        run.awaiting_input_prompt = None
        if forced_status is not None:
            run.status = forced_status
        else:
            run.status = (
                RunStatus.FAILED
                if any(module.status == ModuleStatus.FAILED for module in run.modules)
                else RunStatus.PASSED
            )
        if run.status in {RunStatus.PASSED, RunStatus.FAILED}:
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

    # --- 로그 기록 --------------------------------------------------------

    async def _handle_module_log(self, run: Run, module: RunModule, line: str) -> None:
        trimmed = line.strip()
        if not trimmed:
            return
        module.message = trimmed
        # 로그는 별도 append-only 스토어로 한 줄씩 INSERT(O(1)). Run blob 은 여기서 저장하지
        # 않는다 — 상태 전이 시점에만 save_run 한다(핫패스 full-blob 쓰기 제거). 라이브 전파는
        # WebSocket ``module_log`` 이벤트가 담당하고, 누적 로그는 읽기 시 하이드레이션한다.
        await self._log_store.append(run.run_id, module.module_id, trimmed)
        await self._events.module_log(run, module, trimmed)

    @staticmethod
    def _find_run_module(run: Run, module_id: str) -> RunModule:
        for module in run.modules:
            if module.module_id == module_id:
                return module
        raise KeyError(f"Run module not found: {module_id}")
