from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import RunStatus
from app.core.models import Run, RunComparison, RunModule
from app.core.status_labels import run_status_label


class RunView(BaseModel):
    """Run 의 **읽기 모델(프레젠테이션 프로젝션)**.

    Run 애그리거트(쓰기 모델)를 외부(REST 응답·WebSocket payload)로 내보낼 때, 엔티티를
    그대로 ``model_dump`` 하지 않고 이 프로젝션을 거친다. 와이어로 나가는 필드를 여기서
    *명시적으로* 선언하므로, 도메인 엔티티에 내부 전용 필드가 생겨도 자동으로 새지 않는다
    (과거에 PII·제어 상태를 엔티티에서 계속 도려내야 했던 문제를, "엔티티에서 빼는 규율"이
    아니라 "프로젝션으로 투영"하는 구조로 대체한다). 현재 노출 형태는 기존 ``run.model_dump``
    와 1:1 동일해 프론트엔드 계약을 유지한다.

    모듈 항목은 이미 공개에 안전한 ``RunModule`` 형태를 그대로 재사용한다(필드 드리프트 방지).
    """

    run_id: str
    system_code: str
    system_name: str
    status: RunStatus
    status_label: str
    requested_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    modules: list[RunModule]
    selected_module_ids: list[str] = Field(default_factory=list)
    awaiting_input_module_id: str | None = None
    awaiting_input_prompt: str | None = None
    triggered_by: str = "manual"
    schedule_id: str | None = None
    suite_id: str | None = None
    comparison: RunComparison | None = None
    created_by_user_id: str | None = None
    created_by_user_name: str | None = None

    @classmethod
    def from_run(cls, run: Run) -> RunView:
        return cls(
            run_id=run.run_id,
            system_code=run.system_code,
            system_name=run.system_name,
            status=run.status,
            status_label=run_status_label(run.status),
            requested_at=run.requested_at,
            started_at=run.started_at,
            ended_at=run.ended_at,
            modules=run.modules,
            selected_module_ids=run.selected_module_ids,
            awaiting_input_module_id=run.awaiting_input_module_id,
            awaiting_input_prompt=run.awaiting_input_prompt,
            triggered_by=run.triggered_by,
            schedule_id=run.schedule_id,
            suite_id=run.suite_id,
            comparison=run.comparison,
            created_by_user_id=run.created_by_user_id,
            created_by_user_name=run.created_by_user_name,
        )

    @classmethod
    def dump(cls, run: Run) -> dict:
        """Run → 와이어 JSON(dict). 엔티티를 직접 ``model_dump`` 하지 않는 단일 경로."""
        return cls.from_run(run).model_dump(mode="json")
