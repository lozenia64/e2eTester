from __future__ import annotations

from app.core.models import DashboardEvent, Run, RunModule


class RunEventPublisher:
    """Run 도메인 상태를 대시보드 WebSocket 이벤트로 변환·발행하는 표현 어댑터.

    이벤트 페이로드(``DashboardEvent``)의 모양은 오케스트레이션 로직이 아니라 표현 관심사다.
    상태머신(``RunService``)과 사후 보강 구독자(AI 실패 분석)가 동일한 이벤트 형태를 쓰도록
    한곳에 모아 중복을 없앤다.
    """

    def __init__(self, repository) -> None:
        self._repository = repository

    async def run_event(self, event_type: str, run: Run) -> None:
        await self._repository.publish(
            DashboardEvent(
                event_type=event_type,
                run_id=run.run_id,
                system_code=run.system_code,
                run_status=run.status,
                payload=run.model_dump(mode="json"),
            )
        )

    async def module_event(self, event_type: str, run: Run, module: RunModule) -> None:
        await self._repository.publish(
            DashboardEvent(
                event_type=event_type,
                run_id=run.run_id,
                system_code=run.system_code,
                run_status=run.status,
                payload={
                    "module": module.model_dump(mode="json"),
                    "run_status": run.status,
                },
            )
        )

    async def module_log(self, run: Run, module: RunModule, message: str) -> None:
        await self._repository.publish(
            DashboardEvent(
                event_type="module_log",
                run_id=run.run_id,
                system_code=run.system_code,
                run_status=run.status,
                payload={
                    "module_id": module.module_id,
                    "message": message,
                },
            )
        )
