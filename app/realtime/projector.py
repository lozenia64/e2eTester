"""도메인 이벤트 → WebSocket DashboardEvent/SuiteEvent 프로젝션.

**blob 재수화 없음**: 실시간 WS payload 는 오직 이벤트 payload(fat event)에서 조립한다.
Run 상태 변경 이벤트는 ``run_summary`` 섹션(``RunView`` 계약)을, 모듈 전이 이벤트는
``module`` 와이어 dict + ``run_status``(``ModuleView`` 계약)를 실어 나른다. 따라서 이 프로젝터
는 Run/Suite 상태 저장소(blob)나 로그 스토어를 전혀 읽지 않는다 — WS 이벤트가 고빈도임을
고려한 읽기 경로 blob 제거의 핵심.

단건 상세(스냅샷)는 여기가 아니라 WS 접속 시 ``RunQueries.get_run_detail``(합법적 단일 로드)
가 만든다. Suite 는 아직 요약 프로젝션으로 완전 이전 전이라, suite payload 는 ``suite_summary``
(fat event, WP-A2)를 그대로 실어 보낸다.
"""

from __future__ import annotations

from app.contexts.run.views.view import RunView
from app.contexts.suite.views.view import SuiteView
from app.core.enums import RunStatus, SuiteStatus
from app.core.run_models import DashboardEvent
from app.core.suite_models import SuiteEvent
from app.domain.events import DomainEvent
from app.realtime.ports import RealtimeNotificationPort, SuiteRealtimeNotificationPort

# module_* WS 이벤트를 만드는 Run 이벤트 → 와이어 이벤트 타입.
_MODULE_WIRE = {
    "ModuleQueued": "module_queued",
    "ModuleStarted": "module_started",
    "ModuleFinished": "module_finished",
    "ModuleFailureAnalysisAttached": "module_finished",
    "RunModuleBlocked": "module_finished",
    "RunModuleRetried": "module_queued",
}

# run_* WS 이벤트를 만드는 Run 이벤트 → 와이어 이벤트 타입.
# ``RunSealedInterrupted`` 는 뒤이어 ``RunFinished`` 도 발행하므로 여기 넣지 않는다(중복 방지).
_RUN_WIRE = {
    "RunCreated": "run_created",
    "RunStarted": "run_started",
    "RunFinished": "run_finished",
}


class RealtimeProjector:
    """Outbox 릴레이가 호출하는 실시간 UI 이벤트 변환기(이벤트 payload → WS payload)."""

    def __init__(
        self,
        run_realtime: RealtimeNotificationPort,
        suite_realtime: SuiteRealtimeNotificationPort,
        *,
        run_loader=None,
        suite_loader=None,
        log_store=None,
    ) -> None:
        self._run_realtime = run_realtime
        self._suite_realtime = suite_realtime
        # run_loader/suite_loader/log_store 는 더 이상 쓰지 않는다(blob 미접근). 기존 배선
        # 호환을 위해 시그니처만 유지한다(컴포지션 루트가 넘겨도 무시).

    async def apply(self, event: DomainEvent) -> None:
        if event.aggregate_type == "Run":
            await self._apply_run(event)
        elif event.aggregate_type == "Suite":
            await self._apply_suite(event)

    async def _apply_run(self, event: DomainEvent) -> None:
        # 로그(module_log)는 더 이상 도메인 이벤트가 아니다(WP-B5) — RunService 가 실시간 채널로
        # 직접 발행하므로 이 프로젝터(아웃박스 릴레이 경로)는 로그를 다루지 않는다.
        run_id = event.aggregate_id
        summary = event.payload.get("run_summary")

        system_code = summary["system_code"] if summary else ""
        run_status = (
            RunStatus(event.payload["run_status"]) if "run_status" in event.payload else None
        )

        if event.event_type == "RunModulesCancelled":
            status = run_status or RunStatus.CANCELLED
            for module in event.payload.get("modules", []):
                await self._publish_module_event(
                    run_id, system_code, module, status, "module_finished"
                )
            return

        if event.event_type == "RunWaitingInput":
            await self._publish_module_event(
                run_id, system_code, event.payload.get("module"), run_status, "module_waiting_input"
            )
            if summary is not None:
                await self._publish_run_event(run_id, summary, "run_waiting_input")
            return

        if event.event_type == "RunResumed":
            if summary is not None:
                await self._publish_run_event(run_id, summary, "run_resumed")
            await self._publish_module_event(
                run_id, system_code, event.payload.get("module"), run_status, "module_queued"
            )
            return

        module_wire = _MODULE_WIRE.get(event.event_type)
        if module_wire is not None:
            await self._publish_module_event(
                run_id, system_code, event.payload.get("module"), run_status, module_wire
            )
            return

        run_wire = _RUN_WIRE.get(event.event_type)
        if run_wire is not None and summary is not None:
            await self._publish_run_event(run_id, summary, run_wire)

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
        summary = event.payload.get("suite_summary")
        if summary is None:
            return
        payload = SuiteView.dump_from_summary(event.aggregate_id, summary)
        # 상태머신 결정 등 이벤트별 부가 필드(step_index 등)를 payload 에 덧붙인다.
        for key, value in event.payload.items():
            if key != "suite_summary":
                payload[key] = value
        await self._suite_realtime.publish(
            SuiteEvent(
                event_type=suite_wire,
                suite_id=event.aggregate_id,
                suite_status=SuiteStatus(summary["status"]),
                payload=payload,
            )
        )

    async def _publish_run_event(self, run_id: str, summary: dict, wire_type: str) -> None:
        await self._run_realtime.publish(
            DashboardEvent(
                event_type=wire_type,
                run_id=run_id,
                system_code=summary["system_code"],
                run_status=RunStatus(summary["status"]),
                payload=RunView.dump_from_summary(run_id, summary),
            )
        )

    async def _publish_module_event(
        self,
        run_id: str,
        system_code: str,
        module: dict | None,
        run_status: RunStatus | None,
        wire_type: str,
    ) -> None:
        if module is None or run_status is None:
            return
        await self._run_realtime.publish(
            DashboardEvent(
                event_type=wire_type,
                run_id=run_id,
                system_code=system_code,
                run_status=run_status,
                payload={"module": module, "run_status": run_status.value},
            )
        )
