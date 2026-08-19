"""KPI 카드 조립 — 일간·치유·사용량 세 컨텍스트의 읽기 결과를 카드 4장으로 만든다.

I/O 없음. ``DailySummaryQueries`` 가 스토어에서 읽은 것을 넘겨 호출한다
(``build_healing_metrics`` 와 같은 순수 빌더 패턴).

정직성 규율(설계 §3.8): 추정 지표는 근거(note)를 반드시 동반한다. 실측(통과율·복구
건수·승인 대기)과 추정(절감 시간)을 estimated 플래그로 구분한다.
"""

from __future__ import annotations

from typing import Any

from app.core.stats_models import SavingsSummary

# 추정치가 설정되지 않았을 때 0h 를 성과처럼 표시하지 않기 위한 안내 문구.
SAVINGS_UNSET_LABEL = "추정치 미설정"
MODULE_SETTINGS_URL = "/admin/modules"
PATCH_LIST_URL = "/self-healing#patches"


def _today_auto_healed(healing_metrics: dict[str, Any], today_label: str) -> int:
    for row in healing_metrics.get("trend", []):
        if row.get("date") == today_label:
            return int(row.get("auto", 0))
    return 0


def _savings_card(savings: SavingsSummary) -> dict[str, Any]:
    if not savings.estimated or savings.total_seconds <= 0:
        return {
            "key": "savings",
            "label": "이번 달 절감",
            "value": SAVINGS_UNSET_LABEL,
            "unit": "",
            "period": "이번 달",
            "note": "모듈별 수동 소요 추정치를 설정하면 집계됩니다",
            "tone": "pending",
            "href": MODULE_SETTINGS_URL,
            "estimated": False,
        }
    return {
        "key": "savings",
        "label": "이번 달 절감",
        "value": round(savings.total_seconds / 3600),
        "unit": "h",
        "period": "이번 달",
        "note": savings.note,
        "tone": "passed",
        "href": MODULE_SETTINGS_URL,
        "estimated": True,
    }


def build_daily_summary(
    totals: dict[str, Any],
    healing_metrics: dict[str, Any],
    savings: SavingsSummary,
    *,
    today_label: str,
) -> dict[str, Any]:
    """KPI 카드 4장(순서 고정: 통과율 · 스스로 복구 · 승인 대기 · 절감)."""
    kpi = healing_metrics.get("kpi", {})
    today_healed = _today_auto_healed(healing_metrics, today_label)
    month_healed = int(kpi.get("month_auto_recovered", 0) or 0)
    pending = int(kpi.get("pending_patches", 0) or 0)

    cards: list[dict[str, Any]] = [
        {
            "key": "pass_rate",
            "label": "통과율",
            "value": totals.get("pass_rate", 0),
            "unit": "%",
            "period": "오늘",
            "note": f"{totals.get('passed', 0)}/{totals.get('modules', 0)} 모듈 정상",
            "tone": "passed",
            "href": "",
            "estimated": False,
        },
        {
            "key": "self_healed",
            "label": "스스로 복구",
            "value": today_healed,
            "unit": "건",
            "period": "오늘",
            "note": f"이번 달 누적 {month_healed}건",
            "tone": "running",
            "href": "/self-healing",
            "estimated": False,
        },
        {
            # 유일하게 '행동을 요구하는' 숫자 — 톤을 분리한다(설계 §3.7).
            "key": "pending_patches",
            "label": "내 승인 대기",
            "value": pending,
            "unit": "건",
            "period": "패치",
            "note": "자동 생성된 수정 diff 검토",
            "tone": "anomaly",
            "href": PATCH_LIST_URL,
            "estimated": False,
        },
        _savings_card(savings),
    ]
    return {"cards": cards}
