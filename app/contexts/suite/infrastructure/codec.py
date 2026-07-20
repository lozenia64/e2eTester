"""SuiteEventRecord ↔ EventEnvelope 인코더(다형성 없음 — Suite 컨텍스트 전용)."""

from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from app.contexts.suite.domain.events import (
    SuiteCreated,
    SuiteEvent,
    SuiteEventRecord,
    SuiteFinished,
    SuiteResumed,
    SuiteStarted,
    SuiteStepFinished,
    SuiteStepRunLinked,
    SuiteStepStarted,
    SuiteWaitingInput,
)
from app.core.enums import SuiteStatus
from app.platform.eventing.envelope import EventEnvelope


class SuiteEventCodec:
    """SuiteEventRecord ↔ EventEnvelope(aggregate_type=\"Suite\")."""

    _TYPES: dict[str, type] = {
        "SuiteCreated": SuiteCreated,
        "SuiteStarted": SuiteStarted,
        "SuiteStepStarted": SuiteStepStarted,
        "SuiteStepRunLinked": SuiteStepRunLinked,
        "SuiteStepFinished": SuiteStepFinished,
        "SuiteWaitingInput": SuiteWaitingInput,
        "SuiteResumed": SuiteResumed,
        "SuiteFinished": SuiteFinished,
    }

    def encode(self, suite_id: str, record: SuiteEventRecord) -> EventEnvelope:
        event_type = type(record.event).__name__
        payload = _event_to_payload(record.event)
        if record.suite_summary is not None:
            payload["suite_summary"] = record.suite_summary
        return EventEnvelope(
            event_id=record.event_id,
            aggregate_type="Suite",
            aggregate_id=suite_id,
            event_type=event_type,
            payload=payload,
            occurred_at=record.occurred_at,
            version=record.version,
        )

    def decode(self, envelope: EventEnvelope) -> SuiteEventRecord:
        cls = self._TYPES[envelope.event_type]
        payload = dict(envelope.payload)
        suite_summary = payload.pop("suite_summary", None)
        event = _payload_to_event(cls, payload)
        return SuiteEventRecord(
            event=event,
            suite_summary=suite_summary,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
            version=envelope.version,
        )


def _event_to_payload(event: SuiteEvent) -> dict[str, Any]:
    if isinstance(event, SuiteStarted | SuiteResumed):
        return {}
    if isinstance(event, SuiteFinished):
        return {"status": event.status.value}
    if isinstance(event, SuiteStepFinished):
        payload: dict[str, Any] = {"step_index": event.step_index}
        if event.error is not None:
            payload["error"] = event.error
        return payload
    return asdict(event)


def _payload_to_event(cls: type, payload: dict[str, Any]) -> SuiteEvent:
    field_names = {f.name for f in fields(cls)}
    kwargs = {k: v for k, v in payload.items() if k in field_names}
    if cls is SuiteFinished and "status" in kwargs:
        kwargs["status"] = SuiteStatus(kwargs["status"])
    if cls is SuiteStepFinished and "error" not in payload:
        kwargs.setdefault("error", None)
    return cls(**kwargs)  # type: ignore[call-arg]
