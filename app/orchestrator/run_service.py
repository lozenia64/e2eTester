from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import DashboardEvent, FailureAnalysisRequest, ModuleDefinition, Run, RunModule, SystemDefinition
from app.notifications.run_completion_email import RunCompletionEmailNotifier
from app.registry.loader import ModuleRegistry
from app.runner.artifact_manager import ArtifactManager
from app.runner.workflow_common import StepExecutionResult
from app.storage.run_repository import InMemoryRunRepository
from app.systems.loader import load_workflow_executors


@dataclass
class PendingOtpState:
    run_id: str
    input_data: dict[str, str]
    sequence_index: int
    module_id: str
    execution_mode: str
    runtime: Any


class RunService:
    def __init__(
        self,
        registry: ModuleRegistry,
        repository: InMemoryRunRepository,
        failure_analyzer=None,
        run_completion_notifier: RunCompletionEmailNotifier | None = None,
    ) -> None:
        self._registry = registry
        self._repository = repository
        self._artifact_manager = ArtifactManager()
        self._workflow_executors = load_workflow_executors(
            (system.system_code for system in self._registry.list_systems()),
            self._artifact_manager,
        )
        self._pending_otp: dict[str, PendingOtpState] = {}
        self._failure_analyzer = failure_analyzer
        self._run_completion_notifier = run_completion_notifier

    def list_systems(self):
        return self._registry.list_systems()

    async def get_run(self, run_id: str) -> Run:
        return await self._repository.get_run(run_id)

    async def list_run_summaries(self, limit: int = 50) -> list[dict]:
        runs = await self._repository.list_runs()
        runs.sort(key=lambda run: run.requested_at, reverse=True)
        return [self._summarize_run(run) for run in runs[:limit]]

    @staticmethod
    def _summarize_run(run: Run) -> dict:
        ordered_modules = sorted(run.modules, key=lambda module: module.order)
        selected_module_ids = set(run.selected_module_ids) or {
            module.module_id for module in ordered_modules if module.status != ModuleStatus.SKIPPED
        }
        current_module = next(
            (
                module
                for module in ordered_modules
                if module.module_id in selected_module_ids
                and module.status in {ModuleStatus.RUNNING, ModuleStatus.WAITING_INPUT}
            ),
            None,
        )
        failed_module = next(
            (
                module
                for module in ordered_modules
                if module.module_id in selected_module_ids and module.status == ModuleStatus.FAILED
            ),
            None,
        )
        return {
            "run_id": run.run_id,
            "system_code": run.system_code,
            "system_name": run.system_name,
            "status": run.status,
            "requested_at": run.requested_at.isoformat(),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "awaiting_input_module_id": run.awaiting_input_module_id,
            "awaiting_input_prompt": run.awaiting_input_prompt,
            "module_total": len(selected_module_ids),
            "module_defined_total": len(run.modules),
            "module_skipped": sum(1 for module in run.modules if module.status == ModuleStatus.SKIPPED),
            "module_passed": sum(
                1
                for module in run.modules
                if module.module_id in selected_module_ids and module.status == ModuleStatus.PASSED
            ),
            "current_module_name": current_module.name if current_module else None,
            "failed_module_name": failed_module.name if failed_module else None,
        }

    def get_system(self, system_code: str):
        return self._registry.get_system(system_code)

    async def subscribe(self, run_id: str):
        return await self._repository.subscribe(run_id)

    async def unsubscribe(self, run_id: str, queue):
        await self._repository.unsubscribe(run_id, queue)

    async def submit_otp(self, run_id: str, otp_code: str) -> Run:
        run = await self._repository.get_run(run_id)
        pending = self._pending_otp.get(run_id)
        if pending is None:
            raise KeyError(f"Run is not waiting for OTP: {run_id}")
        pending.input_data["otp_code"] = otp_code.strip()
        executor = self._workflow_executors.get(pending.execution_mode)
        if executor is None:
            raise KeyError(f"Unsupported workflow execution mode: {pending.execution_mode}")
        executor.update_otp_code(pending.runtime, pending.input_data["otp_code"])
        run.status = RunStatus.RUNNING
        run.awaiting_input_module_id = None
        run.awaiting_input_prompt = None
        waiting_module = self._find_run_module(run, pending.module_id)
        waiting_module.status = ModuleStatus.QUEUED
        waiting_module.message = "OTP 입력이 접수되어 재개 대기 중"
        await self._repository.save_run(run)
        await self._publish_module_event("module_queued", run, waiting_module)
        await self._publish_run_event("run_resumed", run)
        del self._pending_otp[run_id]
        asyncio.create_task(self._execute_run(run_id, pending.input_data, pending.sequence_index, pending.runtime))
        return run

    async def start_run(
        self,
        system_code: str,
        input_data: dict[str, str] | None = None,
        selected_module_ids: list[str] | None = None,
    ) -> Run:
        system = self.get_system(system_code)
        run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        sanitized_input = {key: value.strip() for key, value in (input_data or {}).items()}
        resolved_selected_module_ids = self._resolve_selected_module_ids(system, selected_module_ids)
        if system.supported_auth_methods:
            auth_method = sanitized_input.get("auth_method") or system.supported_auth_methods[0]
            sanitized_input["auth_method"] = auth_method
            if auth_method not in system.supported_auth_methods:
                label = system.name
                raise ValueError(f"{label}에서는 휴대폰인증과 카카오인증만 실행할 수 있습니다.")
        run = Run(
            run_id=run_id,
            system_code=system.system_code,
            system_name=system.name,
            status=RunStatus.PENDING,
            requested_at=datetime.now(UTC),
            modules=self._build_run_modules(system, resolved_selected_module_ids),
            selected_module_ids=resolved_selected_module_ids,
        )
        await self._repository.create_run(run)
        await self._repository.publish(
            DashboardEvent(
                event_type="run_created",
                run_id=run.run_id,
                system_code=run.system_code,
                run_status=run.status,
                payload=run.model_dump(mode="json"),
            )
        )
        asyncio.create_task(self._execute_run(run.run_id, sanitized_input))
        return run

    async def _execute_run(
        self,
        run_id: str,
        input_data: dict[str, str],
        start_index: int = 0,
        workflow_runtime: Any | None = None,
        active_workflow_executor=None,
    ) -> None:
        run = await self._repository.get_run(run_id)
        should_finalize = True
        current_module: RunModule | None = None
        if start_index == 0:
            run.status = RunStatus.RUNNING
            run.started_at = datetime.now(UTC)
            await self._repository.save_run(run)
            await self._publish_run_event("run_started", run)
        event_loop = asyncio.get_running_loop()

        system = self._registry.get_system(run.system_code)
        definitions = {module.module_id: module for module in system.modules}

        modules_by_id = {module.module_id: module for module in run.modules}
        ordered_modules = self._ordered_selected_run_modules(run)

        forced_status: RunStatus | None = None
        try:
            for index, module in enumerate(ordered_modules[start_index:], start=start_index):
                current_module = module
                if any(modules_by_id[dependency].status != ModuleStatus.PASSED for dependency in module.depends_on):
                    module.status = ModuleStatus.BLOCKED
                    module.message = "선행 모듈 실패로 인해 실행되지 않음"
                    await self._repository.save_run(run)
                    await self._publish_module_event("module_finished", run, module)
                    continue

                module.status = ModuleStatus.QUEUED
                module.message = "실행 대기열에 등록됨"
                module.failure_analysis = None
                await self._repository.save_run(run)
                await self._publish_module_event("module_queued", run, module)

                await asyncio.sleep(0.6)

                module.status = ModuleStatus.RUNNING
                module.started_at = datetime.now(UTC)
                module.message = "실행 준비 중"
                module.failure_analysis = None
                await self._repository.save_run(run)
                await self._publish_module_event("module_started", run, module)

                definition = definitions[module.module_id]
                workflow_executor = self._workflow_executors.get(definition.execution_mode)
                if workflow_executor is not None:
                    active_workflow_executor = workflow_executor
                    if workflow_runtime is None:
                        try:
                            workflow_runtime = await self._build_workflow_runtime(
                                workflow_executor,
                                input_data,
                                run.run_id,
                                module.module_id,
                            )
                        except Exception as exc:
                            await self._handle_module_log(run, module, f"[error] {exc}")
                            module.status = ModuleStatus.FAILED
                            module.message = str(exc)
                            module.logs = await self._repository.get_module_logs(run.run_id, module.module_id)
                            module.failure_analysis = await self._analyze_module_failure(
                                run=run,
                                module=module,
                                definition=definition,
                                execution_result=StepExecutionResult.failure(
                                    message=str(exc),
                                    current_url=None,
                                    dialog_messages=[],
                                    last_error=str(exc),
                                ),
                            )
                            module.ended_at = datetime.now(UTC)
                            module.duration_ms = int((module.ended_at - module.started_at).total_seconds() * 1000)
                            await self._repository.save_run(run)
                            await self._publish_module_event("module_finished", run, module)
                            continue

                    def emit_from_thread(line: str, current_module=module, current_run=run) -> None:
                        future = asyncio.run_coroutine_threadsafe(
                            self._handle_module_log(current_run, current_module, line),
                            event_loop,
                        )
                        future.result()

                    execution_result = await self._execute_workflow_step(
                        workflow_executor,
                        workflow_runtime,
                        run.run_id,
                        definition,
                        emit_from_thread,
                    )
                    status = execution_result.status
                    message = execution_result.message
                    artifacts = execution_result.artifacts
                    if status == ModuleStatus.WAITING_INPUT:
                        module.status = ModuleStatus.WAITING_INPUT
                        module.message = f"{message}. 웹 화면에서 OTP를 입력해 제출하세요."
                        module.artifacts = artifacts
                        module.artifact_count = len(artifacts)
                        module.logs = await self._repository.get_module_logs(run.run_id, module.module_id)
                        module.failure_analysis = None
                        run.status = RunStatus.WAITING_INPUT
                        run.awaiting_input_module_id = module.module_id
                        run.awaiting_input_prompt = "휴대폰으로 받은 OTP를 입력하세요."
                        await self._repository.save_run(run)
                        await self._publish_module_event("module_waiting_input", run, module)
                        await self._publish_run_event("run_waiting_input", run)
                        self._pending_otp[run.run_id] = PendingOtpState(
                            run_id=run.run_id,
                            input_data=input_data,
                            sequence_index=index,
                            module_id=module.module_id,
                            execution_mode=definition.execution_mode,
                            runtime=workflow_runtime,
                        )
                        should_finalize = False
                        return
                    module.status = status
                    module.message = message
                    module.artifacts = artifacts
                    module.artifact_count = len(artifacts)
                    module.logs = await self._repository.get_module_logs(run.run_id, module.module_id)
                    module.failure_analysis = await self._analyze_module_failure(
                        run=run,
                        module=module,
                        definition=definition,
                        execution_result=execution_result,
                    )
                else:
                    await asyncio.sleep(definition.simulated_duration_ms / 1000)
                    if definition.simulated_outcome.upper() == ModuleStatus.FAILED.value:
                        module.status = ModuleStatus.FAILED
                        module.message = "시뮬레이션 실패"
                    else:
                        module.status = ModuleStatus.PASSED
                        module.message = "시뮬레이션 성공"

                module.ended_at = datetime.now(UTC)
                module.duration_ms = int((module.ended_at - module.started_at).total_seconds() * 1000)
                await self._repository.save_run(run)
                await self._publish_module_event("module_finished", run, module)
        except Exception as exc:
            forced_status = RunStatus.FAILED
            await self._mark_unexpected_run_failure(run, current_module, ordered_modules, exc)
        finally:
            if workflow_runtime is not None and run.run_id not in self._pending_otp:
                try:
                    await self._close_workflow_runtime(active_workflow_executor, workflow_runtime)
                except Exception as exc:
                    if forced_status is None:
                        forced_status = RunStatus.FAILED
                        await self._mark_unexpected_run_failure(run, current_module, ordered_modules, exc)
                    else:
                        print(f"[run] run={run.run_id} runtime cleanup error: {exc}")

        if not should_finalize:
            return
        await self._finalize_run(run, forced_status)

    async def _build_workflow_runtime(
        self,
        workflow_executor,
        input_data: dict[str, str],
        run_id: str,
        module_id: str,
    ):
        prefix = workflow_executor.execution_mode.replace("_workflow_step", "")
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{prefix}-runtime-{run_id}")
        try:
            runtime = await asyncio.get_running_loop().run_in_executor(
                executor,
                workflow_executor.build_runtime,
                input_data,
                run_id,
                module_id,
            )
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        runtime.executor = executor
        return runtime

    async def _execute_workflow_step(
        self,
        workflow_executor,
        runtime,
        run_id: str,
        definition,
        emit_from_thread,
    ) -> StepExecutionResult:
        thread_executor = runtime.executor
        if thread_executor is None:
            return await asyncio.to_thread(
                workflow_executor.execute_step,
                runtime,
                run_id,
                definition,
                emit_from_thread,
            )
        return await asyncio.get_running_loop().run_in_executor(
            thread_executor,
            workflow_executor.execute_step,
            runtime,
            run_id,
            definition,
            emit_from_thread,
        )

    async def _close_workflow_runtime(self, workflow_executor, runtime) -> None:
        if workflow_executor is None:
            return
        thread_executor = runtime.executor
        try:
            if thread_executor is None:
                await asyncio.to_thread(workflow_executor.close_runtime, runtime)
            else:
                await asyncio.get_running_loop().run_in_executor(
                    thread_executor,
                    workflow_executor.close_runtime,
                    runtime,
                )
        finally:
            if thread_executor is not None:
                thread_executor.shutdown(wait=True, cancel_futures=True)
                runtime.executor = None

    async def _publish_run_event(self, event_type: str, run: Run) -> None:
        await self._repository.publish(
            DashboardEvent(
                event_type=event_type,
                run_id=run.run_id,
                system_code=run.system_code,
                run_status=run.status,
                payload=run.model_dump(mode="json"),
            )
        )

    async def _publish_module_event(self, event_type: str, run: Run, module: RunModule) -> None:
        await self._repository.publish(
            DashboardEvent(
                event_type=event_type,
                run_id=run.run_id,
                system_code=run.system_code,
                run_status=run.status,
                payload={
                    "module": module.model_dump(mode="json"),
                    "run_status": run.status,
                },
            )
        )

    async def _handle_module_log(self, run: Run, module: RunModule, line: str) -> None:
        trimmed = line.strip()
        if not trimmed:
            return
        module.message = trimmed
        module.logs.append(trimmed)
        await self._repository.append_module_log(run.run_id, module.module_id, trimmed)
        await self._repository.save_run(run)
        await self._repository.publish(
            DashboardEvent(
                event_type="module_log",
                run_id=run.run_id,
                system_code=run.system_code,
                run_status=run.status,
                payload={
                    "module_id": module.module_id,
                    "message": trimmed,
                },
            )
        )

    async def _analyze_module_failure(self, run: Run, module: RunModule, definition, execution_result: StepExecutionResult):
        if module.status != ModuleStatus.FAILED:
            return None
        if self._failure_analyzer is None or not getattr(self._failure_analyzer, "enabled", False):
            return None

        is_contract_detail = definition.workflow_step == "contract_detail"

        request = FailureAnalysisRequest(
            run_id=run.run_id,
            system_code=run.system_code,
            system_name=run.system_name,
            module_id=module.module_id,
            module_name=module.name,
            module_group=module.group,
            execution_mode=definition.execution_mode,
            workflow_name=definition.workflow_name,
            workflow_step=definition.workflow_step,
            current_url=None if is_contract_detail else execution_result.current_url,
            last_error=execution_result.last_error or module.message,
            recent_logs=[] if is_contract_detail else module.logs[-30:],
            dialog_messages=[] if is_contract_detail else execution_result.dialog_messages[-10:],
            screenshot_path=None if is_contract_detail else self._resolve_screenshot_path(execution_result),
            system_definition={
                "system_code": definition.system_code,
                "module_id": definition.module_id,
                "name": definition.name,
                "description": definition.description,
                "group": definition.group,
                "depends_on": definition.depends_on,
                "execution_mode": definition.execution_mode,
                "workflow_name": definition.workflow_name,
                "workflow_step": definition.workflow_step,
                "timeout_seconds": definition.timeout_seconds,
            },
        )
        try:
            return await asyncio.to_thread(self._failure_analyzer.analyze, request)
        except Exception:
            return None

    @staticmethod
    def _resolve_screenshot_path(execution_result: StepExecutionResult) -> str | None:
        if execution_result.screenshot_path is not None:
            return str(execution_result.screenshot_path)
        for artifact in execution_result.artifacts:
            if artifact.lower().endswith(".png"):
                return str(Path(artifact.lstrip("/")))
        return None

    async def _finalize_run(self, run: Run, forced_status: RunStatus | None = None) -> None:
        run.ended_at = datetime.now(UTC)
        run.awaiting_input_module_id = None
        run.awaiting_input_prompt = None
        if forced_status is not None:
            run.status = forced_status
        else:
            run.status = RunStatus.FAILED if any(module.status == ModuleStatus.FAILED for module in run.modules) else RunStatus.PASSED
        await self._repository.save_run(run)
        await self._publish_run_event("run_finished", run)
        if self._run_completion_notifier is not None:
            asyncio.create_task(self._notify_run_completion(run.model_copy(deep=True)))

    async def _notify_run_completion(self, run: Run) -> None:
        try:
            await asyncio.to_thread(self._run_completion_notifier.send_run_completion, run)
        except Exception as exc:
            print(f"[email] run={run.run_id} 종료 메일 발송 실패: {exc}")

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
        target_module.logs = await self._repository.get_module_logs(run.run_id, target_module.module_id)
        target_module.ended_at = datetime.now(UTC)
        target_module.duration_ms = int((target_module.ended_at - target_module.started_at).total_seconds() * 1000)
        await self._repository.save_run(run)
        await self._publish_module_event("module_finished", run, target_module)

    @staticmethod
    def _find_run_module(run: Run, module_id: str) -> RunModule:
        for module in run.modules:
            if module.module_id == module_id:
                return module
        raise KeyError(f"Run module not found: {module_id}")

    @staticmethod
    def _ordered_modules(system: SystemDefinition) -> list[ModuleDefinition]:
        return sorted(system.modules, key=lambda module: module.order)

    def _resolve_selected_module_ids(
        self,
        system: SystemDefinition,
        selected_module_ids: list[str] | None,
    ) -> list[str]:
        ordered_modules = self._ordered_modules(system)
        if selected_module_ids is None:
            return [module.module_id for module in ordered_modules]

        selected_values: list[str] = []
        seen_module_ids: set[str] = set()
        for raw_module_id in selected_module_ids:
            module_id = raw_module_id.strip()
            if not module_id or module_id in seen_module_ids:
                continue
            selected_values.append(module_id)
            seen_module_ids.add(module_id)

        if not selected_values:
            raise ValueError("최소 1개 이상의 모듈을 선택해야 합니다.")

        module_name_by_id = {module.module_id: module.name for module in ordered_modules}
        unknown_module_ids = [module_id for module_id in selected_values if module_id not in module_name_by_id]
        if unknown_module_ids:
            joined = ", ".join(unknown_module_ids)
            raise ValueError(f"알 수 없는 모듈이 선택되었습니다: {joined}")

        selected_set = set(selected_values)
        dependency_errors: list[str] = []
        for module in ordered_modules:
            if module.module_id not in selected_set:
                continue
            missing_dependencies = [
                dependency
                for dependency in module.depends_on
                if dependency not in selected_set
            ]
            if not missing_dependencies:
                continue
            missing_names = ", ".join(module_name_by_id[dependency] for dependency in missing_dependencies)
            dependency_errors.append(f"{module.name}: {missing_names}")

        if dependency_errors:
            raise ValueError(
                "선행 모듈이 선택되지 않아 실행할 수 없는 조합입니다. "
                + " / ".join(dependency_errors)
            )

        return [module.module_id for module in ordered_modules if module.module_id in selected_set]

    def _build_run_modules(self, system: SystemDefinition, selected_module_ids: list[str]) -> list[RunModule]:
        selected_set = set(selected_module_ids)
        run_modules: list[RunModule] = []
        for module in self._ordered_modules(system):
            is_selected = module.module_id in selected_set
            run_modules.append(
                RunModule(
                    module_id=module.module_id,
                    name=module.name,
                    group=module.group,
                    order=module.order,
                    depends_on=module.depends_on,
                    status=ModuleStatus.PENDING if is_selected else ModuleStatus.SKIPPED,
                    message="대기 중" if is_selected else "사용자 선택에서 제외됨",
                )
            )
        return run_modules

    def _ordered_selected_run_modules(self, run: Run) -> list[RunModule]:
        selected_set = set(run.selected_module_ids) or {
            module.module_id for module in run.modules if module.status != ModuleStatus.SKIPPED
        }
        return sorted(
            [module for module in run.modules if module.module_id in selected_set],
            key=lambda module: module.order,
        )
