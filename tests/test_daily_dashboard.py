"""일간 점검 대시보드 집계기 순수 단위 테스트.

브라우저·DB 없이 집계 규칙만 검증한다. `python3 -m pytest tests/` 로 실행한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.contexts.insights.application.daily_dashboard import (
    build_attention_items,
    build_daily_dashboard,
    sort_systems_attention_first,
    system_attention_rank,
)
from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.core.system_models import ModuleDefinition, SystemDefinition

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


def _run(
    code: str, statuses: dict[str, ModuleStatus], *, at: datetime, status=RunStatus.PASSED
) -> Run:
    return Run(
        run_id=f"run_{code}_{at.timestamp()}",
        system_code=code,
        system_name=code.upper(),
        status=status,
        requested_at=at,
        modules=[
            RunModule(module_id=mid, name=mid, group="g", order=i, status=st)
            for i, (mid, st) in enumerate(statuses.items())
        ],
    )


def test_no_runs_marks_all_modules_not_inspected():
    systems = [_sysdef("hom", ["a", "b"])]
    data = build_daily_dashboard(systems, [], generated_at=GEN_AT, date_label="2026-07-08")

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
    early = _run(
        "hom", {"a": ModuleStatus.PASSED, "b": ModuleStatus.PASSED}, at=GEN_AT - timedelta(hours=2)
    )
    # 최신 Run 에서 b 는 SKIPPED(결과 아님) → 이전 Run 의 PASSED 로 채워져야 한다.
    late = _run(
        "hom", {"a": ModuleStatus.ERROR, "b": ModuleStatus.SKIPPED}, at=GEN_AT - timedelta(hours=1)
    )
    data = build_daily_dashboard(systems, [early, late], generated_at=GEN_AT, date_label="d")

    sys = data["systems"][0]
    by_id = {m["module_id"]: m for m in sys["modules"]}
    assert by_id["a"]["status"] == str(ModuleStatus.ERROR)  # 최신 Run 의 실패 채택
    assert by_id["b"]["status"] == str(ModuleStatus.PASSED)  # SKIPPED 건너뛰고 이전 PASSED
    assert sys["counts"]["error"] == 1
    assert sys["counts"]["passed"] == 1
    assert sys["pass_rate"] == 50
    # 최신 Run id 는 시간상 가장 최근(late)
    assert sys["latest_run_id"] == late.run_id


def test_totals_and_attention_sort_puts_anomaly_before_passed():
    systems = [
        _sysdef("b", ["m1"], order=200),
        _sysdef("a", ["m1", "m2"], order=100),
    ]
    runs = [
        _run("a", {"m1": ModuleStatus.PASSED, "m2": ModuleStatus.PASSED}, at=GEN_AT),
        _run("b", {"m1": ModuleStatus.ANOMALY}, at=GEN_AT),
    ]
    data = build_daily_dashboard(systems, runs, generated_at=GEN_AT, date_label="d")

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
    runs = [
        _run("a", {"m1": ModuleStatus.PASSED}, at=GEN_AT),
        _run("b", {"m1": ModuleStatus.PASSED}, at=GEN_AT),
    ]
    data = build_daily_dashboard(systems, runs, generated_at=GEN_AT, date_label="d")
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
