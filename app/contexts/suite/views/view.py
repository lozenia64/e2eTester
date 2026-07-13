from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.contexts.identity.models import User
from app.core.enums import SuiteStatus
from app.core.requests import StartSuiteRequest
from app.core.status_labels import suite_status_label
from app.core.suite_models import SuiteEvent, SuiteRun, SuiteStep
from app.domain.snapshots import SuiteSnapshot


class SuiteView(BaseModel):
    """Suite 의 **읽기 모델(프레젠테이션 프로젝션)** — ``RunView`` 의 Suite 짝.

    Suite 엔티티(쓰기 모델)를 외부(REST 응답·WebSocket payload·스냅샷)로 내보낼 때, 엔티티를
    그대로 ``model_dump`` 하지 않고 이 프로젝션을 거친다. 와이어로 나가는 필드를 여기서
    *명시적으로* 선언하므로, 엔티티에 내부 전용 필드가 생겨도 자동으로 새지 않는다. 과거
    Suite 직렬화는 REST 4곳·WS 스냅샷·이벤트 발행에서 제각각 ``suite.model_dump`` 를 직접
    호출해, RunView 가 세운 "엔티티를 직접 직렬화하지 않는다"는 규율을 Suite 쪽에서만 깨고
    있었다 — 이 클래스로 그 경로를 단일화한다.

    단계 항목은 이미 공개에 안전한 ``SuiteStep`` 을 그대로 재사용한다(필드 드리프트 방지).
    노출 필드는 기존 ``suite.model_dump`` 와 동일하며, ``RunView`` 와 동일하게 표시용
    ``status_label`` 만 추가로 싣는다.
    """

    suite_id: str
    status: SuiteStatus
    status_label: str
    steps: list[SuiteStep]
    current_step_index: int = 0
    requested_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    active_run_id: str | None = None
    awaiting_input_run_id: str | None = None
    awaiting_input_prompt: str | None = None
    browser_mode: str = "headed"
    selected_system_codes: list[str] = Field(default_factory=list)
    created_by_user_id: str | None = None
    created_by_user_name: str | None = None
    triggered_by: str = "manual"
    schedule_id: str | None = None

    @classmethod
    def from_snapshot(cls, snapshot: SuiteSnapshot) -> SuiteView:
        return cls.from_suite(snapshot.to_suite())

    @classmethod
    def from_suite(cls, suite: SuiteRun) -> SuiteView:
        return cls(
            suite_id=suite.suite_id,
            status=suite.status,
            status_label=suite_status_label(suite.status),
            steps=suite.steps,
            current_step_index=suite.current_step_index,
            requested_at=suite.requested_at,
            started_at=suite.started_at,
            ended_at=suite.ended_at,
            active_run_id=suite.active_run_id,
            awaiting_input_run_id=suite.awaiting_input_run_id,
            awaiting_input_prompt=suite.awaiting_input_prompt,
            browser_mode=suite.browser_mode,
            selected_system_codes=suite.selected_system_codes,
            created_by_user_id=suite.created_by_user_id,
            created_by_user_name=suite.created_by_user_name,
            triggered_by=suite.triggered_by,
            schedule_id=suite.schedule_id,
        )

    @classmethod
    def dump(cls, suite: SuiteRun) -> dict:
        """Suite → 와이어 JSON(dict). 엔티티를 직접 ``model_dump`` 하지 않는 단일 경로."""
        return cls.from_suite(suite).model_dump(mode="json")

    @classmethod
    def dump_from_summary(cls, suite_id: str, summary: dict) -> dict:
        """이벤트에 동봉된 ``suite_summary`` 로 suite_* WS payload 를 만든다(blob 재수화 없음).

        실시간 프로젝터가 Suite 상태 blob 을 읽지 않도록, ``SuiteAggregate`` 가 발행 시점에
        계산한 요약(fat event)으로 ``dump`` 와 동일한 스키마를 재구성한다(스키마 계약의 단일
        출처). ``filter_suite_event_for_user`` 가 payload 를 ``SuiteRun`` 으로 재검증하므로 steps
        는 유효한 ``SuiteStep`` dict 여야 한다(요약이 그 형태를 그대로 싣는다).
        """
        status = SuiteStatus(summary["status"])
        return cls(
            suite_id=suite_id,
            status=status,
            status_label=suite_status_label(status),
            steps=[SuiteStep(**step) for step in summary.get("steps", [])],
            current_step_index=summary.get("current_step_index", 0),
            requested_at=summary["requested_at"],
            started_at=summary.get("started_at"),
            ended_at=summary.get("ended_at"),
            active_run_id=summary.get("active_run_id"),
            awaiting_input_run_id=summary.get("awaiting_input_run_id"),
            awaiting_input_prompt=summary.get("awaiting_input_prompt"),
            browser_mode=summary.get("browser_mode") or "headed",
            selected_system_codes=summary.get("selected_system_codes", []),
            created_by_user_id=summary.get("created_by_user_id"),
            created_by_user_name=summary.get("created_by_user_name"),
            triggered_by=summary.get("triggered_by", "manual"),
            schedule_id=summary.get("schedule_id"),
        ).model_dump(mode="json")


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
