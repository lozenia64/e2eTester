from __future__ import annotations

from app.core.enums import ModuleStatus
from app.core.models import Run, RunComparison
from app.core.status_labels import MODULE_ANOMALY_STATUSES, RUN_TERMINAL_OUTCOME_STATUSES


class RunComparator:
    """직전에 종료된 같은 시스템 Run 을 기준선으로 모듈 상태 변화를 계산하는 도메인 서비스.

    AI 분석·메일 발송과 달리 비교 결과는 Run 의 파생 필드(``comparison``)이며 종료 메일이
    이를 참조한다. 따라서 이벤트 구독자(비결정적 순서)로 빼지 않고, Run 종료(finalize)
    시점에 결정적으로 계산되도록 오케스트레이터에 주입한다(저장소 포트에만 의존).
    """

    def __init__(self, repository) -> None:
        self._repository = repository

    async def compute(self, run: Run) -> RunComparison:
        baseline: Run | None = None
        for other in await self._repository.list_runs():
            if other.run_id == run.run_id or other.system_code != run.system_code:
                continue
            if other.status not in RUN_TERMINAL_OUTCOME_STATUSES:
                continue
            if other.requested_at >= run.requested_at:
                continue
            if baseline is None or other.requested_at > baseline.requested_at:
                baseline = other

        if baseline is None:
            return RunComparison(has_baseline=False)

        baseline_status = {
            module.module_id: module.status
            for module in baseline.modules
            if module.status != ModuleStatus.SKIPPED
        }
        newly_failed: list[str] = []
        recovered: list[str] = []
        still_failing: list[str] = []
        for module in sorted(run.modules, key=lambda item: item.order):
            if module.status == ModuleStatus.SKIPPED:
                continue
            previous = baseline_status.get(module.module_id)
            if module.status in MODULE_ANOMALY_STATUSES:
                if previous in MODULE_ANOMALY_STATUSES:
                    still_failing.append(module.name)
                else:
                    newly_failed.append(module.name)
            elif module.status == ModuleStatus.PASSED and previous in MODULE_ANOMALY_STATUSES:
                recovered.append(module.name)

        return RunComparison(
            has_baseline=True,
            baseline_run_id=baseline.run_id,
            baseline_requested_at=baseline.requested_at,
            newly_failed=newly_failed,
            recovered=recovered,
            still_failing=still_failing,
        )
