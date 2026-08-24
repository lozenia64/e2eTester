"""Wall view builder.

No I/O. Routes pass in ``DailySummaryQueries.get_daily_summary()`` output and
this module reduces it to the view shape the wall template needs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.core.enums import ModuleStatus
from app.core.status_view import status_badge_view

# System block color priority for wall-only aggregation.
_WORST_BUCKET_ORDER = ("error", "anomaly", "running", "other", "not_inspected")
_BUCKET_TO_TONE = {
    "error": "error",
    "anomaly": "anomaly",
    "running": "running",
    "other": "blocked",
    "not_inspected": "pending",
}

_DOMINANT_STATUS = {
    "waiting_input": ModuleStatus.WAITING_INPUT,
    "error": ModuleStatus.ERROR,
    "anomaly": ModuleStatus.ANOMALY,
    "running": ModuleStatus.RUNNING,
    "passed": ModuleStatus.PASSED,
}

# pass_rate is absorbed by the hero.
_STRIP_EXCLUDED_CARD_KEYS = frozenset({"pass_rate"})


def _badge(kind: str) -> tuple[str, str]:
    view = status_badge_view(_DOMINANT_STATUS[kind])
    return view.tone, view.label


def _find_waiting_input(attention: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((item for item in attention if item.get("tone") == "waiting_input"), None)


def _detail_of(item: dict[str, Any] | None) -> str:
    if item is None:
        return ""
    system = item.get("system_name") or item.get("system_code") or ""
    module = item.get("module_name")
    return f"{system} · {module}" if module else str(system)


def _dominant(totals: dict[str, Any], attention: list[dict[str, Any]]) -> dict[str, Any]:
    waiting = _find_waiting_input(attention)
    if waiting is not None:
        tone, headline = _badge("waiting_input")
        detail = _detail_of(waiting)
        return {
            "kind": "waiting_input",
            "tone": tone,
            "headline": headline,
            "detail": f"OTP · {detail}" if detail else "OTP",
        }

    def _first(tone: str) -> dict[str, Any] | None:
        return next((item for item in attention if item.get("tone") == tone), None)

    if int(totals.get("error", 0) or 0) > 0:
        tone, headline = _badge("error")
        return {
            "kind": "error",
            "tone": tone,
            "headline": headline,
            "detail": _detail_of(_first("error")),
        }
    if int(totals.get("anomaly", 0) or 0) > 0:
        tone, headline = _badge("anomaly")
        return {
            "kind": "anomaly",
            "tone": tone,
            "headline": headline,
            "detail": _detail_of(_first("anomaly")),
        }
    if int(totals.get("running", 0) or 0) > 0:
        running = int(totals["running"])
        tone, headline = _badge("running")
        return {
            "kind": "running",
            "tone": tone,
            "headline": headline,
            "detail": f"{running}개 모듈",
        }
    passed = int(totals.get("passed", 0) or 0)
    modules = int(totals.get("modules", 0) or 0)
    tone, headline = _badge("passed")
    return {
        "kind": "passed",
        "tone": tone,
        "headline": headline,
        "detail": f"{passed}/{modules} 모듈",
    }


def _system_tone(counts: dict[str, Any]) -> str:
    for bucket in _WORST_BUCKET_ORDER:
        if int(counts.get(bucket, 0) or 0) > 0:
            return _BUCKET_TO_TONE[bucket]
    return "passed"


# 점검 창이 짧아도 스팬이 화면을 가득 채우지 않게 하는 하한(설계 §4.3).
_MIN_WINDOW = timedelta(minutes=30)
# 26초 Run 이 사라지지 않게 하는 폭 하한(%). 1920px 에서 약 15px.
_MIN_LANE_WIDTH_PCT = 0.8
_TICK_COUNT = 5


def _pct(part: timedelta, whole: timedelta) -> float:
    if whole.total_seconds() <= 0:
        return 0.0
    return round(part.total_seconds() / whole.total_seconds() * 100, 4)


def build_timeline(systems: list[dict[str, Any]], *, now_iso: str) -> dict[str, Any]:
    """오늘의 점검 창을 x축으로 하는 시스템별 스팬(설계 §4.3).

    축의 범위는 '오늘 첫 점검 → 지금'이다. 24시간 축은 실측상 94% 가 빈 공간이 된다
    (설계 §2). 창이 30분보다 짧으면 30분으로 늘려 잡는다.
    """
    now = datetime.fromisoformat(now_iso)
    spans = [
        (
            system,
            datetime.fromisoformat(system["first_at"]),
            datetime.fromisoformat(system["last_at"]),
        )
        for system in systems
        if system.get("first_at") and system.get("last_at")
    ]
    if not spans:
        return {"has_data": False, "span_minutes": 0, "now_pct": 0.0, "lanes": [], "ticks": []}

    origin = min(first for _, first, _ in spans)
    end = max(now, origin + _MIN_WINDOW)
    window = end - origin

    lanes = []
    for system, first, last in spans:
        width = max(_pct(max(last - first, timedelta(0)), window), _MIN_LANE_WIDTH_PCT)
        left = _pct(max(first - origin, timedelta(0)), window)
        lanes.append(
            {
                "code": system["system_code"],
                "name": system.get("system_name", system["system_code"]),
                "tone": _system_tone(system.get("counts", {})),
                # 최소 폭을 준 스팬이 트랙 밖으로 밀려 안 보이는 것을 막는다.
                "left_pct": max(0.0, min(left, 100.0 - width)),
                "width_pct": width,
            }
        )

    ticks = [
        {
            "label": (origin + window * (i / (_TICK_COUNT - 1))).strftime("%H:%M"),
            "left_pct": round(i / (_TICK_COUNT - 1) * 100, 4),
        }
        for i in range(_TICK_COUNT)
    ]

    return {
        "has_data": True,
        "span_minutes": int(window.total_seconds() // 60),
        "now_pct": _pct(now - origin, window),
        "lanes": lanes,
        "ticks": ticks,
    }


def build_wall_view(summary: dict[str, Any]) -> dict[str, Any]:
    """Daily summary -> wall view. Never carries ``my_seconds``."""
    totals = summary.get("totals", {})
    attention = summary.get("attention", []) or []
    generated_at = summary.get("generated_at", "")
    return {
        "dominant": _dominant(totals, attention),
        "systems": [
            {
                "code": system["system_code"],
                "name": system["system_name"],
                "tone": _system_tone(system.get("counts", {})),
                "passed": int(system.get("counts", {}).get("passed", 0) or 0),
                "total": int(system.get("module_total", 0) or 0),
            }
            for system in summary.get("systems", [])
        ],
        "strip": [
            card
            for card in summary.get("cards", [])
            if card.get("key") not in _STRIP_EXCLUDED_CARD_KEYS
        ],
        "timeline": (
            build_timeline(summary.get("systems", []), now_iso=generated_at)
            if generated_at
            else {"has_data": False, "span_minutes": 0, "now_pct": 0.0, "lanes": [], "ticks": []}
        ),
        "date_label": summary.get("date_label", ""),
        "generated_at": generated_at,
    }
