"""테스트용 OutboxRelay / ProjectionHandlers 팩토리."""

from __future__ import annotations

from app.contexts.run.domain.events import RunEventRecord
from app.contexts.run.infrastructure.codec import RunEventCodec
from app.contexts.run.infrastructure.hydration import RunHydrator, RunProjectionLoader
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.contexts.suite.domain.events import SuiteEventRecord
from app.contexts.suite.infrastructure.codec import SuiteEventCodec
from app.platform.eventing.bus import EventBus
from app.platform.eventing.envelope import EventEnvelope
from app.platform.eventing.handlers import ProjectionHandlers
from app.platform.eventing.outbox import SqliteOutbox
from app.platform.eventing.relay import OutboxRelay
from app.platform.eventing.support import SqliteDatabase
from app.realtime.projector import RealtimeProjector

_RUN_CODEC = RunEventCodec()
_SUITE_CODEC = SuiteEventCodec()


def run_events_as_envelopes(run_id: str, records: list[RunEventRecord]) -> list[EventEnvelope]:
    return [_RUN_CODEC.encode(run_id, record) for record in records]


def suite_events_as_envelopes(
    suite_id: str, records: list[SuiteEventRecord]
) -> list[EventEnvelope]:
    return [_SUITE_CODEC.encode(suite_id, record) for record in records]


def make_projection_handlers(
    db: SqliteDatabase,
    write_repo: SqliteRunWriteRepository,
) -> ProjectionHandlers:
    return ProjectionHandlers(db, loaders={"Run": RunProjectionLoader(write_repo)})


def make_outbox_relay(
    outbox: SqliteOutbox,
    projections: ProjectionHandlers,
    write_repo: SqliteRunWriteRepository,
    event_bus: EventBus,
    projector: RealtimeProjector,
    *,
    log_store=None,
) -> OutboxRelay:
    return OutboxRelay(
        outbox,
        projections,
        hydrators={"Run": RunHydrator(write_repo, log_store)},
        event_bus=event_bus,
        realtime=projector,
    )
