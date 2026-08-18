"""EmailNotificationSubscriber 중복 RunFinished 방어 테스트."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.notifications.infrastructure.sqlite_email_notification_dedup import (
    SqliteEmailNotificationDedupStore,
)
from app.notifications.run_completion_email import (
    EmailContentSelection,
    EmailNotificationConfig,
    GeminiPromptSelection,
    RunCompletionEmailBuilder,
    RunCompletionEmailNotifier,
    _build_email_context,
)
from app.platform.eventing.bus import EventBus, RunFinished
from app.platform.eventing.subscribers.email_notification import EmailNotificationSubscriber
from app.platform.eventing.support import SqliteDatabase, ensure_schema


def _passed_run(run_id: str = "run_email_dedup") -> Run:
    return Run(
        run_id=run_id,
        system_code="chbot",
        system_name="챗봇(모바일)",
        status=RunStatus.PASSED,
        requested_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="chbot.simple.auth",
                name="간편본인인증",
                group="auth",
                order=20,
                status=ModuleStatus.PASSED,
            )
        ],
        selected_module_ids=["chbot.simple.auth"],
    )


def _email_config() -> EmailNotificationConfig:
    return EmailNotificationConfig(
        enabled=True,
        gmail_account="sender@gmail.com",
        gmail_app_password="app-password",
        recipients_by_system={"chbot": ("user@company.com",)},
        operator_recipients=(),
        gemini_enabled=False,
        gemini_api_key=None,
        gemini_models=(),
    )


@pytest.mark.asyncio
async def test_four_subscribers_with_shared_store_send_once(tmp_path):
    db = SqliteDatabase(tmp_path / "email_sub_dedup.db")
    await ensure_schema(db)
    store = SqliteEmailNotificationDedupStore(db)
    notifier = RunCompletionEmailNotifier(_email_config(), dedup_store=store)
    mock_sender = MagicMock()
    notifier._sender = mock_sender
    run = _passed_run()

    subscribers = [EmailNotificationSubscriber(["chbot"], dedup_store=store) for _ in range(4)]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.platform.eventing.subscribers.email_notification.RunCompletionEmailNotifier.from_env",
            lambda *_args, **_kwargs: notifier,
        )
        await asyncio.gather(
            *(subscriber.on_run_finished(RunFinished(run=run)) for subscriber in subscribers)
        )

    mock_sender.send.assert_called_once()


@pytest.mark.asyncio
async def test_email_subscriber_sends_once_for_concurrent_run_finished(tmp_path):
    db = SqliteDatabase(tmp_path / "email_sub_concurrent.db")
    await ensure_schema(db)
    store = SqliteEmailNotificationDedupStore(db)
    notifier = RunCompletionEmailNotifier(_email_config(), dedup_store=store)
    mock_sender = MagicMock()
    send_started = threading.Event()
    release_send = threading.Event()

    def slow_send(_message, _recipients):
        send_started.set()
        release_send.wait()

    mock_sender.send.side_effect = slow_send
    notifier._sender = mock_sender
    run = _passed_run()
    subscriber = EmailNotificationSubscriber(["chbot"], dedup_store=store)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.platform.eventing.subscribers.email_notification.RunCompletionEmailNotifier.from_env",
            lambda *_args, **_kwargs: notifier,
        )
        tasks = [
            asyncio.create_task(subscriber.on_run_finished(RunFinished(run=run))) for _ in range(4)
        ]
        await asyncio.wait_for(asyncio.to_thread(send_started.wait), timeout=1.0)
        release_send.set()
        await asyncio.gather(*tasks)

    mock_sender.send.assert_called_once()


def test_event_bus_subscribe_is_idempotent():
    bus = EventBus()
    calls = 0

    async def handler(_event: RunFinished) -> None:
        nonlocal calls
        calls += 1

    bus.subscribe(RunFinished, handler)
    bus.subscribe(RunFinished, handler)
    assert bus.handler_count(RunFinished) == 1


def _plain_text_body(run: Run) -> str:
    empty_selection = EmailContentSelection(inline_screenshots=[], log_attachments=[], omitted=[])
    empty_gemini = GeminiPromptSelection(parts=[], omitted=[], included_labels=[])
    context = _build_email_context(run, empty_selection, empty_gemini)
    return RunCompletionEmailBuilder._build_plain_text(context)


def test_plain_text_body_includes_recovered_module_summary():
    run = _passed_run()
    run.modules[0].retry_count = 2
    run.modules[0].recovered = True

    text_body = _plain_text_body(run)

    assert "자동 복구된 모듈: 간편본인인증" in text_body


def test_plain_text_body_omits_recovered_summary_when_no_recovery():
    run = _passed_run()

    text_body = _plain_text_body(run)

    assert "자동 복구된 모듈" not in text_body
