"""RunCompletionEmailNotifier SMTP 직전 dedup 관문 테스트."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.core.enums import RunStatus
from app.core.run_models import Run
from app.notifications.infrastructure.sqlite_email_notification_dedup import (
    SqliteEmailNotificationDedupStore,
)
from app.notifications.run_completion_email import (
    EmailNotificationConfig,
    RunCompletionEmailNotifier,
)
from app.platform.eventing.support import SqliteDatabase, ensure_schema


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


def _passed_run(run_id: str = "run_notifier_dedup") -> Run:
    return Run(
        run_id=run_id,
        system_code="chbot",
        system_name="챗봇(모바일)",
        status=RunStatus.PASSED,
        requested_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        modules=[],
        selected_module_ids=[],
    )


@pytest.mark.asyncio
async def test_notifier_sends_once_when_send_run_completion_called_four_times(tmp_path):
    db = SqliteDatabase(tmp_path / "notifier_dedup.db")
    await ensure_schema(db)
    store = SqliteEmailNotificationDedupStore(db)
    notifier = RunCompletionEmailNotifier(_email_config(), dedup_store=store)
    mock_sender = MagicMock()
    notifier._sender = mock_sender
    run = _passed_run()

    for _ in range(4):
        notifier.send_run_completion(run)

    mock_sender.send.assert_called_once()


@pytest.mark.asyncio
async def test_notifier_releases_claim_on_smtp_failure_and_allows_retry(tmp_path):
    db = SqliteDatabase(tmp_path / "notifier_retry.db")
    await ensure_schema(db)
    store = SqliteEmailNotificationDedupStore(db)
    notifier = RunCompletionEmailNotifier(_email_config(), dedup_store=store)
    mock_sender = MagicMock()
    mock_sender.send.side_effect = [RuntimeError("smtp down"), None]
    notifier._sender = mock_sender
    run = _passed_run()

    with pytest.raises(RuntimeError, match="smtp down"):
        notifier.send_run_completion(run)
    notifier.send_run_completion(run)

    assert mock_sender.send.call_count == 2
