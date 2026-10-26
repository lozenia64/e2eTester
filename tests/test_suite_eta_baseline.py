"""ETA baseline — 시스템별 평균 Run 소요시간.

'정상 실행이 얼마나 걸리는가' 를 재는 것이므로 PASSED 만 센다. 중간에 끊긴
Run 을 섞으면 평균이 짧아져 ETA 가 낙관적으로 빗나간다(설계 D3).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.contexts.run.infrastructure.in_memory_run_summary_query import InMemoryRunSummaryQuery
from app.contexts.run.infrastructure.sqlite_run_summary_query import SqliteRunSummaryQuery
from app.core.enums import RunStatus
from app.platform.eventing.support import SqliteDatabase, ensure_schema


@pytest.fixture(autouse=True)
def fixed_query_clock(monkeypatch):
    """조회 어댑터의 시계를 고정해 30일 표본이 실행 날짜에 따라 사라지지 않게 한다."""

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 30, 9, 0, tzinfo=UTC).astimezone(tz)

    for adapter in ("in_memory_run_summary_query", "sqlite_run_summary_query"):
        monkeypatch.setattr(f"app.contexts.run.infrastructure.{adapter}.datetime", FixedDatetime)


def _row(system_code: str, status: RunStatus, *, started_min: int, duration_min: int | None):
    """테스트용 run_history_index 행 한 줄."""
    base = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
    started = base + timedelta(minutes=started_min)
    ended = started + timedelta(minutes=duration_min) if duration_min is not None else None
    return {
        "system_code": system_code,
        "status": status,
        "requested_at": started,
        "started_at": started,
        "ended_at": ended,
    }


class _MemoryQuery(InMemoryRunSummaryQuery):
    """seeded 행 위에서 도는 in-memory 어댑터 — 집계 로직만 검증한다."""

    def __init__(self) -> None:
        self._rows: list[SimpleNamespace] = []

    async def seed(self, rows: list[dict]) -> None:
        self._rows.extend(SimpleNamespace(**row) for row in rows)

    async def _all_rows(self) -> list[SimpleNamespace]:
        return list(self._rows)


class _SqliteQuery(SqliteRunSummaryQuery):
    """run_history_index 에 직접 INSERT — 프로젝션이 아니라 집계 SQL 을 검증한다."""

    async def seed(self, rows: list[dict]) -> None:
        for row in rows:
            await self._db.execute(
                "INSERT INTO run_history_index "
                "(run_id, system_code, status, requested_at, started_at, ended_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    uuid4().hex,
                    row["system_code"],
                    row["status"].value,
                    row["requested_at"].isoformat(),
                    row["started_at"].isoformat() if row["started_at"] is not None else None,
                    row["ended_at"].isoformat() if row["ended_at"] is not None else None,
                ),
            )


@pytest.fixture
def memory_query() -> _MemoryQuery:
    return _MemoryQuery()


@pytest.fixture
async def sqlite_query(tmp_path) -> _SqliteQuery:
    db = SqliteDatabase(tmp_path / "eta_baseline.db")
    await ensure_schema(db)
    return _SqliteQuery(db)


@pytest.fixture(params=["memory_query", "sqlite_query"])
def query(request):
    return request.getfixturevalue(request.param)


async def test_averages_only_passed_runs(query) -> None:
    """실패 Run 이 평균을 끌어내리면 안 된다."""
    await query.seed(
        [
            _row("hom", RunStatus.PASSED, started_min=0, duration_min=4),
            _row("hom", RunStatus.PASSED, started_min=60, duration_min=6),
            _row("hom", RunStatus.ERROR, started_min=120, duration_min=1),
        ]
    )
    result = await query.avg_duration_ms_by_system()
    assert result["hom"] == 5 * 60 * 1000


async def test_unfinished_runs_are_excluded(query) -> None:
    """진행 중인 Run 은 ended_at 이 없어 표본이 아니다."""
    await query.seed(
        [
            _row("mhm", RunStatus.PASSED, started_min=0, duration_min=2),
            _row("mhm", RunStatus.RUNNING, started_min=10, duration_min=None),
        ]
    )
    assert (await query.avg_duration_ms_by_system())["mhm"] == 2 * 60 * 1000


async def test_system_without_history_has_no_key(query) -> None:
    """0 을 돌려주면 화면이 '평균 0초' 를 표시한다. 키가 없어야 '평균 —' 로 갈린다."""
    await query.seed([_row("hom", RunStatus.PASSED, started_min=0, duration_min=3)])
    result = await query.avg_duration_ms_by_system()
    assert "chbot" not in result


async def test_days_window_excludes_older_runs(query) -> None:
    old = _row("fp", RunStatus.PASSED, started_min=0, duration_min=10)
    old["requested_at"] = datetime(2026, 1, 1, tzinfo=UTC)
    await query.seed([old, _row("fp", RunStatus.PASSED, started_min=0, duration_min=2)])
    assert (await query.avg_duration_ms_by_system(days=30))["fp"] == 2 * 60 * 1000


async def test_sqlite_and_memory_agree(sqlite_query, memory_query) -> None:
    """두 어댑터가 갈라지면 테스트가 프로덕션을 대변하지 못한다."""
    rows = [
        _row("hom", RunStatus.PASSED, started_min=0, duration_min=4),
        _row("hom", RunStatus.PASSED, started_min=60, duration_min=6),
        _row("hom", RunStatus.ERROR, started_min=120, duration_min=1),
        _row("mhm", RunStatus.PASSED, started_min=0, duration_min=2),
    ]
    await memory_query.seed(rows)
    await sqlite_query.seed(rows)
    assert (
        await sqlite_query.avg_duration_ms_by_system()
        == await memory_query.avg_duration_ms_by_system()
        == {"hom": 300000, "mhm": 120000}
    )
