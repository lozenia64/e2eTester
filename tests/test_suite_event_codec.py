"""SuiteEventCodec payload 키 집합 불변 테스트 — 8개 Suite 이벤트 전부."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contexts.suite.domain.events import (
    SuiteCreated,
    SuiteEventRecord,
    SuiteFinished,
    SuiteResumed,
    SuiteStarted,
    SuiteStepFinished,
    SuiteStepRunLinked,
    SuiteStepStarted,
    SuiteWaitingInput,
)
from app.contexts.suite.infrastructure.codec import SuiteEventCodec
from app.core.enums import SuiteStatus

_CODEC = SuiteEventCodec()
_SUITE_ID = "suite_codec"
_NOW = datetime(2026, 7, 12, 3, 0, tzinfo=UTC)
_SUMMARY = {
    "status": SuiteStatus.RUNNING.value,
    "steps": [
        {
            "system_code": "hom",
            "system_name": "HOM",
            "order": 0,
            "run_id": "run_child",
            "status": SuiteStatus.RUNNING.value,
            "module_total": 3,
        }
    ],
    "current_step_index": 0,
    "requested_at": _NOW.isoformat(),
    "started_at": _NOW.isoformat(),
    "ended_at": None,
    "active_run_id": "run_child",
    "awaiting_input_run_id": None,
    "awaiting_input_prompt": None,
    "browser_mode": "headed",
    "selected_system_codes": ["hom"],
    "created_by_user_id": None,
    "created_by_user_name": None,
    "triggered_by": "manual",
    "schedule_id": None,
}


def _record(event) -> SuiteEventRecord:
    return SuiteEventRecord(
        event=event,
        suite_summary=_SUMMARY,
        event_id="evt_suite_codec",
        occurred_at=_NOW,
    )


def _payload_keys(event) -> frozenset[str]:
    envelope = _CODEC.encode(_SUITE_ID, _record(event))
    return frozenset(envelope.payload.keys()) - {"suite_summary"}


@pytest.mark.parametrize(
    ("event", "expected_keys"),
    [
        (SuiteCreated(triggered_by="manual"), {"triggered_by"}),
        (SuiteStarted(), set()),
        (SuiteStepStarted(step_index=0), {"step_index"}),
        (SuiteStepRunLinked(step_index=0, run_id="run_child"), {"step_index", "run_id"}),
        (SuiteStepFinished(step_index=0), {"step_index"}),
        (SuiteStepFinished(step_index=0, error="boom"), {"step_index", "error"}),
        (SuiteWaitingInput(run_id="run_child"), {"run_id"}),
        (SuiteResumed(), set()),
        (SuiteFinished(status=SuiteStatus.PASSED), {"status"}),
    ],
)
def test_suite_event_payload_key_invariant(event, expected_keys):
    assert _payload_keys(event) == expected_keys


@pytest.mark.parametrize(
    "event",
    [
        SuiteCreated(triggered_by="manual"),
        SuiteStarted(),
        SuiteStepStarted(step_index=0),
        SuiteStepRunLinked(step_index=0, run_id="run_child"),
        SuiteStepFinished(step_index=0),
        SuiteStepFinished(step_index=0, error="boom"),
        SuiteWaitingInput(run_id="run_child"),
        SuiteResumed(),
        SuiteFinished(status=SuiteStatus.PASSED),
    ],
)
def test_suite_event_codec_roundtrip(event):
    record = _record(event)
    envelope = _CODEC.encode(_SUITE_ID, record)
    decoded = _CODEC.decode(envelope)
    assert type(decoded.event) is type(event)
    assert decoded.suite_summary == record.suite_summary
    assert decoded.event_id == record.event_id
    assert decoded.version == record.version
