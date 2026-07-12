"""폐루프 복구 콘솔의 지표 집계 — 순수 빌더(치유 이벤트 목록 → KPI/추이/만성 지점).

I/O 없음. ``HealingService`` 가 스토어에서 읽은 이벤트/패치를 넘겨 호출한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.contexts.healing.models import (
    CHRONIC_HEAL_THRESHOLD,
    HealingAction,
    HealingEvent,
    HealingPatch,
    PatchStatus,
)


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def build_healing_metrics(
    events: list[HealingEvent],
    patches: list[HealingPatch],
    *,
    now: datetime,
    trend_days: int = 30,
) -> dict[str, Any]:
    """상단 KPI(이번 달 자동 복구 N건 · 무인 통과율 · MTTR) + 일별 추이 + 만성 지점 표."""
    now = _as_utc(now)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_events = [e for e in events if _as_utc(e.created_at) >= month_start]

    auto_recovered = [
        e
        for e in month_events
        if e.action is HealingAction.AUTO_HEALED and e.retry_succeeded is True
    ]
    unattended_rate = (
        round(len(auto_recovered) / len(month_events) * 100, 1) if month_events else None
    )
    mttr_ms = (
        round(sum(e.duration_ms for e in auto_recovered) / len(auto_recovered))
        if auto_recovered
        else None
    )

    # 일별 추이(최근 trend_days 일): 자동 복구 / 그 외(제안·실패) 건수.
    trend: list[dict[str, Any]] = []
    day_start = (now - timedelta(days=trend_days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    buckets: dict[str, dict[str, int]] = {}
    for offset in range(trend_days):
        day = (day_start + timedelta(days=offset)).date().isoformat()
        buckets[day] = {"auto": 0, "other": 0}
    for event in events:
        day = _as_utc(event.created_at).date().isoformat()
        bucket = buckets.get(day)
        if bucket is None:
            continue
        if event.action is HealingAction.AUTO_HEALED and event.retry_succeeded is True:
            bucket["auto"] += 1
        else:
            bucket["other"] += 1
    trend = [{"date": day, **counts} for day, counts in buckets.items()]

    # 시스템별 집계(전체 기간).
    by_system: dict[str, dict[str, int]] = {}
    for event in events:
        row = by_system.setdefault(
            event.system_code, {"total": 0, "auto": 0, "suggested": 0, "no_candidate": 0}
        )
        row["total"] += 1
        if event.action is HealingAction.AUTO_HEALED:
            row["auto"] += 1
        elif event.action is HealingAction.SUGGESTED:
            row["suggested"] += 1
        else:
            row["no_candidate"] += 1

    return {
        "kpi": {
            "month_auto_recovered": len(auto_recovered),
            "month_events": len(month_events),
            "unattended_rate": unattended_rate,
            "mttr_ms": mttr_ms,
            "pending_patches": sum(1 for p in patches if p.status is PatchStatus.PROPOSED),
        },
        "trend": trend,
        "by_system": by_system,
        "chronic": build_chronic_selectors(events),
    }


def build_chronic_selectors(events: list[HealingEvent]) -> list[dict[str, Any]]:
    """같은 셀렉터가 반복 치유되면 '만성'으로 승격한다(임계 CHRONIC_HEAL_THRESHOLD 회)."""
    grouped: dict[tuple[str, str], list[HealingEvent]] = {}
    for event in events:
        grouped.setdefault((event.system_code, event.broken_selector), []).append(event)

    chronic: list[dict[str, Any]] = []
    for (system_code, selector), group in grouped.items():
        if len(group) < CHRONIC_HEAL_THRESHOLD:
            continue
        latest = max(group, key=lambda e: _as_utc(e.created_at))
        chronic.append(
            {
                "system_code": system_code,
                "broken_selector": selector,
                "heal_count": len(group),
                "last_healed_selector": latest.healed_selector,
                "last_seen": _as_utc(latest.created_at).isoformat(),
                "module_name": latest.module_name,
            }
        )
    chronic.sort(key=lambda row: row["heal_count"], reverse=True)
    return chronic


def heal_counts_by_selector(events: list[HealingEvent]) -> dict[tuple[str, str], int]:
    """(system_code, broken_selector) → 치유 시도 횟수. 내구성 맵의 만성 신호 입력."""
    counts: dict[tuple[str, str], int] = {}
    for event in events:
        key = (event.system_code, event.broken_selector)
        counts[key] = counts.get(key, 0) + 1
    return counts
