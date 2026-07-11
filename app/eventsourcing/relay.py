"""아웃박스 릴레이 — 프로젝션 갱신 + EventBus + 실시간 UI 디스패치."""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.domain.events import DomainEvent
from app.domain.run_aggregate import RunAggregate
from app.events.bus import EventBus, RunFinished, RunResumed, RunWaitingInput, SuiteFinished
from app.eventsourcing.outbox import SqliteOutbox
from app.projections.handlers import ProjectionHandlers
from app.realtime.projector import RealtimeProjector
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository

logger = get_logger(__name__)

_EVENT_BUS_MAP: dict[str, type] = {
    "RunFinished": RunFinished,
    "RunWaitingInput": RunWaitingInput,
    "RunResumed": RunResumed,
    "SuiteFinished": SuiteFinished,
}


class OutboxRelay:
    """pending outbox 행을 폴링해 프로젝션·EventBus·RealtimeProjector 에 멱등 전달."""

    def __init__(
        self,
        outbox: SqliteOutbox,
        projections: ProjectionHandlers,
        write_repo: SqliteRunWriteRepository,
        event_bus: EventBus,
        realtime: RealtimeProjector,
        *,
        poll_interval_seconds: float = 0.5,
        batch_size: int = 100,
        log_store=None,
        suite_finished_loader=None,
    ) -> None:
        self._outbox = outbox
        self._projections = projections
        self._write_repo = write_repo
        self._event_bus = event_bus
        self._realtime = realtime
        self._poll_interval_seconds = poll_interval_seconds
        self._batch_size = batch_size
        self._log_store = log_store
        self._suite_finished_loader = suite_finished_loader
        self._running = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def process_once(self) -> int:
        """한 번 폴링·처리(테스트/마이그레이션용). 처리한 이벤트 수 반환."""
        entries = await self._outbox.claim_pending(self._batch_size)
        if not entries:
            return 0
        processed = 0
        for entry in entries:
            event = entry.event
            try:
                await self._projections.apply(event, entry.sequence_id)
                await self._maybe_dispatch_event_bus(event)
                await self._realtime.apply(event)
            except Exception as exc:
                logger.exception(
                    "아웃박스 이벤트 처리 실패",
                    log_event="outbox.relay_failed",
                    event_id=event.event_id,
                    event_type=event.event_type,
                )
                await self._outbox.move_to_dead_letter(event, str(exc))
                continue
            await self._outbox.mark_published(event.event_id)
            processed += 1
        return processed

    async def _loop(self) -> None:
        while self._running:
            try:
                processed = await self.process_once()
                if processed == 0:
                    await asyncio.sleep(self._poll_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("아웃박스 릴레이 루프 오류", log_event="outbox.relay_loop_failed")
                await asyncio.sleep(self._poll_interval_seconds)

    async def _maybe_dispatch_event_bus(self, event: DomainEvent) -> None:
        bus_type = _EVENT_BUS_MAP.get(event.event_type)
        if bus_type is None:
            return
        if bus_type is RunFinished:
            run = await self._hydrate_run(event.aggregate_id)
            await self._event_bus.publish(RunFinished(run=run))
        elif bus_type is RunWaitingInput:
            run = await self._hydrate_run(event.aggregate_id)
            await self._event_bus.publish(RunWaitingInput(run=run))
        elif bus_type is RunResumed:
            run = await self._hydrate_run(event.aggregate_id)
            await self._event_bus.publish(RunResumed(run=run))
        elif bus_type is SuiteFinished:
            if self._suite_finished_loader is None:
                return
            suite, runs = await self._suite_finished_loader(event.aggregate_id)
            await self._event_bus.publish(SuiteFinished(suite=suite, runs=runs))

    async def _hydrate_run(self, run_id: str):
        run = await self._write_repo.get_run(run_id)
        if self._log_store is not None:
            logs_by_module = await self._log_store.get_all(run_id)
            RunAggregate(run).hydrate_logs(logs_by_module)
        return run
