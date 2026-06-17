from __future__ import annotations

import asyncio

from app.core.enums import RunStatus, SuiteStatus
from app.events.bus import EventBus, RunFinished, SuiteFinished
from app.notifications.run_completion_email import RunCompletionEmailNotifier


class EmailNotificationSubscriber:
    """Run/Suite 종료 이벤트를 받아 결과 메일을 발송하는 구독자.

    오케스트레이터에서 분리된 부수 관심사다. 메일 발송 정책(취소 Run 제외, Suite 소속
    Run 은 통합 메일로 갈음 등)도 이 구독자가 소유한다.
    """

    def __init__(self, notifier: RunCompletionEmailNotifier) -> None:
        self._notifier = notifier

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(RunFinished, self.on_run_finished)
        event_bus.subscribe(SuiteFinished, self.on_suite_finished)

    async def on_run_finished(self, event: RunFinished) -> None:
        run = event.run
        # 사용자가 취소한 Run 은 보내지 않고(PASSED/FAILED 만), Suite 소속 Run 은
        # Suite 종료 시 통합 메일 1통으로 갈음한다.
        if run.status not in {RunStatus.PASSED, RunStatus.FAILED} or run.suite_id:
            return
        snapshot = run.model_copy(deep=True)
        try:
            await asyncio.to_thread(self._notifier.send_run_completion, snapshot)
        except Exception as exc:
            print(f"[email] run={run.run_id} 종료 메일 발송 실패: {exc}")

    async def on_suite_finished(self, event: SuiteFinished) -> None:
        suite = event.suite
        if suite.status not in {SuiteStatus.PASSED, SuiteStatus.FAILED}:
            return
        try:
            await asyncio.to_thread(self._notifier.send_suite_completion, suite, event.runs)
        except Exception as exc:
            print(f"[email] suite={suite.suite_id} 종료 메일 발송 실패: {exc}")
