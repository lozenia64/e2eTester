from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.models import (
    FailureAnalysis,
    FailureAnalysisRequest,
    ModuleDefinition,
    Run,
    RunModule,
)
from app.core.status_labels import MODULE_ANOMALY_STATUSES
from app.domain.run_aggregate import RunAggregate
from app.events.bus import EventBus, RunFinished


class FailureAnalysisSubscriber:
    """Run 종료 후 실패 모듈을 AI 로 분석해 결과를 덧붙이는 구독자."""

    def __init__(self, analyzer, write_repo, registry) -> None:
        self._analyzer = analyzer
        self._write_repo = write_repo
        self._registry = registry

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(RunFinished, self.on_run_finished)

    @property
    def _enabled(self) -> bool:
        return self._analyzer is not None and getattr(self._analyzer, "enabled", False)

    async def on_run_finished(self, event: RunFinished) -> None:
        if not self._enabled:
            return
        run = event.run
        failed_modules = [
            module for module in run.modules if module.status in MODULE_ANOMALY_STATUSES
        ]
        if not failed_modules:
            return
        try:
            system = self._registry.get_system(run.system_code)
        except KeyError:
            return
        definitions = {definition.module_id: definition for definition in system.modules}

        for module in failed_modules:
            definition = definitions.get(module.module_id)
            if definition is None:
                continue
            analysis = await self._analyze(run, module, definition)
            if analysis is None:
                continue
            aggregate = RunAggregate(run)
            aggregate.attach_failure_analysis(module, analysis)
            await self._write_repo.save_run(run, events=aggregate.pull_events())

    async def _analyze(
        self, run: Run, module: RunModule, definition: ModuleDefinition
    ) -> FailureAnalysis | None:
        request = self._build_request(run, module, definition)
        try:
            return await asyncio.to_thread(self._analyzer.analyze, request)
        except Exception:
            return None

    def _build_request(
        self, run: Run, module: RunModule, definition: ModuleDefinition
    ) -> FailureAnalysisRequest:
        is_contract_detail = definition.workflow_step == "contract_detail"
        return FailureAnalysisRequest(
            run_id=run.run_id,
            system_code=run.system_code,
            system_name=run.system_name,
            module_id=module.module_id,
            module_name=module.name,
            module_group=module.group,
            execution_mode=definition.execution_mode,
            workflow_name=definition.workflow_name,
            workflow_step=definition.workflow_step,
            current_url=None if is_contract_detail else module.current_url,
            last_error=module.message,
            recent_logs=[] if is_contract_detail else module.logs[-30:],
            dialog_messages=[] if is_contract_detail else module.dialog_messages[-10:],
            screenshot_path=None if is_contract_detail else self._screenshot_path(module),
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

    @staticmethod
    def _screenshot_path(module: RunModule) -> str | None:
        for artifact in module.artifacts:
            if artifact.lower().endswith(".png"):
                return str(Path(artifact.lstrip("/")))
        return None
