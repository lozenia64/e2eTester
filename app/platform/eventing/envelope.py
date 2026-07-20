"""도메인 이벤트 물리 봉투 — event store/outbox/relay 가 다루는 직렬화 단위."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class EventEnvelope:
    """모든 도메인 이벤트의 공통 메타데이터(온디스크 domain_events/outbox 행)."""

    event_id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: int = 1

    @staticmethod
    def create(
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        version: int = 1,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_id=uuid4().hex,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            version=version,
        )
