from __future__ import annotations

import asyncio

from app.core.status_labels import RUN_TERMINAL_OUTCOME_STATUSES, SUITE_TERMINAL_OUTCOME_STATUSES
from app.events.bus import EventBus, RunFinished, SuiteFinished
from app.notifications.run_completion_email import RunCompletionEmailNotifier
from app.storage.sqlite_email_notification_dedup import SqliteEmailNotificationDedupStore


class EmailNotificationSubscriber:
    """Run/Suite 종료 이벤트를 받아 결과 메일을 발송하는 구독자.

    오케스트레이터에서 분리된 부수 관심사다. 메일 발송 정책(취소 Run 제외, Suite 소속
    Run 은 통합 메일로 갈음, ERROR 는 운영자 수신 등)도 이 구독자가 소유한다.

    중복 방어의 최종 관문은 ``RunCompletionEmailNotifier`` 의 SQLite claim(SMTP 직전)이다.
    이 구독자는 이벤트를 notifier 로 위임만 한다.
    """

    def __init__(
        self,
        system_codes: list[str],
        *,
        dedup_store: SqliteEmailNotificationDedupStore | None = None,
    ) -> None:
        self._system_codes = system_codes
        self._dedup_store = dedup_store

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(RunFinished, self.on_run_finished)
        event_bus.subscribe(SuiteFinished, self.on_suite_finished)

    async def on_run_finished(self, event: RunFinished) -> None:
        run = event.run
        if run.status not in RUN_TERMINAL_OUTCOME_STATUSES or run.suite_id:
            return

        notifier = RunCompletionEmailNotifier.from_env(
            self._system_codes, dedup_store=self._dedup_store
        )
        if notifier is None:
            return

        snapshot = run.model_copy(deep=True)
        try:
            await asyncio.to_thread(notifier.send_run_completion, snapshot)
        except Exception as exc:
            print(f"[email] run={run.run_id} 종료 메일 발송 실패: {exc}")

    async def on_suite_finished(self, event: SuiteFinished) -> None:
        suite = event.suite
        if suite.status not in SUITE_TERMINAL_OUTCOME_STATUSES:
            return

        notifier = RunCompletionEmailNotifier.from_env(
            self._system_codes, dedup_store=self._dedup_store
        )
        if notifier is None:
            return

        try:
            await asyncio.to_thread(notifier.send_suite_completion, suite, event.runs)
        except Exception as exc:
            print(f"[email] suite={suite.suite_id} 종료 메일 발송 실패: {exc}")
