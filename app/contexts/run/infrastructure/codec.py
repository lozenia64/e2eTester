"""RunEventRecord ↔ EventEnvelope 인코더(다형성 없음 — Run 컨텍스트 전용)."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from typing import Any

from app.contexts.run.contracts.records import RunModuleRecord
from app.contexts.run.domain.events import (
    ModuleFailureAnalysisAttached,
    ModuleFinished,
    ModuleQueued,
    ModuleStarted,
    RunComparisonAttached,
    RunCreated,
    RunDeleted,
    RunEvent,
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
from app.core.enums import ModuleStatus, RunStatus
from app.platform.eventing.envelope import EventEnvelope


class RunEventCodec:
    """RunEventRecord ↔ EventEnvelope(aggregate_type=\"Run\")."""

    _TYPES: dict[str, type] = {
        "RunCreated": RunCreated,
        "RunStarted": RunStarted,
        "ModuleQueued": ModuleQueued,
        "ModuleStarted": ModuleStarted,
        "ModuleFinished": ModuleFinished,
        "RunWaitingInput": RunWaitingInput,
        "RunResumed": RunResumed,
        "RunFinished": RunFinished,
        "RunModuleBlocked": RunModuleBlocked,
        "RunModulesCancelled": RunModulesCancelled,
        "RunComparisonAttached": RunComparisonAttached,
        "RunSealedInterrupted": RunSealedInterrupted,
        "RunModuleRetried": RunModuleRetried,
        "RunPartialRerunStarted": RunPartialRerunStarted,
        "ModuleFailureAnalysisAttached": ModuleFailureAnalysisAttached,
        "RunImported": RunImported,
        "RunDeleted": RunDeleted,
    }

    def encode(self, run_id: str, record: RunEventRecord) -> EventEnvelope:
        event_type = type(record.event).__name__
        payload = _event_to_payload(record.event)
        if record.run_summary is not None:
            payload["run_summary"] = record.run_summary
        # 구 RunAggregate._emit 과 동치: payload 에 module/modules 키가 있을 때만(값 None/[] 포함).
        if record.run_summary is not None and ("module" in payload or "modules" in payload):
            payload["run_status"] = record.run_summary["status"]
        return EventEnvelope(
            event_id=record.event_id,
            aggregate_type="Run",
            aggregate_id=run_id,
            event_type=event_type,
            payload=payload,
            occurred_at=record.occurred_at,
            version=record.version,
        )

    def decode(self, envelope: EventEnvelope) -> RunEventRecord:
        cls = self._TYPES[envelope.event_type]
        payload = dict(envelope.payload)
        run_summary = payload.pop("run_summary", None)
        payload.pop("run_status", None)
        if cls is RunImported:
            payload["run_summary"] = run_summary
        event = _payload_to_event(cls, payload)
        return RunEventRecord(
            event=event,
            run_summary=run_summary,
            event_id=envelope.event_id,
            occurred_at=envelope.occurred_at,
            version=envelope.version,
        )


def _module_to_wire(module: RunModuleRecord | None) -> dict | None:
    if module is None:
        return None
    return module.model_dump(mode="json")


def _wire_to_module(wire: dict | None) -> RunModuleRecord | None:
    if wire is None:
        return None
    return RunModuleRecord.model_validate(wire)


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _event_to_payload(event: RunEvent) -> dict[str, Any]:
    if isinstance(event, RunStarted | RunDeleted):
        return {}
    if isinstance(event, RunCreated):
        return {
            "system_code": event.system_code,
            "triggered_by": event.triggered_by,
            "all_modules": [_module_to_wire(m) for m in event.all_modules],
        }
    if isinstance(event, RunImported):
        return {
            "run_summary": event.run_summary,
            "all_modules": [_module_to_wire(m) for m in event.all_modules],
        }
    if isinstance(event, RunFinished):
        return {
            "status": event.status.value,
            "system_code": event.system_code,
            "schedule_id": event.schedule_id,
            "suite_id": event.suite_id,
            "requested_at": event.requested_at.isoformat(),
            "ended_at": event.ended_at.isoformat() if event.ended_at else None,
            "created_by_user_id": event.created_by_user_id,
        }
    if isinstance(event, ModuleFinished):
        return {
            "module_id": event.module_id,
            "status": event.status.value,
            "system_code": event.system_code,
            "schedule_id": event.schedule_id,
            "suite_id": event.suite_id,
            "module_name": event.module_name,
            "message": event.message,
            "started_at": event.started_at.isoformat() if event.started_at else None,
            "ended_at": event.ended_at.isoformat() if event.ended_at else None,
            "duration_ms": event.duration_ms,
            "created_by_user_id": event.created_by_user_id,
            "current_url": event.current_url,
            "artifacts": list(event.artifacts),
            "module": _module_to_wire(event.module),
        }
    if isinstance(event, RunModulesCancelled):
        return {
            "module_ids": list(event.module_ids),
            "modules": [_module_to_wire(m) for m in event.modules],
        }
    if isinstance(event, RunComparisonAttached):
        return {
            "baseline_run_id": event.baseline_run_id,
            "newly_failed": list(event.newly_failed),
            "recovered": list(event.recovered),
            "still_failing": list(event.still_failing),
        }
    if isinstance(event, RunSealedInterrupted):
        return {"all_modules": [_module_to_wire(m) for m in event.all_modules]}
    if isinstance(event, RunPartialRerunStarted):
        return {
            "from_module_id": event.from_module_id,
            "all_modules": [_module_to_wire(m) for m in event.all_modules],
        }
    if isinstance(event, RunModuleRetried):
        return {
            "module_id": event.module_id,
            "attempt": event.attempt,
            "module": _module_to_wire(event.module),
        }
    if isinstance(event, ModuleFailureAnalysisAttached):
        return {
            "module_id": event.module_id,
            "category": event.category,
            "user_summary": event.user_summary,
            "recommended_action": event.recommended_action,
            "module": _module_to_wire(event.module),
        }
    if isinstance(
        event, ModuleQueued | ModuleStarted | RunWaitingInput | RunResumed | RunModuleBlocked
    ):
        return {"module_id": event.module_id, "module": _module_to_wire(event.module)}
    raise TypeError(f"unsupported Run event: {type(event).__name__}")


def _payload_to_event(cls: type, payload: dict[str, Any]) -> RunEvent:
    field_names = {f.name for f in fields(cls)}
    kwargs = {k: v for k, v in payload.items() if k in field_names}
    if cls is RunFinished:
        kwargs["status"] = RunStatus(kwargs["status"])
        kwargs["requested_at"] = _parse_dt(kwargs["requested_at"])
        kwargs["ended_at"] = _parse_dt(kwargs.get("ended_at"))
    elif cls is ModuleFinished:
        kwargs["status"] = ModuleStatus(kwargs["status"])
        kwargs["started_at"] = _parse_dt(kwargs.get("started_at"))
        kwargs["ended_at"] = _parse_dt(kwargs.get("ended_at"))
        kwargs["artifacts"] = list(kwargs.get("artifacts") or [])
        kwargs["module"] = _wire_to_module(kwargs.get("module"))
    elif cls in {RunCreated, RunSealedInterrupted, RunPartialRerunStarted}:
        key = "all_modules"
        kwargs[key] = [_wire_to_module(w) for w in kwargs.get(key, [])]  # type: ignore[misc]
    elif cls is RunImported:
        kwargs["all_modules"] = [_wire_to_module(w) for w in kwargs.get("all_modules", [])]
    elif cls is RunModulesCancelled:
        kwargs["modules"] = [_wire_to_module(w) for w in kwargs.get("modules", [])]
    elif cls is RunModuleRetried:
        kwargs["module"] = _wire_to_module(kwargs.get("module"))
    elif cls is ModuleFailureAnalysisAttached:
        kwargs["module"] = _wire_to_module(kwargs.get("module"))
    elif cls in {ModuleQueued, ModuleStarted, RunWaitingInput, RunResumed, RunModuleBlocked}:
        kwargs["module"] = _wire_to_module(kwargs.get("module"))
    elif cls is RunComparisonAttached:
        kwargs["newly_failed"] = list(kwargs.get("newly_failed") or [])
        kwargs["recovered"] = list(kwargs.get("recovered") or [])
        kwargs["still_failing"] = list(kwargs.get("still_failing") or [])
    return cls(**kwargs)  # type: ignore[call-arg]
