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
    FAIL_COLOR,
    INFO_COLOR,
    NEUTRAL_COLOR,
    PASS_COLOR,
    WARN_COLOR,
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
    assert _status_color(ModuleStatus.PASSED.value) == PASS_COLOR
    assert _status_color(ModuleStatus.ERROR.value) == FAIL_COLOR
    assert _status_color(ModuleStatus.ANOMALY.value) == WARN_COLOR
    assert _status_color(ModuleStatus.WAITING_INPUT.value) == WARN_COLOR


def test_mail_status_colors_are_derived_from_the_shared_palette() -> None:
    """화면과 메일이 같은 상태를 다른 색으로 말하지 않는다(P3-4 §3.2).

    메일의 (글자색, 옅은 배경) 쌍은 웹 팔레트의 (text, surface) 축에 대응한다.
    """
    from app.core.status_colors import PALETTE
    from app.notifications import report_renderer as renderer

    expected = {
        "PASS": "passed",
        "FAIL": "error",
        "WARN": "anomaly",
        "NEUTRAL": "pending",
        "INFO": "running",
    }
    for prefix, tone in expected.items():
        assert getattr(renderer, f"{prefix}_COLOR") == PALETTE[tone]["text"], prefix
        assert getattr(renderer, f"{prefix}_SOFT_BG") == PALETTE[tone]["surface"], prefix


def test_mail_layout_colors_are_untouched() -> None:
    """레이아웃 색은 상태와 무관하다 — 팔레트 통일이 메일 크롬까지 바꾸면 안 된다."""
    from app.notifications import report_renderer as renderer

    assert renderer.PAGE_BG == "#f4f5f7"
    assert renderer.CARD_BG == "#ffffff"
    assert renderer.INK == "#1f2328"
    assert renderer.MUTED == "#6b7280"
    assert renderer.BORDER == "#e5e7eb"
    assert renderer.SOFT_BG == "#f7f8fa"
    assert renderer.LABEL_BG == "#f4f6f8"
