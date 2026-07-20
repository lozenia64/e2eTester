"""Insights BC query/store ports."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.contexts.insights.contracts.query_rows import (
    AnomalyInboxRow,
    DailyRunSummaryRow,
    DailyStatusRow,
    StatsRollupRow,
)
from app.contexts.run.contracts.query_rows import ModuleHistoryRow, RunSummaryRow
from app.core.run_models import AnomalyHandling


class AnomalyHandlingStorePort(Protocol):
    """이상징후 인박스 **처리 레코드**(``AnomalyHandling``)의 저장 경계.

    ANOMALY/ERROR 로 끝난 모듈(이상건)마다 처리상태·담당자·메모를 모듈-Run 단위로 보관한다.
    이상건 자체는 Run 스캔으로 매번 새로 도출하고, 이 스토어는 그 위에 얹히는 '조치' 메타데이터만
    소유한다(행이 없으면 기본 ``UNRESOLVED``). ``module_run_id`` = ``f"{run_id}::{module_id}"``.
    """

    async def get(self, module_run_id: str) -> AnomalyHandling | None: ...
    async def list(self) -> list[AnomalyHandling]: ...
    async def upsert(self, handling: AnomalyHandling) -> AnomalyHandling: ...


class AnomalyInboxQueryPort(Protocol):
    """이상징후 인박스 **읽기** 쿼리 — ``anomaly_inbox_index`` 프로젝션."""

    async def list_page(
        self,
        allowed_system_codes: list[str] | None,
        *,
        limit: int = 500,
        offset: int = 0,
    ) -> list[AnomalyInboxRow]: ...


class DailyStatusQueryPort(Protocol):
    """일간 점검 현황 **읽기** 쿼리 — ``daily_system_status`` + 당일 Run 요약."""

    async def list_for_date(
        self,
        date_label: str,
        allowed_system_codes: list[str] | None,
    ) -> list[DailyStatusRow]: ...

    async def list_run_summaries_for_date(
        self,
        date_label: str,
        since_utc: datetime,
        allowed_system_codes: list[str] | None,
    ) -> list[DailyRunSummaryRow]: ...


class StatsQueryPort(Protocol):
    """사용량 통계 **읽기** 쿼리 — ``stats_rollup`` + run/module 이력 인덱스 행.

    통계는 Run 엔티티(blob)를 받지 않는다: Run 단위 귀속은 ``RunSummaryRow``,
    모듈 단위 집계(통과/실패/소요/절감시간)는 ``ModuleHistoryRow`` 로 계산한다.
    """

    async def rollup_between(
        self,
        from_day: str | None,
        to_day: str | None,
        *,
        system_codes: list[str] | None = None,
    ) -> list[StatsRollupRow]: ...

    async def list_usage_run_rows(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[RunSummaryRow]: ...

    async def list_usage_module_rows(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[ModuleHistoryRow]: ...
