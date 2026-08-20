"""Wall view builder.

No I/O. Routes pass in ``DailySummaryQueries.get_daily_summary()`` output and
this module reduces it to the view shape the wall template needs.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import ModuleStatus
from app.web.status_view import status_badge_view

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


def build_wall_view(summary: dict[str, Any]) -> dict[str, Any]:
    """Daily summary -> wall view. Never carries ``my_seconds``."""
    totals = summary.get("totals", {})
    attention = summary.get("attention", []) or []
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
        "date_label": summary.get("date_label", ""),
        "generated_at": summary.get("generated_at", ""),
    }
