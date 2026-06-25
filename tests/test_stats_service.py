"""StatsService 절감시간(초) 합산 단위 테스트.

Run 단위로 초→분 변환 시 내림(truncation)하지 않고, 초를 그대로 누적한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import ModuleDefinition, Run, RunModule, SystemDefinition
from app.orchestrator.stats_service import StatsService
from app.storage.run_repository import InMemoryRunRepository


class _FakeSuiteRepo:
    async def list_suites(self):
        return []


class _FakeRegistry:
    def __init__(self, systems: list[SystemDefinition]) -> None:
        self._systems = systems

    def list_systems(self) -> list[SystemDefinition]:
        return self._systems


def _module(module_id: str, *, status: ModuleStatus = ModuleStatus.PASSED) -> RunModule:
    return RunModule(
        module_id=module_id,
        name=module_id,
        group="g",
        order=0,
        status=status,
    )


def _passed_run(run_id: str, module_id: str) -> Run:
    return Run(
        run_id=run_id,
        system_code="hom",
        system_name="HOM",
        status=RunStatus.PASSED,
        requested_at=datetime.now(UTC),
        modules=[_module(module_id)],
        selected_module_ids=[module_id],
    )


async def test_saved_seconds_sums_without_per_run_truncation():
    """3 runs × 45s saved each = 135s total (not 0 from per-run // 60)."""
    module_id = "hom.login"
    registry = _FakeRegistry(
        [
            SystemDefinition(
                system_code="hom",
                name="HOM",
                description="",
                modules=[
                    ModuleDefinition(
                        module_id=module_id,
                        system_code="hom",
                        name="login",
                        description="",
                        group="auth",
                        order=0,
                        estimated_manual_seconds=45,
                    ),
                ],
            ),
        ]
    )
    run_repo = InMemoryRunRepository()
    for i in range(3):
        await run_repo.create_run(_passed_run(f"run_{i}", module_id))

    service = StatsService(
        run_repo=run_repo,
        suite_repo=_FakeSuiteRepo(),
        registry=registry,
    )
    stats = await service.get_usage_stats()

    assert len(stats.by_system) == 1
    assert stats.by_system[0].manual_seconds_saved == 135
    assert stats.by_user[0].manual_seconds_saved == 135
    assert stats.by_user[0].by_system[0].manual_seconds_saved == 135


async def test_usage_stats_includes_anomaly_excludes_error():
    module_id = "hom.login"
    registry = _FakeRegistry(
        [
            SystemDefinition(
                system_code="hom",
                name="HOM",
                description="",
                modules=[
                    ModuleDefinition(
                        module_id=module_id,
                        system_code="hom",
                        name="login",
                        description="",
                        group="auth",
                        order=0,
                        estimated_manual_seconds=30,
                    ),
                ],
            ),
        ]
    )
    run_repo = InMemoryRunRepository()

    def _run(run_id: str, status: RunStatus) -> Run:
        return Run(
            run_id=run_id,
            system_code="hom",
            system_name="HOM",
            status=status,
            requested_at=datetime.now(UTC),
            modules=[_module(module_id, status=ModuleStatus.PASSED)],
            selected_module_ids=[module_id],
        )

    await run_repo.create_run(_passed_run("run_passed", module_id))
    await run_repo.create_run(_run("run_anomaly", RunStatus.ANOMALY))
    await run_repo.create_run(_run("run_error", RunStatus.ERROR))

    service = StatsService(
        run_repo=run_repo,
        suite_repo=_FakeSuiteRepo(),
        registry=registry,
    )
    stats = await service.get_usage_stats()

    assert stats.total_runs == 2
    assert stats.by_system[0].runs == 2
