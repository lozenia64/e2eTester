"""RunEventCodec payload 키 집합 불변 테스트 — 17개 Run 이벤트 전부."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contexts.run.contracts.records import RunModuleRecord
from app.contexts.run.domain.events import (
    ModuleFailureAnalysisAttached,
    ModuleFinished,
    ModuleQueued,
    ModuleStarted,
    RunComparisonAttached,
    RunCreated,
    RunDeleted,
    RunEventRecord,
    RunFinished,
    RunImported,
    RunModuleBlocked,
    RunModuleRetried,
    RunModulesCancelled,
    RunPartialRerunStarted,
    RunResumed,
    RunSealedInterrupted,
    RunStarted,
    RunWaitingInput,
)
from app.contexts.run.infrastructure.codec import RunEventCodec
from app.core.enums import ModuleStatus, RunStatus

_CODEC = RunEventCodec()
_RUN_ID = "run_codec"
_NOW = datetime(2026, 7, 12, 3, 0, tzinfo=UTC)
_MODULE = RunModuleRecord(
    module_id="hom.login",
    name="로그인",
    group="auth",
    order=0,
    status=ModuleStatus.PASSED,
)
_SUMMARY = {
    "system_code": "hom",
    "system_name": "HOM",
    "status": RunStatus.RUNNING.value,
    "requested_at": _NOW.isoformat(),
    "started_at": _NOW.isoformat(),
    "ended_at": None,
    "awaiting_input_module_id": None,
    "awaiting_input_prompt": None,
    "module_total": 1,
    "module_defined_total": 1,
    "module_skipped": 0,
    "module_passed": 0,
    "module_anomaly": 0,
    "module_error": 0,
    "module_blocked": 0,
    "module_cancelled": 0,
    "current_module_id": None,
    "current_module_name": None,
    "failed_module_id": None,
    "failed_module_name": None,
    "triggered_by": "manual",
    "schedule_id": None,
    "suite_id": None,
    "selected_module_ids": ["hom.login"],
    "created_by_user_id": None,
    "created_by_user_name": None,
    "comparison": None,
}


def _record(event) -> RunEventRecord:
    return RunEventRecord(
        event=event,
        run_summary=_SUMMARY,
        event_id="evt_codec",
        occurred_at=_NOW,
    )


def _payload_keys(event) -> frozenset[str]:
    envelope = _CODEC.encode(_RUN_ID, _record(event))
    return frozenset(envelope.payload.keys()) - {"run_summary"}


def _expects_run_status(event) -> bool:
    body = _CODEC.encode(_RUN_ID, _record(event)).payload
    return "module" in body or "modules" in body


@pytest.mark.parametrize(
    ("event", "expected_keys"),
    [
        (
            RunCreated(system_code="hom", triggered_by="manual", all_modules=[_MODULE]),
            {"system_code", "triggered_by", "all_modules"},
        ),
        (RunStarted(), set()),
        (ModuleQueued(module_id="hom.login", module=_MODULE), {"module_id", "module"}),
        (ModuleStarted(module_id="hom.login", module=_MODULE), {"module_id", "module"}),
        (
            ModuleFinished(
                module_id="hom.login",
                status=ModuleStatus.PASSED,
                system_code="hom",
                schedule_id=None,
                suite_id=None,
                module_name="로그인",
                message="ok",
                started_at=_NOW,
                ended_at=_NOW,
                duration_ms=100,
                created_by_user_id="u1",
                current_url="https://example.com",
                artifacts=["a.png"],
                module=_MODULE,
            ),
            {
                "module_id",
                "status",
                "system_code",
                "schedule_id",
                "suite_id",
                "module_name",
                "message",
                "started_at",
                "ended_at",
                "duration_ms",
                "created_by_user_id",
                "current_url",
                "artifacts",
                "module",
            },
        ),
        (RunWaitingInput(module_id="hom.login", module=_MODULE), {"module_id", "module"}),
        (RunResumed(module_id="hom.login", module=_MODULE), {"module_id", "module"}),
        (
            RunFinished(
                status=RunStatus.PASSED,
                system_code="hom",
                schedule_id=None,
                suite_id=None,
                requested_at=_NOW,
                ended_at=_NOW,
                created_by_user_id="u1",
            ),
            {
                "status",
                "system_code",
                "schedule_id",
                "suite_id",
                "requested_at",
                "ended_at",
                "created_by_user_id",
            },
        ),
        (RunModuleBlocked(module_id="hom.login", module=_MODULE), {"module_id", "module"}),
        (
            RunModulesCancelled(module_ids=["hom.login"], modules=[_MODULE]),
            {"module_ids", "modules"},
        ),
        (
            RunComparisonAttached(
                baseline_run_id="run_prev",
                newly_failed=["로그인"],
                recovered=[],
                still_failing=[],
            ),
            {"baseline_run_id", "newly_failed", "recovered", "still_failing"},
        ),
        (RunSealedInterrupted(all_modules=[_MODULE]), {"all_modules"}),
        (
            RunModuleRetried(module_id="hom.login", attempt=2, module=_MODULE),
            {"module_id", "attempt", "module"},
        ),
        (
            RunPartialRerunStarted(from_module_id="hom.login", all_modules=[_MODULE]),
            {"from_module_id", "all_modules"},
        ),
        (
            ModuleFailureAnalysisAttached(
                module_id="hom.login",
                category="selector_broken",
                user_summary="요약",
                recommended_action="조치",
                module=_MODULE,
            ),
            {"module_id", "category", "user_summary", "recommended_action", "module"},
        ),
        (RunImported(run_summary=_SUMMARY, all_modules=[_MODULE]), {"all_modules"}),
        (RunDeleted(), set()),
    ],
)
def test_run_event_payload_key_invariant(event, expected_keys):
    keys = _payload_keys(event)
    assert keys - {"run_status"} == expected_keys
    assert ("run_status" in keys) is _expects_run_status(event)


def test_module_queued_none_still_carries_run_status():
    event = ModuleQueued(module_id="hom.login", module=None)
    payload = _CODEC.encode(_RUN_ID, _record(event)).payload
    assert "module" in payload
    assert payload["module"] is None
    assert "run_status" in payload


def test_modules_cancelled_empty_still_carries_run_status():
    event = RunModulesCancelled(module_ids=[], modules=[])
    payload = _CODEC.encode(_RUN_ID, _record(event)).payload
    assert "modules" in payload
    assert payload["modules"] == []
    assert "run_status" in payload


def test_run_created_does_not_carry_run_status():
    event = RunCreated(system_code="hom", triggered_by="manual", all_modules=[_MODULE])
    payload = _CODEC.encode(_RUN_ID, _record(event)).payload
    assert "run_status" not in payload
    assert "all_modules" in payload


@pytest.mark.parametrize(
    "event",
    [
        RunCreated(system_code="hom", triggered_by="manual", all_modules=[_MODULE]),
        RunStarted(),
        ModuleQueued(module_id="hom.login", module=_MODULE),
        ModuleStarted(module_id="hom.login", module=_MODULE),
        ModuleFinished(
            module_id="hom.login",
            status=ModuleStatus.PASSED,
            system_code="hom",
            schedule_id=None,
            suite_id=None,
            module=_MODULE,
        ),
        RunWaitingInput(module_id="hom.login", module=_MODULE),
        RunResumed(module_id="hom.login", module=_MODULE),
        RunFinished(
            status=RunStatus.PASSED,
            system_code="hom",
            schedule_id=None,
            suite_id=None,
            requested_at=_NOW,
            ended_at=_NOW,
            created_by_user_id=None,
        ),
        RunModuleBlocked(module_id="hom.login", module=_MODULE),
        RunModulesCancelled(module_ids=["hom.login"], modules=[_MODULE]),
        RunComparisonAttached(baseline_run_id=None),
        RunSealedInterrupted(all_modules=[_MODULE]),
        RunModuleRetried(module_id="hom.login", attempt=2, module=_MODULE),
        RunPartialRerunStarted(from_module_id="hom.login", all_modules=[_MODULE]),
        ModuleFailureAnalysisAttached(module_id="hom.login", module=_MODULE),
        RunImported(run_summary=_SUMMARY, all_modules=[_MODULE]),
        RunDeleted(),
    ],
)
def test_run_event_codec_roundtrip(event):
    record = _record(event)
    envelope = _CODEC.encode(_RUN_ID, record)
    decoded = _CODEC.decode(envelope)
    assert type(decoded.event) is type(event)
    assert decoded.run_summary == record.run_summary
    assert decoded.event_id == record.event_id
    assert decoded.version == record.version


def test_decode_legacy_thin_event_without_run_summary():
    from app.platform.eventing.envelope import EventEnvelope

    envelope = EventEnvelope(
        event_id="evt_thin_created",
        aggregate_type="Run",
        aggregate_id=_RUN_ID,
        event_type="RunCreated",
        payload={
            "system_code": "hom",
            "triggered_by": "manual",
            "all_modules": [],
        },
        occurred_at=_NOW,
    )

    decoded = _CODEC.decode(envelope)

    assert decoded.run_summary is None
    assert isinstance(decoded.event, RunCreated)


def test_encode_omits_run_summary_when_none():
    record = RunEventRecord(
        event=RunStarted(),
        run_summary=None,
        event_id="evt_thin",
        occurred_at=_NOW,
    )

    envelope = _CODEC.encode(_RUN_ID, record)

    assert "run_summary" not in envelope.payload
