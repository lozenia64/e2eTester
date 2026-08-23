"""활동 피드 집계기 순수 단위 테스트.

브라우저·DB 없이 정렬·필터·포맷 규칙만 검증한다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.contexts.insights.application.daily_dashboard import build_activity_feed
from app.core.enums import ModuleStatus
from app.core.system_models import ModuleDefinition, SystemDefinition
from tests.conftest import make_status_row

KST = ZoneInfo("Asia/Seoul")


def _sysdef(code: str, module_ids: list[str]) -> SystemDefinition:
    return SystemDefinition(
        system_code=code,
        name=code.upper(),
        description="",
        display_order=100,
        modules=[
            ModuleDefinition(
                module_id=mid,
                system_code=code,
                name=f"{mid}-이름",
                description="",
                group="g",
                order=i,
            )
            for i, mid in enumerate(module_ids)
        ],
    )


def _row_at(hour: int, minute: int, *, module_id: str, status: ModuleStatus, **kw):
    row = make_status_row(system_code="hom", module_id=module_id, last_status=status, **kw)
    return type(row)(
        day_key=row.day_key,
        system_code=row.system_code,
        module_id=row.module_id,
        last_status=row.last_status,
        last_run_id=row.last_run_id,
        duration_ms=row.duration_ms,
        updated_at=datetime(2026, 8, 15, hour, minute, tzinfo=UTC),
        recovered=row.recovered,
    )


def test_sorts_by_updated_at_descending():
    systems = [_sysdef("hom", ["login", "search", "order"])]
    rows = [
        _row_at(1, 0, module_id="login", status=ModuleStatus.PASSED),
        _row_at(3, 0, module_id="search", status=ModuleStatus.PASSED),
        _row_at(2, 0, module_id="order", status=ModuleStatus.PASSED),
    ]
    feed = build_activity_feed(rows, systems, tz=KST)
    assert [item["module_id"] for item in feed] == ["search", "order", "login"]


def test_respects_limit():
    systems = [_sysdef("hom", ["a", "b", "c"])]
    rows = [
        _row_at(1, 0, module_id="a", status=ModuleStatus.PASSED),
        _row_at(2, 0, module_id="b", status=ModuleStatus.PASSED),
        _row_at(3, 0, module_id="c", status=ModuleStatus.PASSED),
    ]
    feed = build_activity_feed(rows, systems, tz=KST, limit=2)
    assert len(feed) == 2
    assert [item["module_id"] for item in feed] == ["c", "b"]


def test_formats_time_in_given_timezone():
    systems = [_sysdef("hom", ["login"])]
    # UTC 00:30 == KST 09:30
    rows = [_row_at(0, 30, module_id="login", status=ModuleStatus.PASSED)]
    feed = build_activity_feed(rows, systems, tz=KST)
    assert feed[0]["at"] == "09:30"
    assert feed[0]["at_iso"].startswith("2026-08-15T09:30")


def test_excludes_non_result_statuses():
    systems = [_sysdef("hom", ["a", "b", "c", "d"])]
    rows = [
        _row_at(1, 0, module_id="a", status=ModuleStatus.PENDING),
        _row_at(2, 0, module_id="b", status=ModuleStatus.QUEUED),
        _row_at(3, 0, module_id="c", status=ModuleStatus.SKIPPED),
        _row_at(4, 0, module_id="d", status=ModuleStatus.PASSED),
    ]
    feed = build_activity_feed(rows, systems, tz=KST)
    assert [item["module_id"] for item in feed] == ["d"]


def test_carries_label_tone_run_id_and_recovered():
    systems = [_sysdef("hom", ["login"])]
    rows = [
        _row_at(
            5,
            0,
            module_id="login",
            status=ModuleStatus.PASSED,
            last_run_id="run-42",
            recovered=True,
        )
    ]
    feed = build_activity_feed(rows, systems, tz=KST)
    item = feed[0]
    assert item["system_name"] == "HOM"
    assert item["module_name"] == "login-이름"
    assert item["status_label"] == "정상"
    assert item["tone"] == "passed"
    assert item["run_id"] == "run-42"
    assert item["recovered"] is True


def test_skips_rows_whose_module_is_not_in_registry():
    """레지스트리에서 모듈이 제거된 뒤 남은 과거 프로젝션 행은 조용히 버린다."""
    systems = [_sysdef("hom", ["login"])]
    rows = [_row_at(1, 0, module_id="deleted-module", status=ModuleStatus.PASSED)]
    assert build_activity_feed(rows, systems, tz=KST) == []


def test_empty_input_returns_empty_list():
    assert build_activity_feed([], [], tz=KST) == []
