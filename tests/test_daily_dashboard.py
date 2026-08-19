"""일간 점검 대시보드 집계기 순수 단위 테스트.

브라우저·DB 없이 집계 규칙만 검증한다. `python3 -m pytest tests/` 로 실행한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.contexts.insights.application.daily_dashboard import (
    build_attention_items,
    build_daily_dashboard_from_projection,
    sort_systems_attention_first,
    system_attention_rank,
    system_summary_badge,
)
from app.core.enums import ModuleStatus
from app.core.system_models import ModuleDefinition, SystemDefinition
from tests.conftest import make_run_summary_row, make_status_row

GEN_AT = datetime(2026, 7, 8, 3, 0, tzinfo=UTC)


def _sysdef(code: str, module_ids: list[str], *, order: int = 100) -> SystemDefinition:
    return SystemDefinition(
        system_code=code,
        name=code.upper(),
        description="",
        display_order=order,
        modules=[
            ModuleDefinition(
                module_id=mid,
                system_code=code,
                name=mid,
                description="",
                group="g",
                order=i,
            )
            for i, mid in enumerate(module_ids)
        ],
    )


def test_only_one_dashboard_builder_exists():
    """레거시 빌더가 되살아나면 테스트가 프로덕션을 검증하지 못하게 된다."""
    import app.contexts.insights.application.daily_dashboard as mod

    assert not hasattr(mod, "build_daily_dashboard"), (
        "build_daily_dashboard 는 프로덕션에서 쓰이지 않는다. "
        "build_daily_dashboard_from_projection 만 남겨야 테스트가 실제 경로를 검증한다."
    )


def test_no_runs_marks_all_modules_not_inspected():
    systems = [_sysdef("hom", ["a", "b"])]
    data = build_daily_dashboard_from_projection(
        systems, [], [], generated_at=GEN_AT, date_label="2026-07-08"
    )

    assert data["date_label"] == "2026-07-08"
    sys = data["systems"][0]
    assert sys["module_total"] == 2
    assert sys["inspected"] == 0
    assert sys["pass_rate"] == 0
    assert sys["counts"]["not_inspected"] == 2
    assert sys["latest_run_id"] is None
    assert all(
        m["tone"] == "not_inspected" and m["status_label"] == "미점검" for m in sys["modules"]
    )
    assert data["totals"]["not_inspected"] == 2
    assert data["totals"]["systems_all_passed"] == 0


def test_latest_meaningful_status_wins_and_skips_non_results():
    systems = [_sysdef("hom", ["a", "b"])]
    # SKIPPED(결과 아님) 건너뛰고 이전 PASSED 를 채택하는 건 프로젝션 쿼리의 책임이므로,
    # 여기서는 프로젝션이 이미 해결한 최종 상태(a=ERROR, b=PASSED)를 그대로 픽스처로 준다.
    status_rows = [
        make_status_row(
            system_code="hom", module_id="a", last_status=ModuleStatus.ERROR, last_run_id="run_late"
        ),
        make_status_row(
            system_code="hom",
            module_id="b",
            last_status=ModuleStatus.PASSED,
            last_run_id="run_early",
        ),
    ]
    run_summaries = [
        make_run_summary_row(
            system_code="hom", run_id="run_early", requested_at=GEN_AT - timedelta(hours=2)
        ),
        make_run_summary_row(
            system_code="hom", run_id="run_late", requested_at=GEN_AT - timedelta(hours=1)
        ),
    ]
    data = build_daily_dashboard_from_projection(
        systems, status_rows, run_summaries, generated_at=GEN_AT, date_label="d"
    )

    sys = data["systems"][0]
    by_id = {m["module_id"]: m for m in sys["modules"]}
    assert by_id["a"]["status"] == str(ModuleStatus.ERROR)
    assert by_id["b"]["status"] == str(ModuleStatus.PASSED)
    assert sys["counts"]["error"] == 1
    assert sys["counts"]["passed"] == 1
    assert sys["pass_rate"] == 50
    # 최신 run_id 는 run_summaries 중 요청 시각이 가장 최근인 것(late)
    assert sys["latest_run_id"] == "run_late"


def test_recovered_flag_surfaces_on_module_view():
    """자동 복구된 모듈은 일간 현황 모듈 뷰에 recovered=True 로 노출되어야 한다."""
    systems = [_sysdef("hom", ["a"])]
    data = build_daily_dashboard_from_projection(
        systems,
        [
            make_status_row(
                system_code="hom",
                module_id="a",
                last_status=ModuleStatus.PASSED,
                last_run_id="run_recovered",
                recovered=True,
            )
        ],
        [make_run_summary_row(system_code="hom", run_id="run_recovered", requested_at=GEN_AT)],
        generated_at=GEN_AT,
        date_label="d",
    )

    module = data["systems"][0]["modules"][0]
    assert module["recovered"] is True


def test_recovered_flag_defaults_false_for_clean_module():
    systems = [_sysdef("hom", ["a"])]
    data = build_daily_dashboard_from_projection(
        systems,
        [make_status_row(system_code="hom", module_id="a", last_status=ModuleStatus.PASSED)],
        [make_run_summary_row(system_code="hom")],
        generated_at=GEN_AT,
        date_label="d",
    )

    module = data["systems"][0]["modules"][0]
    assert module["recovered"] is False


def test_totals_and_attention_sort_puts_anomaly_before_passed():
    systems = [
        _sysdef("b", ["m1"], order=200),
        _sysdef("a", ["m1", "m2"], order=100),
    ]
    status_rows = [
        make_status_row(system_code="a", module_id="m1", last_status=ModuleStatus.PASSED),
        make_status_row(system_code="a", module_id="m2", last_status=ModuleStatus.PASSED),
        make_status_row(system_code="b", module_id="m1", last_status=ModuleStatus.ANOMALY),
    ]
    run_summaries = [
        make_run_summary_row(system_code="a"),
        make_run_summary_row(system_code="b"),
    ]
    data = build_daily_dashboard_from_projection(
        systems, status_rows, run_summaries, generated_at=GEN_AT, date_label="d"
    )

    # 이상징후 시스템(b)이 전체 정상 시스템(a)보다 먼저
    assert [s["system_code"] for s in data["systems"]] == ["b", "a"]
    totals = data["totals"]
    assert totals["modules"] == 3
    assert totals["passed"] == 2
    assert totals["anomaly"] == 1
    assert totals["pass_rate"] == round(2 / 3 * 100)
    assert totals["systems_all_passed"] == 1
    assert len(data["attention"]) >= 1
    assert data["attention"][0]["system_code"] == "b"


def test_display_order_within_same_attention_rank():
    systems = [
        _sysdef("b", ["m1"], order=200),
        _sysdef("a", ["m1"], order=100),
    ]
    status_rows = [
        make_status_row(system_code="a", module_id="m1", last_status=ModuleStatus.PASSED),
        make_status_row(system_code="b", module_id="m1", last_status=ModuleStatus.PASSED),
    ]
    run_summaries = [
        make_run_summary_row(system_code="a"),
        make_run_summary_row(system_code="b"),
    ]
    data = build_daily_dashboard_from_projection(
        systems, status_rows, run_summaries, generated_at=GEN_AT, date_label="d"
    )
    assert [s["system_code"] for s in data["systems"]] == ["a", "b"]


def test_system_attention_rank_and_sort_helpers():
    views = [
        {
            "system_code": "ok",
            "display_order": 10,
            "module_total": 2,
            "counts": {
                "passed": 2,
                "error": 0,
                "anomaly": 0,
                "running": 0,
                "other": 0,
                "not_inspected": 0,
            },
            "modules": [],
        },
        {
            "system_code": "bad",
            "display_order": 20,
            "module_total": 1,
            "counts": {
                "passed": 0,
                "error": 1,
                "anomaly": 0,
                "running": 0,
                "other": 0,
                "not_inspected": 0,
            },
            "modules": [
                {
                    "module_id": "m1",
                    "name": "m1",
                    "bucket": "error",
                    "status_label": "점검실패",
                    "tone": "error",
                    "run_id": "r1",
                },
            ],
        },
    ]
    assert system_attention_rank(views[1]["counts"], module_total=1) > system_attention_rank(
        views[0]["counts"], module_total=2
    )
    sorted_codes = [s["system_code"] for s in sort_systems_attention_first(views)]
    assert sorted_codes == ["bad", "ok"]
    items = build_attention_items(views)
    assert items[0]["system_code"] == "bad"


@pytest.mark.spec("SPEC-UI-004", "AC-006")
def test_system_summary_badge_error_wins():
    view = {
        "counts": {
            "error": 1,
            "anomaly": 2,
            "running": 1,
            "other": 0,
            "not_inspected": 0,
            "passed": 0,
        },
        "module_total": 4,
    }
    badge = system_summary_badge(view)
    assert badge == {"label": "점검실패", "tone": "error"}


@pytest.mark.spec("SPEC-UI-004", "AC-006")
def test_system_summary_badge_all_passed():
    view = {
        "counts": {
            "error": 0,
            "anomaly": 0,
            "running": 0,
            "other": 0,
            "not_inspected": 0,
            "passed": 4,
        },
        "module_total": 4,
    }
    badge = system_summary_badge(view)
    assert badge == {"label": "정상", "tone": "passed"}


@pytest.mark.spec("SPEC-UI-004", "AC-006")
def test_system_summary_badge_anomaly_wins_over_running():
    view = {
        "counts": {
            "error": 0,
            "anomaly": 1,
            "running": 2,
            "other": 0,
            "not_inspected": 0,
            "passed": 1,
        },
        "module_total": 4,
    }
    badge = system_summary_badge(view)
    assert badge == {"label": "이상징후", "tone": "anomaly"}


@pytest.mark.spec("SPEC-UI-004", "AC-006")
def test_system_summary_badge_not_inspected_when_uninspected_modules():
    view = {
        "counts": {
            "error": 0,
            "anomaly": 0,
            "running": 0,
            "other": 0,
            "not_inspected": 2,
            "passed": 1,
        },
        "module_total": 3,
    }
    badge = system_summary_badge(view)
    assert badge == {"label": "미점검", "tone": "not_inspected"}


@pytest.mark.spec("SPEC-UI-004", "AC-006")
def test_system_summary_badge_not_inspected_when_zero_modules():
    view = {
        "counts": {
            "error": 0,
            "anomaly": 0,
            "running": 0,
            "other": 0,
            "not_inspected": 0,
            "passed": 0,
        },
        "module_total": 0,
    }
    badge = system_summary_badge(view)
    assert badge == {"label": "미점검", "tone": "not_inspected"}
