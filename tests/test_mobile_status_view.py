"""모바일 즉시 점검 화면의 상태 맵 — 드리프트가 실제로 일어났던 자리.

이 템플릿의 인라인 STATUS_VIEW 는 8개 항목 중 4개가 SSOT 와 어긋나 있었고
(대기→"진행 중", 실행 중→"진행 중", 입력 대기→"인증번호 대기", 취소→"취소됨")
FG-006 은 하나도 잡지 못했다. 서버가 SSOT 에서 만들어 내려보낸다.
"""

from __future__ import annotations

from app.core.enums import RunStatus
from app.core.status_labels import run_status_label
from app.core.status_view import mobile_status_view_map

# 이 화면에만 있는 레거시 배지 클래스. P4 가 화면을 이관하면 사라진다.
_LEGACY_CLASSES = {
    "badge-running",
    "badge-waiting",
    "badge-passed",
    "badge-anomaly",
    "badge-error",
    "badge-cancelled",
}


def test_map_covers_every_run_status() -> None:
    view = mobile_status_view_map()
    for status in RunStatus:
        assert status.value in view, status


def test_labels_come_from_the_ssot() -> None:
    view = mobile_status_view_map()
    for status in RunStatus:
        assert view[status.value]["label"] == run_status_label(status), status


def test_classes_are_all_defined_in_the_template() -> None:
    """없는 클래스를 주면 배지가 무스타일로 나간다 — 템플릿 CSS 와 맞춘다."""
    view = mobile_status_view_map()
    for status in RunStatus:
        assert view[status.value]["cls"] in _LEGACY_CLASSES, status


def test_only_in_progress_states_spin() -> None:
    """spin 은 SSOT 축이 아니라 뷰 규칙이다 — 진행을 나타내는 상태만 돈다."""
    view = mobile_status_view_map()
    spinning = {value for value, item in view.items() if item["spin"]}
    assert spinning == {RunStatus.PENDING.value, RunStatus.RUNNING.value}
