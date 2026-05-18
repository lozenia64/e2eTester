from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import DashboardEvent, FailureAnalysisRequest, Run, RunModule
from app.registry.loader import ModuleRegistry
from app.runner.artifact_manager import ArtifactManager
from app.runner.hom_workflow_executor import HomWorkflowExecutor, HomWorkflowRuntime, StepExecutionResult
from app.storage.run_repository import InMemoryRunRepository


@dataclass
class PendingOtpState:
    run_id: str
    input_data: dict[str, str]
    start_index: int
    runtime: HomWorkflowRuntime


class RunService:
    def __init__(self, registry: ModuleRegistry, repository: InMemoryRunRepository, failure_analyzer=None) -> None:
        self._registry = registry
        self._repository = repository
        self._artifact_manager = ArtifactManager()
        self._hom_executor = HomWorkflowExecutor(self._artifact_manager)
        self._pending_otp: dict[str, PendingOtpState] = {}
        self._failure_analyzer = failure_analyzer

    def list_systems(self):
        return self._registry.list_systems()

    async def get_run(self, run_id: str) -> Run:
        return await self._repository.get_run(run_id)

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
        self._hom_executor.update_otp_code(pending.runtime, pending.input_data["otp_code"])
        run.status = RunStatus.RUNNING
        run.awaiting_input_module_id = None
        run.awaiting_input_prompt = None
        waiting_module = run.modules[pending.start_index]
        waiting_module.status = ModuleStatus.QUEUED
        waiting_module.message = "OTP 입력이 접수되어 재개 대기 중"
        await self._repository.save_run(run)
        await self._publish_module_event("module_queued", run, waiting_module)
        await self._publish_run_event("run_resumed", run)
        del self._pending_otp[run_id]
        asyncio.create_task(self._execute_run(run_id, pending.input_data, pending.start_index, pending.runtime))
        return run

    async def start_run(self, system_code: str, input_data: dict[str, str] | None = None) -> Run:
        system = self.get_system(system_code)
        run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        sanitized_input = {key: value.strip() for key, value in (input_data or {}).items()}
        auth_method = sanitized_input.get("auth_method", "phone")
        if auth_method != "phone":
            raise ValueError("현재는 휴대폰인증만 실행할 수 있습니다.")
        run = Run(
            run_id=run_id,
            system_code=system.system_code,
            system_name=system.name,
            status=RunStatus.PENDING,
            requested_at=datetime.now(UTC),
            modules=[
                RunModule(
                    module_id=module.module_id,
                    name=module.name,
                    group=module.group,
                    order=module.order,
                    depends_on=module.depends_on,
                )
                for module in system.modules
            ],
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
        hom_runtime: HomWorkflowRuntime | None = None,
    ) -> None:
        run = await self._repository.get_run(run_id)
        if start_index == 0:
            run.status = RunStatus.RUNNING
            run.started_at = datetime.now(UTC)
            await self._repository.save_run(run)
            await self._publish_run_event("run_started", run)
        event_loop = asyncio.get_running_loop()

        definitions = {
            module.module_id: module
            for module in self._registry.get_system(run.system_code).modules
        }

        modules_by_id = {module.module_id: module for module in run.modules}
        ordered_modules = sorted(run.modules, key=lambda item: item.order)

        try:
            for index, module in enumerate(ordered_modules[start_index:], start=start_index):
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
                if definition.execution_mode == "hom_workflow_step":
                    if hom_runtime is None:
                        try:
                            hom_runtime = await asyncio.to_thread(
                                self._hom_executor.build_runtime,
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

                    execution_result = await asyncio.to_thread(
                        self._hom_executor.execute_step,
                        hom_runtime,
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
                            start_index=index,
                            runtime=hom_runtime,
                        )
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
        finally:
            if hom_runtime is not None and run.run_id not in self._pending_otp:
                await asyncio.to_thread(self._hom_executor.close_runtime, hom_runtime)

        run.ended_at = datetime.now(UTC)
        run.awaiting_input_module_id = None
        run.awaiting_input_prompt = None
        run.status = RunStatus.FAILED if any(module.status == ModuleStatus.FAILED for module in run.modules) else RunStatus.PASSED
        await self._repository.save_run(run)
        await self._publish_run_event("run_finished", run)

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
