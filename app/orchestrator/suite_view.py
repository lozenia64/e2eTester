from __future__ import annotations

from app.auth.models import User
from app.core.models import StartSuiteRequest, SuiteEvent, SuiteRun


def resolve_suite_request_for_user(
    payload: StartSuiteRequest,
    *,
    all_system_codes: list[str],
    allowed_system_codes: list[str],
) -> StartSuiteRequest:
    """비관리자 Suite 요청을 허용 시스템 범위로 제한한다."""
    allowed = set(allowed_system_codes)
    scope_codes = [code for code in all_system_codes if code in allowed]
    requested = payload.selected_system_codes or scope_codes
    blocked = [code for code in requested if code not in allowed]
    if blocked:
        joined = ", ".join(blocked)
        raise ValueError(f"접근 권한이 없는 시스템: {joined}")

    client_scope = payload.scope_system_codes or scope_codes
    resolved_scope = [code for code in client_scope if code in allowed]
    return payload.model_copy(
        update={
            "selected_system_codes": [code for code in requested if code in allowed],
            "scope_system_codes": resolved_scope,
        }
    )


def filter_suite_for_user(suite: SuiteRun, user: User | None) -> SuiteRun:
    """비관리자에게는 허용된 시스템 단계만 노출한다."""
    if user is None or user.role == "admin":
        return suite
    allowed = set(user.allowed_system_codes)
    filtered_steps = [step for step in suite.steps if step.system_code in allowed]
    if len(filtered_steps) == len(suite.steps):
        return suite
    return suite.model_copy(update={"steps": filtered_steps})


def filter_suite_event_for_user(event: SuiteEvent, user: User | None) -> SuiteEvent:
    payload = event.payload
    if not isinstance(payload, dict) or "steps" not in payload:
        return event
    suite = SuiteRun.model_validate(payload)
    filtered = filter_suite_for_user(suite, user)
    if filtered is suite:
        return event
    updated_payload = dict(payload)
    updated_payload["steps"] = [step.model_dump(mode="json") for step in filtered.steps]
    return event.model_copy(update={"payload": updated_payload})
