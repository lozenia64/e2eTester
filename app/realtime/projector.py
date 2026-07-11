"""도메인 이벤트 → WebSocket DashboardEvent/SuiteEvent 프로젝션."""

from __future__ import annotations

from app.core.models import DashboardEvent, SuiteEvent
from app.domain.events import DomainEvent
from app.domain.run_aggregate import RunAggregate
from app.orchestrator.module_view import ModuleView
from app.orchestrator.run_view import RunView
from app.orchestrator.suite_view import SuiteView
from app.realtime.ports import RealtimeNotificationPort, SuiteRealtimeNotificationPort


class RealtimeProjector:
    """Outbox 릴레이가 호출하는 실시간 UI 이벤트 변환기."""

    def __init__(
        self,
        run_realtime: RealtimeNotificationPort,
        suite_realtime: SuiteRealtimeNotificationPort,
        *,
        run_loader,
        suite_loader,
        log_store=None,
    ) -> None:
        self._run_realtime = run_realtime
        self._suite_realtime = suite_realtime
        self._run_loader = run_loader
        self._suite_loader = suite_loader
        self._log_store = log_store

    async def apply(self, event: DomainEvent) -> None:
        if event.aggregate_type == "Run":
            await self._apply_run(event)
        elif event.aggregate_type == "Suite":
            await self._apply_suite(event)

    async def _apply_run(self, event: DomainEvent) -> None:
        if event.event_type == "ModuleLogAppended":
            run = await self._hydrate_run(event.aggregate_id)
            await self._run_realtime.publish(
                DashboardEvent(
                    event_type="module_log",
                    run_id=run.run_id,
                    system_code=run.system_code,
                    run_status=run.status,
                    payload={
                        "module_id": event.payload["module_id"],
                        "message": event.payload["message"],
                    },
                )
            )
            return

        if event.event_type == "RunModulesCancelled":
            run = await self._hydrate_run(event.aggregate_id)
            aggregate = RunAggregate(run)
            for module_id in event.payload.get("module_ids", []):
                module = aggregate.module(module_id)
                await self._publish_module_event(run, module, "module_finished")
            return

        module_events = {
            "ModuleQueued",
            "ModuleStarted",
            "ModuleFinished",
            "ModuleFailureAnalysisAttached",
            "RunModuleBlocked",
        }
        if event.event_type in module_events:
            run = await self._hydrate_run(event.aggregate_id)
            module = RunAggregate(run).module(event.payload["module_id"])
            wire = {
                "ModuleQueued": "module_queued",
                "ModuleStarted": "module_started",
            }.get(event.event_type, "module_finished")
            await self._publish_module_event(run, module, wire)
            return

        if event.event_type == "RunWaitingInput":
            run = await self._hydrate_run(event.aggregate_id)
            module = RunAggregate(run).module(event.payload["module_id"])
            await self._publish_module_event(run, module, "module_waiting_input")
            await self._publish_run_event(run, "run_waiting_input")
            return

        if event.event_type == "RunResumed":
            run = await self._hydrate_run(event.aggregate_id)
            module = RunAggregate(run).module(event.payload["module_id"])
            await self._publish_run_event(run, "run_resumed")
            await self._publish_module_event(run, module, "module_queued")
            return

        run_wire = {
            "RunCreated": "run_created",
            "RunStarted": "run_started",
            "RunFinished": "run_finished",
        }.get(event.event_type)
        if run_wire is not None:
            run = await self._hydrate_run(event.aggregate_id)
            await self._publish_run_event(run, run_wire)

    async def _apply_suite(self, event: DomainEvent) -> None:
        suite_wire = {
            "SuiteCreated": "suite_created",
            "SuiteStarted": "suite_started",
            "SuiteStepStarted": "suite_step_started",
            "SuiteStepRunLinked": "suite_step_run_linked",
            "SuiteStepFinished": "suite_step_finished",
            "SuiteWaitingInput": "suite_waiting_input",
            "SuiteResumed": "suite_resumed",
            "SuiteFinished": "suite_finished",
        }.get(event.event_type)
        if suite_wire is None:
            return
        suite = await self._suite_loader(event.aggregate_id)
        payload = SuiteView.dump(suite)
        payload.update(event.payload)
        await self._suite_realtime.publish(
            SuiteEvent(
                event_type=suite_wire,
                suite_id=suite.suite_id,
                suite_status=suite.status,
                payload=payload,
            )
        )

    async def _publish_run_event(self, run, wire_type: str) -> None:
        await self._run_realtime.publish(
            DashboardEvent(
                event_type=wire_type,
                run_id=run.run_id,
                system_code=run.system_code,
                run_status=run.status,
                payload=RunView.dump(run),
            )
        )

    async def _publish_module_event(self, run, module, wire_type: str) -> None:
        await self._run_realtime.publish(
            DashboardEvent(
                event_type=wire_type,
                run_id=run.run_id,
                system_code=run.system_code,
                run_status=run.status,
                payload=ModuleView.dump(module, run),
            )
        )

    async def _hydrate_run(self, run_id: str):
        run = await self._run_loader(run_id)
        if self._log_store is not None:
            logs_by_module = await self._log_store.get_all(run_id)
            RunAggregate(run).hydrate_logs(logs_by_module)
        return run
