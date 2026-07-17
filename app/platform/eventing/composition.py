"""이벤트 배선 composition — EventBus + 도메인 구독자."""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.failure_analyzer import GeminiFailureAnalyzer
from app.platform.eventing.bus import EventBus
from app.platform.eventing.subscribers.email_notification import EmailNotificationSubscriber
from app.platform.eventing.subscribers.failure_analysis import FailureAnalysisSubscriber
from app.platform.eventing.support import SqliteDatabase
from app.registry.loader import ModuleRegistry
from app.storage.sqlite_email_notification_dedup import SqliteEmailNotificationDedupStore
from app.storage.sqlite_run_write_repository import SqliteRunWriteRepository


@dataclass(frozen=True)
class EventingComposition:
    event_bus: EventBus
    email_dedup_store: SqliteEmailNotificationDedupStore
    email_subscriber: EmailNotificationSubscriber


def compose_event_bus(
    *,
    registry: ModuleRegistry,
    run_write_repo: SqliteRunWriteRepository,
    system_codes: list[str],
    es_db: SqliteDatabase,
) -> EventingComposition:
    event_bus = EventBus()
    failure_analyzer = GeminiFailureAnalyzer.from_env()
    FailureAnalysisSubscriber(failure_analyzer, run_write_repo, registry).register(event_bus)
    email_dedup_store = SqliteEmailNotificationDedupStore(es_db)
    email_subscriber = EmailNotificationSubscriber(
        system_codes,
        dedup_store=email_dedup_store,
    )
    email_subscriber.register(event_bus)
    return EventingComposition(
        event_bus=event_bus,
        email_dedup_store=email_dedup_store,
        email_subscriber=email_subscriber,
    )
