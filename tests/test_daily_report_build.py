"""일간 리포트 내용 조립.

제목 규칙은 상황판과 다르다 — 발송 시각(다음 날 아침)에는 어제의 OTP 대기가 이미
끝났거나 무의미하므로 하루가 닫힌 뒤의 결론만 담는다(설계 §3.3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.enums import ModuleStatus
from app.core.status_labels import module_status_label
from app.notifications.daily_report import build_daily_report

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


def _system(code: str, name: str, *, passed: int, total: int, **counts: int) -> dict[str, Any]:
    base = {
        "passed": passed,
        "anomaly": 0,
        "error": 0,
        "running": 0,
        "other": 0,
        "not_inspected": 0,
    }
    base.update(counts)
    return {
        "system_code": code,
        "system_name": name,
        "module_total": total,
        "pass_rate": round(passed / total * 100) if total else 0,
        "counts": base,
        "modules": [],
    }


def _summary(
    *,
    error: int = 0,
    anomaly: int = 0,
    not_inspected: int = 0,
    modules: int = 36,
    systems: list[dict] | None = None,
    attention: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "cards": CARDS,
        "systems": systems
        if systems is not None
        else [
            _system("HOM", "대표홈", passed=6, total=6),
            _system("FP", "위촉서류", passed=4, total=6, anomaly=2),
        ],
        "totals": {
            "modules": modules,
            "passed": modules - error - anomaly - not_inspected,
            "pass_rate": 94,
            "error": error,
            "anomaly": anomaly,
            "running": 0,
            "not_inspected": not_inspected,
        },
        "attention": attention or [],
        "date_label": "2026-08-20",
        "generated_at": "2026-08-21T08:00:00+00:00",
    }


def _attention(system: str, module: str, label: str) -> dict[str, Any]:
    return {
        "kind": "module",
        "system_code": system,
        "system_name": system,
        "module_id": "m",
        "module_name": module,
        "status_label": label,
        "tone": "error",
        "run_id": "r",
        "rank": 50,
    }


def test_error_headline_wins():
    report = build_daily_report(_summary(error=2), date_label="2026-08-20")
    assert report["headline"] == f"{module_status_label(ModuleStatus.ERROR)} 2건"
    assert report["status_value"] == ModuleStatus.ERROR.value


def test_anomaly_headline_when_no_error():
    report = build_daily_report(_summary(anomaly=3), date_label="2026-08-20")
    assert report["headline"] == f"{module_status_label(ModuleStatus.ANOMALY)} 3건"
    assert report["status_value"] == ModuleStatus.ANOMALY.value


def test_error_beats_anomaly():
    report = build_daily_report(_summary(error=1, anomaly=5), date_label="2026-08-20")
    assert report["status_value"] == ModuleStatus.ERROR.value


def test_not_inspected_day():
    report = build_daily_report(_summary(not_inspected=36, modules=36), date_label="2026-08-20")
    assert report["headline"] == "점검 미실행"
    assert report["status_value"] == ModuleStatus.PENDING.value


def test_all_clear_headline():
    report = build_daily_report(_summary(), date_label="2026-08-20")
    assert report["headline"] == module_status_label(ModuleStatus.PASSED)
    assert report["status_value"] == ModuleStatus.PASSED.value


def test_kpis_come_from_cards_in_order():
    report = build_daily_report(_summary(), date_label="2026-08-20")
    assert [label for label, _v, _u in report["kpis"]] == [
        "통과율",
        "스스로 복구",
        "내 승인 대기",
        "이번 달 절감",
    ]


def test_systems_carry_worst_status():
    report = build_daily_report(_summary(), date_label="2026-08-20")
    by_code = {s["code"]: s for s in report["systems"]}
    assert by_code["HOM"]["status_value"] == ModuleStatus.PASSED.value
    assert by_code["FP"]["status_value"] == ModuleStatus.ANOMALY.value
    assert by_code["FP"]["passed"] == 4
    assert by_code["FP"]["total"] == 6


def test_system_error_beats_anomaly():
    systems = [_system("X", "X", passed=1, total=4, anomaly=1, error=1)]
    report = build_daily_report(_summary(systems=systems), date_label="2026-08-20")
    assert report["systems"][0]["status_value"] == ModuleStatus.ERROR.value


def test_uninspected_system_is_pending():
    systems = [_system("Y", "Y", passed=0, total=3, not_inspected=3)]
    report = build_daily_report(_summary(systems=systems), date_label="2026-08-20")
    assert report["systems"][0]["status_value"] == ModuleStatus.PENDING.value


def test_issues_come_from_attention():
    attention = [_attention("FP", "첨부", "점검실패"), _attention("HOM", "로그인", "이상징후")]
    report = build_daily_report(_summary(error=1, attention=attention), date_label="2026-08-20")
    assert [(i["system"], i["module"]) for i in report["issues"]] == [
        ("FP", "첨부"),
        ("HOM", "로그인"),
    ]


def test_date_label_is_echoed():
    report = build_daily_report(_summary(), date_label="2026-08-20")
    assert report["date_label"] == "2026-08-20"


def test_source_has_no_hardcoded_status_labels():
    """P3-2 에서 파이썬에 한국어 라벨을 하드코딩했다가 지적받았다. 반복하지 않는다."""
    source = Path("app/notifications/daily_report.py").read_text(encoding="utf-8")
    for label in ("정상", "이상징후", "점검실패", "입력 대기", "실행 중"):
        assert f'"{label}"' not in source, label
