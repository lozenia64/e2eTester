"""아웃박스 릴레이 — 프로젝션 갱신 + EventBus + 실시간 UI 디스패치."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from app.core.logging import get_logger
from app.domain.events import DomainEvent
from app.platform.eventing.bus import (
    EventBus,
    RunFinished,
    RunResumed,
    RunWaitingInput,
    SuiteFinished,
)
from app.platform.eventing.handlers import ProjectionHandlers
from app.platform.eventing.hydration import AggregateHydratorPort
from app.platform.eventing.outbox import SqliteOutbox

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class RealtimeApplyPort(Protocol):
    async def apply(self, event: DomainEvent) -> None: ...


_EVENT_BUS_MAP: dict[str, tuple[str, Callable[[object], object]]] = {
    "RunFinished": ("Run", lambda run: RunFinished(run=run)),
    "RunWaitingInput": ("Run", lambda run: RunWaitingInput(run=run)),
    "RunResumed": ("Run", lambda run: RunResumed(run=run)),
    "SuiteFinished": ("Suite", lambda payload: SuiteFinished(suite=payload[0], runs=payload[1])),
}


class OutboxRelay:
    """pending outbox 행을 폴링해 프로젝션·EventBus·RealtimeProjector 에 멱등 전달."""

    def __init__(
        self,
        outbox: SqliteOutbox,
        projections: ProjectionHandlers,
        hydrators: dict[str, AggregateHydratorPort],
        event_bus: EventBus,
        realtime: RealtimeApplyPort,
        *,
        poll_interval_seconds: float = 0.5,
        batch_size: int = 100,
    ) -> None:
        self._outbox = outbox
        self._projections = projections
        self._hydrators = hydrators
        self._event_bus = event_bus
        self._realtime = realtime
        self._poll_interval_seconds = poll_interval_seconds
        self._batch_size = batch_size
        self._running = False
        self._task: asyncio.Task | None = None
        self._claim_token = f"relay-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.relay_instance_id = id(self)

    def start(self) -> None:
        if self._running:
            logger.warning(
                "아웃박스 릴레이 이중 기동 무시",
                log_event="outbox.relay_double_start",
                relay_instance_id=self.relay_instance_id,
                pid=os.getpid(),
            )
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "아웃박스 릴레이 시작",
            log_event="outbox.relay_started",
            relay_instance_id=self.relay_instance_id,
            claim_token=self._claim_token,
            pid=os.getpid(),
        )

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
        entries = await self._outbox.claim_pending(self._batch_size, claim_token=self._claim_token)
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
                await self._outbox.release_claim(event.event_id, claim_token=self._claim_token)
                await self._outbox.move_to_dead_letter(event, str(exc))
                continue
            await self._outbox.mark_published(event.event_id, claim_token=self._claim_token)
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
        entry = _EVENT_BUS_MAP.get(event.event_type)
        if entry is None:
            return
        aggregate_type, make_bus_event = entry
        hydrator = self._hydrators.get(aggregate_type)
        if hydrator is None:
            return
        payload = await hydrator.hydrate(event.aggregate_id)
        await self._event_bus.publish(make_bus_event(payload))
