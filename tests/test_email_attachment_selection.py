"""메일 본문 CID 인라인 스크린샷 선택 규칙 검증."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.core.enums import RunStatus
from app.core.run_models import Run
from app.notifications.run_completion_email import (
    EmailNotificationConfig,
    RunArtifact,
    RunCompletionEmailNotifier,
)


def _artifact(
    *, module_id: str, kind: str = "screenshot", system_code: str = "FP", seq: int = 1
) -> RunArtifact:
    return RunArtifact(
        module_id=module_id,
        module_name=module_id,
        order=10,
        seq=seq,
        kind=kind,
        path=Path("artifacts/run/final.png"),
        relative_path=f"artifacts/run/{module_id}/final.png",
        size_bytes=100,
        system_code=system_code,
        run_id="run_test",
    )


def test_run_email_content_includes_main_access_screenshot() -> None:
    config = EmailNotificationConfig(
        enabled=True,
        gmail_account="sender@gmail.com",
        gmail_app_password="app-password",
        recipients_by_system={"FP": ("user@company.com",)},
        operator_recipients=(),
        gemini_enabled=False,
        gemini_api_key=None,
        gemini_models=(),
    )
    notifier = RunCompletionEmailNotifier(config)
    run = Run(
        run_id="run_test",
        system_code="FP",
        system_name="FP",
        status=RunStatus.PASSED,
        requested_at=datetime.now(UTC),
        modules=[],
        selected_module_ids=[],
    )
    artifacts = [
        _artifact(module_id="fp.main.access", seq=1),
        _artifact(module_id="fp.identity.verify", seq=2),
    ]

    selection = notifier._select_email_content(run, artifacts)

    assert [item.artifact.module_id for item in selection.inline_screenshots] == [
        "fp.main.access",
        "fp.identity.verify",
    ]
    assert selection.log_attachments == []
