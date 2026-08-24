"""상태 → 배지(톤·라벨) 해석 단일 경로.

템플릿이 자체 색 맵을 들고 있던 것이 P3-1 이 고치는 버그의 근원이다. 이 함수가
유일한 해석 경로이며, status_labels.py 의 SSOT 만 참조한다.
"""

import pytest

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.status_labels import (
    STATUS_TONES,
    module_status_badge_tone,
    module_status_label,
    run_status_badge_tone,
    run_status_label,
    suite_status_badge_tone,
    suite_status_label,
)
from app.core.status_view import StatusBadgeView, status_badge_view


@pytest.mark.parametrize("status", list(ModuleStatus))
def test_module_status_matches_ssot(status: ModuleStatus) -> None:
    view = status_badge_view(status)
    assert view.tone == module_status_badge_tone(status)
    assert view.label == module_status_label(status)


@pytest.mark.parametrize("status", list(RunStatus))
def test_run_status_matches_ssot(status: RunStatus) -> None:
    view = status_badge_view(status)
    assert view.tone == run_status_badge_tone(status)
    assert view.label == run_status_label(status)


@pytest.mark.parametrize("status", list(SuiteStatus))
def test_suite_status_matches_ssot(status: SuiteStatus) -> None:
    view = status_badge_view(status)
    assert view.tone == suite_status_badge_tone(status)
    assert view.label == suite_status_label(status)


@pytest.mark.parametrize("status", list(ModuleStatus))
def test_every_tone_is_in_the_nine_tone_axis(status: ModuleStatus) -> None:
    assert status_badge_view(status).tone in STATUS_TONES


def test_anomaly_and_error_are_not_neutral() -> None:
    """버그 2 회귀 가드 — 이 둘이 pending/회색으로 떨어지면 안 된다."""
    assert status_badge_view(ModuleStatus.ANOMALY).tone == "anomaly"
    assert status_badge_view(ModuleStatus.ERROR).tone == "error"


def test_legacy_failed_is_anomaly_not_error() -> None:
    """버그 3 회귀 가드 — 레거시 FAILED 는 이상징후(amber)다."""
    assert status_badge_view(ModuleStatus.FAILED).tone == "anomaly"
    assert status_badge_view(ModuleStatus.FAILED).label == "이상징후"


def test_labels_are_korean() -> None:
    """버그 1 회귀 가드 — 영문 enum 값이 라벨로 새지 않는다."""
    for status in ModuleStatus:
        label = status_badge_view(status).label
        assert label != status.value
        assert not label.isascii(), (status, label)


def test_unknown_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="지원하지 않는 상태 타입"):
        status_badge_view("PASSED")  # type: ignore[arg-type]


def test_view_is_immutable() -> None:
    view = status_badge_view(ModuleStatus.PASSED)
    assert isinstance(view, StatusBadgeView)
    with pytest.raises(AttributeError):
        view.tone = "error"  # type: ignore[misc]
