"""인사이트 집계 빌더가 공유하는 순수 헬퍼(브라우저·DB·설정 접근 없음)."""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import TYPE_CHECKING

from app.core.enums import ModuleStatus
from app.core.status_labels import MODULE_ANOMALY_STATUSES, MODULE_ERROR_STATUSES

if TYPE_CHECKING:
    from app.core.models import Run, RunModule

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


def screenshot_url(module: RunModule) -> str | None:
    """모듈 아티팩트 중 스크린샷(final.png)의 서빙 URL. 없으면 ``None``."""
    for artifact in module.artifacts or []:
        if artifact.lower().endswith(".png"):
            return artifact
    return None


def module_kind(status: ModuleStatus) -> str:
    """이상건 대분류: ``error``(점검실패) / ``anomaly``(이상징후)."""
    if status in MODULE_ERROR_STATUSES:
        return "error"
    return "anomaly"


def module_occurred_at(run: Run, module: RunModule) -> datetime:
    """모듈 결과의 대표 시각(종료 → 시작 → Run 요청 순으로 폴백)."""
    return module.ended_at or module.started_at or run.ended_at or run.requested_at


def local_date_key(moment: datetime, tz: tzinfo) -> str:
    """UTC/naive 시각을 주어진 타임존의 ``YYYY-MM-DD`` 로 버킷팅한다."""
    if moment.tzinfo is None:
        from datetime import UTC

        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(tz).strftime("%Y-%m-%d")


def sort_runs_desc(runs: list[Run]) -> list[Run]:
    return sorted(runs, key=lambda r: r.requested_at, reverse=True)


def sort_runs_asc(runs: list[Run]) -> list[Run]:
    return sorted(runs, key=lambda r: r.requested_at)
