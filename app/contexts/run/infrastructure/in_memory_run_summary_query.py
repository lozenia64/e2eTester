"""``RunSummaryQueryPort`` 인메모리 어댑터(테스트 전용).

프로덕션은 ``run_history_index`` 프로젝션(SQLite)을 읽지만, 브라우저/DB 없는 단위 테스트는
인메모리 저장소의 Run 에서 요약 행을 그때그때 도출한다 — 도출 규칙은 프로젝션과 동일한
``run_summary_fields`` 를 재사용하므로 두 어댑터의 의미가 갈라지지 않는다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.contexts.run.contracts.query_rows import (
    Page,
    RunComparisonRow,
    RunSummaryFilter,
    RunSummaryRow,
)
from app.core.enums import RunStatus
from app.domain.summary_fields import run_summary_fields

if TYPE_CHECKING:
    from app.contexts.run.infrastructure.in_memory_run_repository import InMemoryRunRepository
    from app.core.run_models import Run

_TERMINAL_FOR_BASELINE = {
    RunStatus.PASSED,
    RunStatus.ANOMALY,
    RunStatus.ERROR,
    RunStatus.FAILED,
}


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _parse(value: str | None) -> datetime | None:
    return _as_utc(datetime.fromisoformat(value)) if value else None


def _row_from_run(run: Run) -> RunSummaryRow:
    fields = run_summary_fields(run)
    return RunSummaryRow(
        run_id=run.run_id,
        system_code=fields["system_code"],
        system_name=fields["system_name"],
        status=RunStatus(fields["status"]),
        requested_at=_parse(fields["requested_at"]),
        started_at=_parse(fields["started_at"]),
        ended_at=_parse(fields["ended_at"]),
        schedule_id=fields["schedule_id"],
        suite_id=fields["suite_id"],
        created_by_user_id=fields["created_by_user_id"],
        created_by_user_name=fields["created_by_user_name"],
        triggered_by=fields["triggered_by"],
        awaiting_input_module_id=fields["awaiting_input_module_id"],
        awaiting_input_prompt=fields["awaiting_input_prompt"],
        module_total=fields["module_total"],
        module_defined_total=fields["module_defined_total"],
        module_skipped=fields["module_skipped"],
        module_passed=fields["module_passed"],
        current_module_name=fields["current_module_name"],
        failed_module_name=fields["failed_module_name"],
    )


def _matches(row: RunSummaryRow, query: RunSummaryFilter) -> bool:
    if query.system_codes is not None and row.system_code not in query.system_codes:
        return False
    if query.system_code is not None and row.system_code != query.system_code:
        return False
    if query.statuses is not None and row.status not in query.statuses:
        return False
    if query.user_id is not None and row.created_by_user_id != query.user_id:
        return False
    if query.user_name_query:
        name = row.created_by_user_name or ""
        if query.user_name_query.strip() not in name:
            return False
    if query.schedule_id is not None and row.schedule_id != query.schedule_id:
        return False
    if query.suite_id is not None and row.suite_id != query.suite_id:
        return False
    if query.requested_since is not None and row.requested_at < _as_utc(query.requested_since):
        return False
    if query.requested_before is not None and row.requested_at >= _as_utc(query.requested_before):
        return False
    if query.schedule_tagged_only and row.schedule_id is None:
        return False
    if query.triggered_by == "schedule":
        if row.triggered_by != "schedule" and row.schedule_id is None:
            return False
    elif query.triggered_by == "suite":
        if row.triggered_by != "suite" and row.suite_id is None:
            return False
    elif query.triggered_by == "manual":
        if row.triggered_by not in (None, "", "manual"):
            return False
    if query.run_id_query:
        prefix = query.run_id_query.strip()
        if not row.run_id.startswith(prefix):
            return False
    return True


class InMemoryRunSummaryQuery:
    """인메모리 저장소 위의 ``RunSummaryQueryPort`` 구현(테스트 전용)."""

    def __init__(self, repository: InMemoryRunRepository) -> None:
        self._repository = repository

    async def _all_rows(self) -> list[RunSummaryRow]:
        runs = await self._repository.list_all_runs()
        rows = [_row_from_run(run) for run in runs]
        rows.sort(key=lambda row: row.requested_at, reverse=True)
        return rows

    async def list_summaries(self, query: RunSummaryFilter, page: Page) -> list[RunSummaryRow]:
        rows = [row for row in await self._all_rows() if _matches(row, query)]
        return rows[page.offset : page.offset + page.limit]

    async def count(self, query: RunSummaryFilter) -> int:
        return len([row for row in await self._all_rows() if _matches(row, query)])

    async def counts_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in await self._all_rows():
            counts[row.status.value] = counts.get(row.status.value, 0) + 1
        return counts

    async def counts_by_status_filtered(self, query: RunSummaryFilter) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in await self._all_rows():
            if not _matches(row, query):
                continue
            counts[row.status.value] = counts.get(row.status.value, 0) + 1
        return counts

    async def daily_status_counts(
        self, query: RunSummaryFilter, *, tz: ZoneInfo | None = None
    ) -> list[tuple[str, str, int]]:
        buckets: dict[tuple[str, str], int] = {}
        for row in await self._all_rows():
            if not _matches(row, query):
                continue
            if tz is not None:
                day_key = row.requested_at.astimezone(tz).strftime("%Y-%m-%d")
            else:
                day_key = row.requested_at.isoformat()[:10]
            key = (day_key, row.status.value)
            buckets[key] = buckets.get(key, 0) + 1
        return [(day, status, count) for (day, status), count in sorted(buckets.items())]

    async def list_run_ids(self, query: RunSummaryFilter) -> list[str]:
        return [row.run_id for row in await self._all_rows() if _matches(row, query)]

    async def last_finished_at_by_system(self) -> dict[str, datetime]:
        result: dict[str, datetime] = {}
        for row in await self._all_rows():
            if row.status == RunStatus.CANCELLED or row.status not in {
                *_TERMINAL_FOR_BASELINE,
            }:
                continue
            moment = row.ended_at or row.requested_at
            if row.system_code not in result or moment > result[row.system_code]:
                result[row.system_code] = moment
        return result

    async def avg_duration_ms_by_system(self, *, days: int = 30) -> dict[str, int]:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        buckets: dict[str, list[float]] = {}
        for row in await self._all_rows():
            if row.status != RunStatus.PASSED:
                continue
            if row.started_at is None or row.ended_at is None:
                continue
            if row.requested_at < cutoff:
                continue
            buckets.setdefault(row.system_code, []).append(
                (row.ended_at - row.started_at).total_seconds() * 1000.0
            )
        return {code: round(sum(v) / len(v)) for code, v in buckets.items() if v}

    async def list_summaries_for_last_finished_by_system(self) -> list[RunSummaryRow]:
        last_map = await self.last_finished_at_by_system()
        all_rows = await self._all_rows()
        if not last_map:
            return self._fallback_latest_terminal_per_system(all_rows)
        result: list[RunSummaryRow] = []
        for system_code in sorted(last_map):
            moment = _as_utc(last_map[system_code])
            matches = sorted(
                [
                    row
                    for row in all_rows
                    if row.system_code == system_code
                    and _as_utc(row.ended_at or row.requested_at) == moment
                ],
                key=lambda row: row.requested_at,
                reverse=True,
            )
            if matches:
                result.append(matches[0])
        if result:
            return result
        return self._fallback_latest_terminal_per_system(all_rows)

    @staticmethod
    def _fallback_latest_terminal_per_system(rows: list[RunSummaryRow]) -> list[RunSummaryRow]:
        latest: dict[str, RunSummaryRow] = {}
        for row in rows:
            if row.status not in _TERMINAL_FOR_BASELINE:
                continue
            moment = row.ended_at or row.requested_at
            current = latest.get(row.system_code)
            if current is None:
                latest[row.system_code] = row
                continue
            current_moment = current.ended_at or current.requested_at
            if moment > current_moment or (
                moment == current_moment and row.requested_at > current.requested_at
            ):
                latest[row.system_code] = row
        return [latest[code] for code in sorted(latest)]

    async def find_previous_finished_run_id(
        self, system_code: str, before: datetime, exclude_run_id: str
    ) -> str | None:
        before_utc = _as_utc(before)
        for row in await self._all_rows():
            if (
                row.system_code == system_code
                and row.status in _TERMINAL_FOR_BASELINE
                and row.requested_at < before_utc
                and row.run_id != exclude_run_id
            ):
                return row.run_id
        return None

    async def list_comparisons(self, run_ids: list[str]) -> dict[str, RunComparisonRow]:
        wanted = set(run_ids)
        result: dict[str, RunComparisonRow] = {}
        for run in await self._repository.list_all_runs():
            if run.run_id not in wanted or run.comparison is None:
                continue
            comparison = run.comparison
            result[run.run_id] = RunComparisonRow(
                run_id=run.run_id,
                baseline_run_id=comparison.baseline_run_id,
                newly_failed=tuple(comparison.newly_failed),
                recovered=tuple(comparison.recovered),
                still_failing=tuple(comparison.still_failing),
            )
        return result
