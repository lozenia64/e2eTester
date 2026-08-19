from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.contexts.insights.application.stats_service import StatsService
from app.core.stats_models import (
    SavingsSummary,
    SystemUsageStat,
    UsageStats,
    UserUsageStat,
)

FROM_DT = datetime(2026, 8, 1, tzinfo=UTC)
TO_DT = datetime(2026, 8, 19, tzinfo=UTC)


def test_summary_never_carries_user_identifiers():
    """프라이버시 계약 — 사용자별 분해는 관리자 전용에만 남는다."""
    summary = SavingsSummary(
        total_seconds=1116000,
        my_seconds=72000,
        run_count=1240,
        module_count=36,
        basis_updated_at=datetime(2026, 8, 1, tzinfo=UTC),
        estimated=True,
        note="1,240회 · 36개 모듈 × 수동 추정치 (기준 8/1)",
    )
    payload = summary.model_dump()
    forbidden = {"user_id", "email", "user_name", "by_user"}
    assert forbidden.isdisjoint(payload.keys())
    # 중첩 구조에도 없어야 한다
    assert "email" not in str(payload)


def test_estimated_requires_note():
    """근거 없는 추정치를 만들 수 없다(정직성 계약)."""
    with pytest.raises(ValueError, match="note"):
        SavingsSummary(
            total_seconds=1,
            my_seconds=0,
            run_count=1,
            module_count=1,
            basis_updated_at=None,
            estimated=True,
            note="",
        )


def test_not_estimated_allows_empty_note():
    summary = SavingsSummary(
        total_seconds=0,
        my_seconds=0,
        run_count=0,
        module_count=0,
        basis_updated_at=None,
        estimated=False,
        note="",
    )
    assert summary.note == ""


def _service_with_usage(stats: UsageStats, *, settings_rows=()) -> StatsService:
    """get_savings_summary 만 검증한다 — get_usage_stats 는 이미 다른 테스트가 덮는다.

    StatsQueryPort 전체를 스텁하는 대신 get_usage_stats 를 대체한다. 새로 추가된
    로직(합산·본인 몫 추출·근거 문자열)만 좁게 검증하기 위해서다.
    """

    class _Registry:
        def list_systems(self):
            return [
                SimpleNamespace(system_code="HOM", name="대표홈", modules=[1, 2]),
                SimpleNamespace(system_code="FP", name="위촉서류", modules=[3]),
            ]

    class _SettingsRepo:
        async def list(self):
            return list(settings_rows)

    service = StatsService(
        stats_query=SimpleNamespace(),
        suite_summary_query=SimpleNamespace(),
        registry=_Registry(),
        module_settings_repo=_SettingsRepo(),
    )

    async def _fake_usage(from_dt=None, to_dt=None):
        return stats

    service.get_usage_stats = _fake_usage  # type: ignore[method-assign]
    return service


def _usage_stats() -> UsageStats:
    def _sys(code: str, name: str, saved: int) -> SystemUsageStat:
        return SystemUsageStat(
            system_code=code,
            system_name=name,
            runs=1,
            modules_passed=1,
            modules_failed=0,
            total_duration_ms=1000,
            manual_seconds_saved=saved,
        )

    return UsageStats(
        period_from=FROM_DT,
        period_to=TO_DT,
        generated_at=TO_DT,
        total_runs=3,
        total_users=2,
        by_user=[
            UserUsageStat(
                user_id="user-a",
                user_name="가",
                email="a@example.com",
                total_runs=2,
                total_modules_passed=2,
                total_modules_failed=0,
                total_duration_ms=2000,
                manual_seconds_saved=600,
                by_system=[],
            ),
            UserUsageStat(
                user_id="user-b",
                user_name="나",
                email="b@example.com",
                total_runs=1,
                total_modules_passed=1,
                total_modules_failed=0,
                total_duration_ms=1000,
                manual_seconds_saved=300,
                by_system=[],
            ),
        ],
        by_system=[_sys("HOM", "대표홈", 600), _sys("FP", "위촉서류", 300)],
    )


@pytest.mark.asyncio
async def test_get_savings_summary_sums_systems_and_picks_my_share():
    """전사 합계는 by_system 합, 내 기여분은 로그인 사용자의 것만."""
    service = _service_with_usage(_usage_stats())
    summary = await service.get_savings_summary(from_dt=FROM_DT, to_dt=TO_DT, user_id="user-a")
    assert summary.total_seconds == 900  # HOM 600 + FP 300
    assert summary.my_seconds == 600  # user-a 몫만
    assert summary.run_count == 3
    assert summary.module_count == 3  # HOM 2 + FP 1
    assert summary.estimated is True
    assert "3회" in summary.note


@pytest.mark.asyncio
async def test_unknown_user_gets_zero_my_seconds():
    service = _service_with_usage(_usage_stats())
    summary = await service.get_savings_summary(from_dt=FROM_DT, to_dt=TO_DT, user_id="nobody")
    assert summary.total_seconds == 900
    assert summary.my_seconds == 0


@pytest.mark.asyncio
async def test_returned_summary_drops_the_user_list():
    """by_user 를 받아 계산하되 응답에는 남기지 않는다."""
    service = _service_with_usage(_usage_stats())
    summary = await service.get_savings_summary(from_dt=FROM_DT, to_dt=TO_DT, user_id="user-a")
    assert "a@example.com" not in str(summary.model_dump())


@pytest.mark.asyncio
async def test_zero_savings_is_not_estimated():
    """추정치 미설정 → estimated=False, note 없이도 유효하다."""
    stats = _usage_stats().model_copy(
        update={
            "by_system": [
                SystemUsageStat(
                    system_code="HOM",
                    system_name="대표홈",
                    runs=1,
                    modules_passed=1,
                    modules_failed=0,
                    total_duration_ms=1000,
                    manual_seconds_saved=0,
                )
            ]
        }
    )
    service = _service_with_usage(stats)
    summary = await service.get_savings_summary(from_dt=FROM_DT, to_dt=TO_DT, user_id="user-a")
    assert summary.total_seconds == 0
    assert summary.estimated is False
