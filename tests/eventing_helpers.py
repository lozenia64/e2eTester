"""테스트용 OutboxRelay / ProjectionHandlers 팩토리."""

from __future__ import annotations

from app.contexts.run.infrastructure.hydration import RunHydrator, RunProjectionLoader
from app.contexts.run.infrastructure.sqlite_run_write_repository import SqliteRunWriteRepository
from app.platform.eventing.bus import EventBus
from app.platform.eventing.handlers import ProjectionHandlers
from app.platform.eventing.outbox import SqliteOutbox
from app.platform.eventing.relay import OutboxRelay
from app.platform.eventing.support import SqliteDatabase
from app.realtime.projector import RealtimeProjector


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
