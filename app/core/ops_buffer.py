"""프로세스 내 최근 운영 이벤트 링 버퍼 — 관리자 운영 관측 UI용."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class OpsEvent:
    ts: str
    event: str
    level: str
    component: str
    message: str
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "event": self.event,
            "level": self.level,
            "component": self.component,
            "message": self.message,
            "fields": self.fields,
        }


class OpsEventBuffer:
    def __init__(self, capacity: int = 250) -> None:
        self._capacity = max(1, capacity)
        self._events: deque[OpsEvent] = deque(maxlen=self._capacity)
        self._lock = threading.Lock()

    def record(
        self,
        *,
        event: str,
        message: str,
        level: str = "info",
        component: str | None = None,
        **fields: Any,
    ) -> None:
        resolved_component = component or (event.split(".", 1)[0] if "." in event else "ops")
        payload = {key: value for key, value in fields.items() if value is not None}
        entry = OpsEvent(
            ts=datetime.now(UTC).isoformat(),
            event=event,
            level=level,
            component=resolved_component,
            message=message,
            fields=payload,
        )
        with self._lock:
            self._events.append(entry)

    def list_recent(self, limit: int = 80) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._events)
        if limit < 1:
            return []
        return [item.to_dict() for item in items[-limit:]]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


ops_event_buffer = OpsEventBuffer()
