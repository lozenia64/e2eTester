"""상황판 지배 요소 판정.

상황판의 직분은 "지금 정상인가" 하나다. 이상이 있으면 몰라보기가 불가능해야 한다.
OTP 대기는 실패보다 우선한다 — 이미 끝난 실패보다 지금 막혀서 사람을 기다리는
Run 이 급하기 때문이다(설계 §3.3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.contexts.insights.application.wall_view import build_wall_view
from app.core.enums import ModuleStatus
from app.core.status_labels import STATUS_TONES, module_status_label

CARDS = [
    {
        "key": "pass_rate",
        "label": "통과율",
        "value": 94,
        "unit": "%",
        "period": "오늘",
        "note": "34/36 모듈 정상",
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
        "note": "이번 달 누적 21건",
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

SYSTEMS = [
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
]


def _summary(
    *,
    error: int = 0,
    anomaly: int = 0,
    running: int = 0,
    attention: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "cards": CARDS,
        "systems": SYSTEMS,
        "totals": {
            "modules": 36,
            "passed": 34,
            "pass_rate": 94,
            "error": error,
            "anomaly": anomaly,
            "running": running,
            "not_inspected": 0,
        },
        "attention": attention or [],
        "date_label": "2026-08-20",
        "generated_at": "2026-08-20T09:14:00+00:00",
    }


def _attention(tone: str, *, system_name: str = "HOM", module_name: str = "로그인") -> dict:
    return {
        "kind": "module",
        "system_code": "HOM",
        "system_name": system_name,
        "module_id": "m1",
        "module_name": module_name,
        "status_label": "입력 대기" if tone == "waiting_input" else "점검실패",
        "tone": tone,
        "run_id": "run1",
        "rank": 30,
    }


def test_all_clear_shows_passed_as_dominant():
    view = build_wall_view(_summary())
    assert view["dominant"]["kind"] == "passed"
    assert view["dominant"]["tone"] == "passed"
    assert "정상" in view["dominant"]["headline"]


def test_error_dominates_over_clear():
    view = build_wall_view(_summary(error=2, attention=[_attention("error")]))
    assert view["dominant"]["kind"] == "error"
    assert view["dominant"]["tone"] == "error"


def test_anomaly_dominates_when_no_error():
    view = build_wall_view(_summary(anomaly=2, attention=[_attention("anomaly")]))
    assert view["dominant"]["kind"] == "anomaly"


def test_error_beats_anomaly():
    view = build_wall_view(_summary(error=1, anomaly=3, attention=[_attention("error")]))
    assert view["dominant"]["kind"] == "error"


def test_running_dominates_when_nothing_wrong():
    view = build_wall_view(_summary(running=3))
    assert view["dominant"]["kind"] == "running"


def test_waiting_input_beats_error():
    """핵심 규칙 — 이미 끝난 실패보다 사람을 기다리는 Run 이 급하다."""
    view = build_wall_view(
        _summary(error=2, attention=[_attention("error"), _attention("waiting_input")])
    )
    assert view["dominant"]["kind"] == "waiting_input"
    assert view["dominant"]["tone"] == "waiting_input"
    assert view["dominant"]["headline"] == "입력 대기"


def test_waiting_input_found_anywhere_in_attention():
    """attention 은 rank 순 정렬이라 waiting_input 이 첫 항목이 아닐 수 있다."""
    attention = [_attention("error"), _attention("anomaly"), _attention("waiting_input")]
    view = build_wall_view(_summary(error=1, anomaly=1, attention=attention))
    assert view["dominant"]["kind"] == "waiting_input"


def test_dominant_detail_names_the_system_and_module():
    view = build_wall_view(
        _summary(error=1, attention=[_attention("error", system_name="FP", module_name="첨부")])
    )
    assert "FP" in view["dominant"]["detail"]
    assert "첨부" in view["dominant"]["detail"]


def test_strip_excludes_pass_rate_card():
    """통과율은 히어로가 흡수하므로 스트립에 두지 않는다(설계 §3.5)."""
    view = build_wall_view(_summary())
    assert [c["key"] for c in view["strip"]] == [
        "self_healed",
        "pending_patches",
        "savings",
    ]


def test_systems_are_reduced_to_wall_shape():
    view = build_wall_view(_summary())
    assert view["systems"] == [
        {"code": "HOM", "name": "대표홈", "tone": "passed", "passed": 6, "total": 6},
        {"code": "FP", "name": "위촉서류", "tone": "anomaly", "passed": 4, "total": 6},
    ]


def test_system_tone_takes_the_worst_bucket():
    systems = [
        {
            "system_code": "X",
            "system_name": "X",
            "module_total": 4,
            "pass_rate": 25,
            "counts": {
                "passed": 1,
                "anomaly": 1,
                "error": 1,
                "running": 1,
                "other": 0,
                "not_inspected": 0,
            },
            "modules": [],
        }
    ]
    summary = _summary()
    summary["systems"] = systems
    view = build_wall_view(summary)
    assert view["systems"][0]["tone"] == "error"


def test_not_inspected_system_is_pending():
    systems = [
        {
            "system_code": "Y",
            "system_name": "Y",
            "module_total": 3,
            "pass_rate": 0,
            "counts": {
                "passed": 0,
                "anomaly": 0,
                "error": 0,
                "running": 0,
                "other": 0,
                "not_inspected": 3,
            },
            "modules": [],
        }
    ]
    summary = _summary()
    summary["systems"] = systems
    view = build_wall_view(summary)
    assert view["systems"][0]["tone"] == "pending"


def test_view_never_carries_my_seconds():
    """프라이버시 계약 — 상황판은 개인 기여분을 쓰지 않는다."""
    view = build_wall_view(_summary())
    assert "my_seconds" not in str(view)


def test_system_tones_stay_inside_status_tone_axis():
    view = build_wall_view(_summary())
    assert {system["tone"] for system in view["systems"]}.issubset(set(STATUS_TONES))


def test_dominant_headline_matches_status_ssot():
    cases = {
        "waiting_input": (
            ModuleStatus.WAITING_INPUT,
            _summary(attention=[_attention("waiting_input")]),
        ),
        "error": (ModuleStatus.ERROR, _summary(error=1, attention=[_attention("error")])),
        "anomaly": (ModuleStatus.ANOMALY, _summary(anomaly=1, attention=[_attention("anomaly")])),
        "running": (ModuleStatus.RUNNING, _summary(running=2)),
        "passed": (ModuleStatus.PASSED, _summary()),
    }
    for kind, (status, summary) in cases.items():
        view = build_wall_view(summary)
        assert view["dominant"]["kind"] == kind
        assert view["dominant"]["headline"] == module_status_label(status)


def test_wall_view_source_has_no_status_label_literals():
    source = Path("app/contexts/insights/application/wall_view.py").read_text(encoding="utf-8")
    for forbidden in ("정상", "이상징후", "점검실패", "입력 대기", "실행 중"):
        assert forbidden not in source, forbidden
