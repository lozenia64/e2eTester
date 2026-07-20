"""이벤트 배선 composition — EventBus + 도메인 구독자."""

from __future__ import annotations

from dataclasses import dataclass

from app.notifications.infrastructure.sqlite_email_notification_dedup import (
    SqliteEmailNotificationDedupStore,
)
from app.platform.eventing.bus import EventBus
from app.platform.eventing.subscribers.email_notification import EmailNotificationSubscriber
from app.platform.eventing.support import SqliteDatabase


@dataclass(frozen=True)
class EventingContainer:
    event_bus: EventBus
    email_dedup_store: SqliteEmailNotificationDedupStore
    email_subscriber: EmailNotificationSubscriber


def compose_event_bus(
    *,
    system_codes: list[str],
    es_db: SqliteDatabase,
) -> EventingContainer:
    event_bus = EventBus()
    email_dedup_store = SqliteEmailNotificationDedupStore(es_db)
    email_subscriber = EmailNotificationSubscriber(
        system_codes,
        dedup_store=email_dedup_store,
    )
    email_subscriber.register(event_bus)
    return EventingContainer(
        event_bus=event_bus,
        email_dedup_store=email_dedup_store,
        email_subscriber=email_subscriber,
    )
