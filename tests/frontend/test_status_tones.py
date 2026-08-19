"""톤 축(STATUS_TONES)이 실제 badge_tone 함수의 출력 전체를 덮는지 검증."""

from app.core.enums import ModuleStatus, RunStatus
from app.core.status_labels import (
    STATUS_TONES,
    module_status_badge_tone,
    run_status_badge_tone,
)


def test_status_tones_has_exactly_nine_tones():
    assert STATUS_TONES == (
        "passed",
        "anomaly",
        "error",
        "running",
        "waiting_input",
        "blocked",
        "skipped",
        "cancelled",
        "pending",
    )


def test_every_run_status_maps_into_status_tones():
    for status in RunStatus:
        assert run_status_badge_tone(status) in STATUS_TONES, status


def test_every_module_status_maps_into_status_tones():
    for status in ModuleStatus:
        assert module_status_badge_tone(status) in STATUS_TONES, status


def test_no_unused_tone():
    """선언만 되고 아무 상태도 매핑되지 않는 톤이 없어야 한다(죽은 토큰 차단)."""
    produced = {run_status_badge_tone(s) for s in RunStatus}
    produced |= {module_status_badge_tone(s) for s in ModuleStatus}
    assert produced == set(STATUS_TONES)
