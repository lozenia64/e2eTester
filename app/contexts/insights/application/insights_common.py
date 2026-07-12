"""인사이트 집계 빌더가 공유하는 순수 헬퍼 + 읽기 뷰(브라우저·DB·설정 접근 없음).

빌더의 입력은 더 이상 ``Run`` 엔티티(blob)가 아니라, 프로젝션 행(``run_history_index`` ·
``module_history_index`` · ``run_comparison_cache``)으로 조립한 ``RunHistoryView`` 다 —
읽기 경로에서 도메인 엔티티가 완전히 사라진다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.enums import ModuleStatus, RunStatus
from app.core.status_labels import MODULE_ANOMALY_STATUSES, MODULE_ERROR_STATUSES

if TYPE_CHECKING:
    from datetime import datetime, tzinfo

    from app.storage.query_rows import (
        ModuleHistoryRow,
        RunComparisonRow,
        RunSummaryRow,
    )

# 이상건(인박스·집계 대상)으로 세는 종료 상태 = 이상징후 ∪ 점검실패.
ANOMALY_OR_ERROR_STATUSES = frozenset(MODULE_ANOMALY_STATUSES | MODULE_ERROR_STATUSES)

# '점검 결과가 확정된' 모듈 상태(통과율·시계열의 분모로 삼는다).
CONCLUSIVE_MODULE_STATUSES = frozenset(
    {ModuleStatus.PASSED, *MODULE_ANOMALY_STATUSES, *MODULE_ERROR_STATUSES}
)


def module_run_id(run_id: str, module_id: str) -> str:
    """이상건(모듈 실행 1건)의 안정적 식별자."""
    return f"{run_id}::{module_id}"


def split_module_run_id(value: str) -> tuple[str, str]:
    """``module_run_id`` 를 ``(run_id, module_id)`` 로 되돌린다."""
    run_id, _, module_id = value.partition("::")
    return run_id, module_id


def screenshot_url(module) -> str | None:
    """모듈 아티팩트 중 스크린샷(final.png)의 서빙 URL. 없으면 ``None``.

    ``artifacts`` 속성을 가진 어떤 모듈 뷰든 받는다(덕 타이핑).
    """
    for artifact in module.artifacts or []:
        if artifact.lower().endswith(".png"):
            return artifact
    return None


def module_kind(status: ModuleStatus) -> str:
    """이상건 대분류: ``error``(점검실패) / ``anomaly``(이상징후)."""
    if status in MODULE_ERROR_STATUSES:
        return "error"
    return "anomaly"


def module_occurred_at(run, module) -> datetime:
    """모듈 결과의 대표 시각(종료 → 시작 → Run 요청 순으로 폴백)."""
    return module.ended_at or module.started_at or run.ended_at or run.requested_at


def local_date_key(moment: datetime, tz: tzinfo) -> str:
    """UTC/naive 시각을 주어진 타임존의 ``YYYY-MM-DD`` 로 버킷팅한다."""
    if moment.tzinfo is None:
        from datetime import UTC

        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(tz).strftime("%Y-%m-%d")


def sort_runs_desc(runs: list[RunHistoryView]) -> list[RunHistoryView]:
    return sorted(runs, key=lambda r: r.requested_at, reverse=True)


def sort_runs_asc(runs: list[RunHistoryView]) -> list[RunHistoryView]:
    return sorted(runs, key=lambda r: r.requested_at)


# --- 프로젝션 조립 읽기 뷰 ---------------------------------------------------


@dataclass(frozen=True)
class ModuleHistoryView:
    """빌더가 소비하는 모듈 실행 이력 1건(``module_history_index`` 행의 뷰)."""

    module_id: str
    name: str | None
    status: ModuleStatus
    message: str | None
    duration_ms: int | None
    current_url: str | None
    artifacts: tuple[str, ...]
    started_at: datetime | None
    ended_at: datetime | None
    ai_category: str | None
    ai_summary: str | None
    ai_action: str | None


@dataclass(frozen=True)
class RunComparisonView:
    """직전 Run 대비 변화(``run_comparison_cache`` 행의 뷰)."""

    newly_failed: tuple[str, ...]
    recovered: tuple[str, ...]
    still_failing: tuple[str, ...]


@dataclass(frozen=True)
class RunHistoryView:
    """빌더가 소비하는 Run 1건의 읽기 뷰 — 프로젝션 행 3종으로 조립(blob 아님)."""

    run_id: str
    system_code: str
    system_name: str | None
    status: RunStatus
    requested_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    triggered_by: str
    suite_id: str | None
    schedule_id: str | None
    created_by_user_id: str | None
    created_by_user_name: str | None
    modules: tuple[ModuleHistoryView, ...]
    comparison: RunComparisonView | None


def build_run_history_views(
    run_rows: list[RunSummaryRow],
    module_rows: list[ModuleHistoryRow],
    comparisons: dict[str, RunComparisonRow],
) -> list[RunHistoryView]:
    """프로젝션 행들을 Run 단위 읽기 뷰로 조립한다(순수)."""
    modules_by_run: dict[str, list[ModuleHistoryView]] = {}
    for row in module_rows:
        modules_by_run.setdefault(row.run_id, []).append(
            ModuleHistoryView(
                module_id=row.module_id,
                name=row.module_name,
                status=row.status,
                message=row.message,
                duration_ms=row.duration_ms,
                current_url=row.current_url,
                artifacts=row.artifacts,
                started_at=row.started_at,
                ended_at=row.ended_at,
                ai_category=row.ai_category,
                ai_summary=row.ai_summary,
                ai_action=row.ai_action,
            )
        )
    views: list[RunHistoryView] = []
    for run in run_rows:
        comparison_row = comparisons.get(run.run_id)
        views.append(
            RunHistoryView(
                run_id=run.run_id,
                system_code=run.system_code,
                system_name=run.system_name,
                status=run.status,
                requested_at=run.requested_at,
                started_at=run.started_at,
                ended_at=run.ended_at,
                triggered_by=run.triggered_by,
                suite_id=run.suite_id,
                schedule_id=run.schedule_id,
                created_by_user_id=run.created_by_user_id,
                created_by_user_name=run.created_by_user_name,
                modules=tuple(modules_by_run.get(run.run_id, [])),
                comparison=RunComparisonView(
                    newly_failed=comparison_row.newly_failed,
                    recovered=comparison_row.recovered,
                    still_failing=comparison_row.still_failing,
                )
                if comparison_row is not None
                else None,
            )
        )
    return views
