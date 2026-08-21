"""메일 상태 색의 전수 커버리지.

_STATUS_COLORS 는 손으로 유지하는 매핑인데 전수 검사가 없어 RUNNING·PENDING·QUEUED 가
빠져 중립 회색으로 떨어지고 있었다. run.html:6 의 status_pill 이 anomaly·error 키를
빠뜨렸던 것과 같은 병이다.

맵은 enum 이 아니라 **문자열 값**으로 키가 잡히므로 값 하나가 세 enum 을 모두 덮는다.
"""

import pytest

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.notifications.report_renderer import (
    _STATUS_COLORS,
    INFO_COLOR,
    NEUTRAL_COLOR,
    _status_color,
)

ALL_STATUS_VALUES = sorted(
    {s.value for s in ModuleStatus} | {s.value for s in RunStatus} | {s.value for s in SuiteStatus}
)


@pytest.mark.parametrize("value", ALL_STATUS_VALUES)
def test_every_status_value_is_explicitly_mapped(value: str) -> None:
    """기본값으로 흘러내리는 상태가 없어야 한다.

    PENDING 처럼 중립색이 맞는 상태도 '명시'를 요구한다 — 기본값으로 우연히 맞는 것과
    의도적으로 중립인 것을 구분하기 위해서다.
    """
    assert value in _STATUS_COLORS, f"{value} 가 _STATUS_COLORS 에 없습니다."


def test_running_is_not_neutral() -> None:
    """진행 중은 중립이 아니다 — 웹 토큰도 파랑(--st-running-text)이다."""
    assert _status_color(ModuleStatus.RUNNING.value) == INFO_COLOR
    assert _status_color(RunStatus.RUNNING.value) == INFO_COLOR
    assert _status_color(SuiteStatus.RUNNING.value) == INFO_COLOR


def test_pending_and_queued_are_deliberately_neutral() -> None:
    assert _status_color(ModuleStatus.PENDING.value) == NEUTRAL_COLOR
    assert _status_color(ModuleStatus.QUEUED.value) == NEUTRAL_COLOR


def test_existing_values_are_unchanged() -> None:
    """설계 D5 — 커버리지만 메우고 값은 바꾸지 않는다."""
    assert _status_color(ModuleStatus.PASSED.value) == "#2f8f4e"
    assert _status_color(ModuleStatus.ERROR.value) == "#c0392b"
    assert _status_color(ModuleStatus.ANOMALY.value) == "#b7791f"
    assert _status_color(ModuleStatus.WAITING_INPUT.value) == "#b7791f"
