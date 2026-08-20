"""상태 → 배지(톤·라벨) 해석 — 템플릿이 쓰는 단일 경로.

템플릿이 자체 색 맵(`status_pill`)을 들고 있던 것이 P3-1 이 고치는 버그의 근원이다.
Jinja 전역으로 등록해 템플릿이 톤을 직접 계산하지 않게 한다
(`app/api/routes_daily.py` 의 `system_summary_badge` 등록과 같은 패턴).

뷰 모델에 필드를 추가하지 않는 이유: `RunView.modules` 는 도메인 `RunModule` 을
의도적으로 그대로 재사용하며(필드 드리프트 방지), 여기에 표현용 필드를 넣으면
그 규율이 깨진다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.status_labels import (
    module_status_badge_tone,
    module_status_label,
    run_status_badge_tone,
    run_status_label,
    suite_status_badge_tone,
    suite_status_label,
)


@dataclass(frozen=True)
class StatusBadgeView:
    """배지 렌더에 필요한 최소 표현. `status-badge` 매크로의 인자와 1:1."""

    tone: str
    label: str


def status_badge_view(status: RunStatus | ModuleStatus | SuiteStatus) -> StatusBadgeView:
    """상태 enum → 톤·라벨. 톤·라벨 규칙은 status_labels.py 가 유일한 출처다.

    문자열을 받지 않는다 — 어느 enum 인지 모르면 톤 규칙을 고를 수 없고,
    조용히 잘못된 톤을 주는 것보다 실패하는 편이 안전하다.
    """
    if isinstance(status, ModuleStatus):
        return StatusBadgeView(module_status_badge_tone(status), module_status_label(status))
    if isinstance(status, RunStatus):
        return StatusBadgeView(run_status_badge_tone(status), run_status_label(status))
    if isinstance(status, SuiteStatus):
        return StatusBadgeView(suite_status_badge_tone(status), suite_status_label(status))
    msg = (
        f"지원하지 않는 상태 타입: {type(status).__name__}. "
        "RunStatus/ModuleStatus/SuiteStatus 중 하나를 넘기세요."
    )
    raise TypeError(msg)
