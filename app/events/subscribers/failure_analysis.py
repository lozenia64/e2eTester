from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.enums import ModuleStatus
from app.core.models import (
    FailureAnalysis,
    FailureAnalysisRequest,
    ModuleDefinition,
    Run,
    RunModule,
)
from app.events.bus import EventBus, RunFinished
from app.orchestrator.run_event_publisher import RunEventPublisher


class FailureAnalysisSubscriber:
    """Run 종료 후 실패 모듈을 AI 로 분석해 결과를 덧붙이는 구독자.

    오케스트레이터에서 분리된 부수 관심사다. 분석은 Run 종료 이후 비동기로 수행되며,
    결과가 준비되면 해당 모듈을 갱신·저장하고 ``module_finished`` 이벤트를 다시 발행해
    대시보드가 분석 결과를 반영하도록 한다(프런트는 ``payload.module`` 을 든 모든 이벤트로
    카드를 갱신한다). AI 분석이 비활성이거나 실패해도 Run 판정/표시에는 영향이 없다.

    분석에 필요한 진단 정보(현재 URL·다이얼로그·스크린샷)는 단계 실행 시점에 ``RunModule``
    에 영속되므로, 이 구독자는 실행 컨텍스트 없이 종료된 Run 만으로 분석을 재구성한다.
    """

    def __init__(self, analyzer, repository, registry) -> None:
        self._analyzer = analyzer
        self._repository = repository
        self._registry = registry
        self._events = RunEventPublisher(repository)

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(RunFinished, self.on_run_finished)

    @property
    def _enabled(self) -> bool:
        return self._analyzer is not None and getattr(self._analyzer, "enabled", False)

    async def on_run_finished(self, event: RunFinished) -> None:
        if not self._enabled:
            return
        run = event.run
        failed_modules = [module for module in run.modules if module.status == ModuleStatus.FAILED]
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
            module.failure_analysis = analysis
            await self._repository.save_run(run)
            # 분석 결과를 모듈 카드에 반영하도록 module_finished 를 다시 발행한다.
            await self._events.module_event("module_finished", run, module)

    async def _analyze(self, run: Run, module: RunModule, definition: ModuleDefinition) -> FailureAnalysis | None:
        request = self._build_request(run, module, definition)
        try:
            return await asyncio.to_thread(self._analyzer.analyze, request)
        except Exception:
            return None

    def _build_request(self, run: Run, module: RunModule, definition: ModuleDefinition) -> FailureAnalysisRequest:
        # 계약상세(contract_detail) 화면은 PII 노출 위험이 있어 URL/로그/다이얼로그/스크린샷을
        # AI 에 보내지 않는다(기존 정책 보존).
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
