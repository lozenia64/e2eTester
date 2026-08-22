"""일간 리포트 메일 HTML.

기존 Run 완료 메일과 같은 셸·헬퍼를 쓴다. 링크는 넣지 않는다 — 기존 메일에도 링크가
없고 공개 URL env 자체가 없다(설계 D6).
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from app.core.enums import ModuleStatus
from app.notifications.daily_report import build_daily_report
from app.notifications.report_renderer import render_daily_report_html

CARDS = [
    {
        "key": "pass_rate",
        "label": "통과율",
        "value": 94,
        "unit": "%",
        "period": "오늘",
        "note": "34/36",
        "tone": "passed",
        "href": "",
        "estimated": False,
    },
    {
        "key": "self_healed",
        "label": "스스로 복구",
        "value": 7,
        "unit": "건",
        "period": "오늘",
        "note": "누적 21건",
        "tone": "running",
        "href": "",
        "estimated": False,
    },
    {
        "key": "pending_patches",
        "label": "내 승인 대기",
        "value": 2,
        "unit": "건",
        "period": "패치",
        "note": "검토",
        "tone": "anomaly",
        "href": "",
        "estimated": False,
    },
    {
        "key": "savings",
        "label": "이번 달 절감",
        "value": 310,
        "unit": "h",
        "period": "이번 달",
        "note": "1,240회",
        "tone": "passed",
        "href": "",
        "estimated": True,
    },
]


def _summary(*, error: int = 0, anomaly: int = 0) -> dict[str, Any]:
    return {
        "cards": CARDS,
        "systems": [
            {
                "system_code": "HOM",
                "system_name": "대표홈",
                "module_total": 6,
                "pass_rate": 100,
                "counts": {
                    "passed": 6,
                    "anomaly": 0,
                    "error": 0,
                    "running": 0,
                    "other": 0,
                    "not_inspected": 0,
                },
                "modules": [],
            },
            {
                "system_code": "FP",
                "system_name": "위촉서류",
                "module_total": 6,
                "pass_rate": 67,
                "counts": {
                    "passed": 4,
                    "anomaly": 2,
                    "error": 0,
                    "running": 0,
                    "other": 0,
                    "not_inspected": 0,
                },
                "modules": [],
            },
        ],
        "totals": {
            "modules": 36,
            "passed": 34,
            "pass_rate": 94,
            "error": error,
            "anomaly": anomaly,
            "running": 0,
            "not_inspected": 0,
        },
        "attention": [
            {
                "kind": "module",
                "system_code": "FP",
                "system_name": "위촉서류",
                "module_id": "m",
                "module_name": "첨부",
                "status_label": "이상징후",
                "tone": "anomaly",
                "run_id": "r",
                "rank": 40,
            }
        ],
        "date_label": "2026-08-20",
        "generated_at": "2026-08-21T08:00:00+00:00",
    }


def _html(**kwargs) -> str:
    context = build_daily_report(_summary(**kwargs), date_label="2026-08-20")
    return render_daily_report_html(context)


@pytest.mark.parametrize(
    "kwargs", [{}, {"error": 2}, {"anomaly": 3}], ids=["clear", "error", "anomaly"]
)
def test_renders_without_error(kwargs) -> None:
    assert _html(**kwargs).strip()


def test_headline_is_in_the_html() -> None:
    assert "점검실패 2건" in _html(error=2)


def test_systems_table_lists_every_system() -> None:
    html = _html()
    assert "HOM" in html
    assert "대표홈" in html
    assert "위촉서류" in html


def test_system_row_shows_passed_over_total() -> None:
    assert "4/6" in _html()


def test_kpi_labels_are_rendered() -> None:
    html = _html()
    for label in ("통과율", "스스로 복구", "내 승인 대기", "이번 달 절감"):
        assert label in html


def test_issue_list_names_system_and_module() -> None:
    html = _html(anomaly=2)
    assert "위촉서류" in html
    assert "첨부" in html


def test_no_external_links() -> None:
    """설계 D6 — 자족적 메일. cid: 인라인 이미지는 이 리포트에 없다."""
    html = _html(error=1)
    assert not re.search(r"https?://", html)
    assert "<a " not in html


def test_date_is_in_the_html() -> None:
    assert "2026-08-20" in _html()


def test_running_status_is_not_neutral_gray() -> None:
    """Task 3 의 커버리지 수정이 렌더까지 이어지는지."""
    from app.notifications.report_renderer import INFO_COLOR, _status_color

    assert _status_color(ModuleStatus.RUNNING.value) == INFO_COLOR
