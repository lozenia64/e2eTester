"""admin_run_history_board 순수 빌더 단위 테스트 — 이번 달 시스템 지도."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.contexts.insights.application.admin_run_history_board import (
    build_admin_run_history_board,
    build_system_map,
)

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
FROM = datetime(2026, 9, 30, 15, 0, tzinfo=UTC)


def _map(counts: list[tuple[str, str, str, int]]) -> dict:
    return build_system_map(counts, period_from=FROM, period_to=NOW)


def test_system_map_sums_anomaly_and_failed_and_sorts_by_runs() -> None:
    result = _map(
        [
            ("chbot", "챗봇", "ANOMALY", 3),
            ("chbot", "챗봇", "PASSED", 2),
            ("hom", "대표홈페이지", "ANOMALY", 1),
            ("hom", "대표홈페이지", "FAILED", 1),
            ("hom", "대표홈페이지", "PASSED", 5),
        ]
    )
    assert result["systems"] == [
        {"system_code": "hom", "system_name": "대표홈페이지", "runs": 7, "anomaly": 2},
        {"system_code": "chbot", "system_name": "챗봇", "runs": 5, "anomaly": 3},
    ]
    assert result["top_runs"] == "hom"
    assert result["top_anomaly"] == "chbot"
    assert result["period"] == {"from": FROM.isoformat(), "to": NOW.isoformat()}


def test_system_map_tie_breaks_by_code() -> None:
    result = _map(
        [
            ("mhm", "모바일홈", "ANOMALY", 1),
            ("mhm", "모바일홈", "PASSED", 2),
            ("hom", "대표홈페이지", "ANOMALY", 1),
            ("hom", "대표홈페이지", "PASSED", 2),
        ]
    )
    assert [s["system_code"] for s in result["systems"]] == ["hom", "mhm"]
    assert result["top_runs"] == "hom"
    assert result["top_anomaly"] == "hom"


def test_system_map_no_anomaly_gives_null() -> None:
    result = _map([("hom", "대표홈페이지", "PASSED", 3)])
    assert result["top_runs"] == "hom"
    assert result["top_anomaly"] is None


def test_system_map_empty() -> None:
    result = _map([])
    assert result["systems"] == []
    assert result["top_runs"] is None
    assert result["top_anomaly"] is None


def test_board_payload_keys() -> None:
    board = build_admin_run_history_board(now=NOW, tz=KST, today_start=NOW, system_map=_map([]))
    assert set(board) == {"generated_at", "timezone", "today_start", "system_map"}
