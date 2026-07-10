"""폐루프 복구 콘솔 지표 집계(순수 빌더) 단위 테스트."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.healing.metrics import build_healing_metrics, heal_counts_by_selector
from app.healing.models import HealingAction, HealingEvent, HealingPatch, PatchStatus

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _event(
    *,
    action: HealingAction = HealingAction.AUTO_HEALED,
    retry_succeeded: bool | None = True,
    created_at: datetime = NOW,
    system_code: str = "hrp",
    broken: str = "#btnRA",
    duration_ms: int = 1200,
) -> HealingEvent:
    return HealingEvent(
        event_id=uuid4().hex,
        run_id="r1",
        module_id="login",
        system_code=system_code,
        broken_selector=broken,
        healed_selector="#btnRA2",
        action=action,
        retry_succeeded=retry_succeeded,
        duration_ms=duration_ms,
        created_at=created_at,
    )


def _patch(status: PatchStatus = PatchStatus.PROPOSED) -> HealingPatch:
    return HealingPatch(
        patch_id=uuid4().hex,
        event_id="e1",
        system_code="hrp",
        broken_selector="#btnRA",
        healed_selector="#btnRA2",
        file_path="app/systems/hrp/steps/login.py",
        status=status,
        created_at=NOW,
    )


def test_month_kpi_counts_only_verified_auto_heals():
    events = [
        _event(duration_ms=1000),
        _event(duration_ms=3000),
        _event(action=HealingAction.SUGGESTED, retry_succeeded=None),
        _event(action=HealingAction.AUTO_HEALED, retry_succeeded=False),
        # 지난달 이벤트는 이번 달 KPI 에서 제외.
        _event(created_at=NOW - timedelta(days=45)),
    ]
    metrics = build_healing_metrics(events, [_patch(), _patch(PatchStatus.APPROVED)], now=NOW)

    assert metrics["kpi"]["month_auto_recovered"] == 2
    assert metrics["kpi"]["month_events"] == 4
    assert metrics["kpi"]["unattended_rate"] == 50.0
    assert metrics["kpi"]["mttr_ms"] == 2000
    assert metrics["kpi"]["pending_patches"] == 1


def test_empty_events_produce_null_rates():
    metrics = build_healing_metrics([], [], now=NOW)
    assert metrics["kpi"]["month_auto_recovered"] == 0
    assert metrics["kpi"]["unattended_rate"] is None
    assert metrics["kpi"]["mttr_ms"] is None
    assert len(metrics["trend"]) == 30


def test_chronic_promotion_needs_three_heals():
    twice = [_event(), _event()]
    assert build_healing_metrics(twice, [], now=NOW)["chronic"] == []

    thrice = twice + [_event()]
    chronic = build_healing_metrics(thrice, [], now=NOW)["chronic"]
    assert len(chronic) == 1
    assert chronic[0]["broken_selector"] == "#btnRA"
    assert chronic[0]["heal_count"] == 3


def test_heal_counts_grouped_by_system_and_selector():
    events = [
        _event(system_code="hrp"),
        _event(system_code="hrp"),
        _event(system_code="fp"),
        _event(system_code="hrp", broken="#other"),
    ]
    counts = heal_counts_by_selector(events)
    assert counts[("hrp", "#btnRA")] == 2
    assert counts[("fp", "#btnRA")] == 1
    assert counts[("hrp", "#other")] == 1


def test_trend_buckets_split_auto_and_other():
    events = [
        _event(),
        _event(action=HealingAction.NO_CANDIDATE, retry_succeeded=None),
    ]
    metrics = build_healing_metrics(events, [], now=NOW)
    today = next(row for row in metrics["trend"] if row["date"] == "2026-07-10")
    assert today["auto"] == 1
    assert today["other"] == 1
