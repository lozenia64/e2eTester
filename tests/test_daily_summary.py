from datetime import UTC, datetime

from app.contexts.insights.application.daily_summary import build_daily_summary
from app.core.stats_models import SavingsSummary

TOTALS = {"modules": 36, "passed": 34, "pass_rate": 94, "anomaly": 2, "error": 0}
HEALING = {
    "kpi": {"month_auto_recovered": 21, "unattended_rate": 82.0, "pending_patches": 2},
    "trend": [
        {"date": "2026-08-18", "auto": 3, "other": 1},
        {"date": "2026-08-19", "auto": 7, "other": 0},
    ],
}
SAVINGS = SavingsSummary(
    total_seconds=1116000,
    my_seconds=72000,
    run_count=1240,
    module_count=36,
    basis_updated_at=datetime(2026, 8, 1, tzinfo=UTC),
    estimated=True,
    note="1,240회 · 36개 모듈 × 수동 추정치 (기준 8/1)",
)


def _cards(**overrides):
    kwargs = {
        "totals": TOTALS,
        "healing_metrics": HEALING,
        "savings": SAVINGS,
        "today_label": "2026-08-19",
    }
    kwargs.update(overrides)
    summary = build_daily_summary(
        kwargs["totals"],
        kwargs["healing_metrics"],
        kwargs["savings"],
        today_label=kwargs["today_label"],
    )
    return {card["key"]: card for card in summary["cards"]}


def test_produces_exactly_four_cards_in_order():
    summary = build_daily_summary(TOTALS, HEALING, SAVINGS, today_label="2026-08-19")
    assert [c["key"] for c in summary["cards"]] == [
        "pass_rate",
        "self_healed",
        "pending_patches",
        "savings",
    ]


def test_self_healed_uses_today_bucket_not_month():
    """오늘 버킷(7)을 쓴다. 이번 달 누적(21)은 부연으로만."""
    card = _cards()["self_healed"]
    assert card["value"] == 7
    assert "21" in card["note"]


def test_self_healed_is_zero_when_today_bucket_absent():
    card = _cards(healing_metrics={"kpi": HEALING["kpi"], "trend": []})["self_healed"]
    assert card["value"] == 0


def test_every_card_has_a_period_label():
    for key, card in _cards().items():
        assert card["period"], key


def test_only_pending_patches_uses_anomaly_tone():
    cards = _cards()
    assert cards["pending_patches"]["tone"] == "anomaly"
    assert cards["pass_rate"]["tone"] != "anomaly"
    assert cards["self_healed"]["tone"] != "anomaly"
    assert cards["savings"]["tone"] != "anomaly"


def test_pending_patches_links_to_patch_list():
    assert _cards()["pending_patches"]["href"] == "/self-healing#patches"


def test_estimated_card_always_carries_note():
    for card in _cards().values():
        if card["estimated"]:
            assert card["note"].strip(), card["key"]


def test_only_savings_is_estimated():
    cards = _cards()
    assert cards["savings"]["estimated"] is True
    assert cards["pass_rate"]["estimated"] is False
    assert cards["self_healed"]["estimated"] is False
    assert cards["pending_patches"]["estimated"] is False


def test_unset_basis_shows_guidance_instead_of_zero_hours():
    """추정치 미설정 상태에서 0h 를 성과처럼 띄우지 않는다."""
    empty = SavingsSummary(
        total_seconds=0,
        my_seconds=0,
        run_count=0,
        module_count=36,
        basis_updated_at=None,
        estimated=False,
        note="",
    )
    card = _cards(savings=empty)["savings"]
    assert card["value"] == "추정치 미설정"
    assert card["href"] == "/admin/modules"


def test_summary_has_no_user_identifiers():
    summary = build_daily_summary(TOTALS, HEALING, SAVINGS, today_label="2026-08-19")
    assert "email" not in str(summary)
    assert "user_id" not in str(summary)
