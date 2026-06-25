"""GmailEmailSender SMTP 전송 재시도(tenacity) 단위 테스트.

네트워크 없이 ① 일시/영구 오류 분류 ② 일시 오류 재시도 후 성공 ③ 영구 오류는
재시도하지 않음 을 검증한다. tenacity 의 대기는 time.sleep 을 no-op 으로 만들어 즉시 진행.
"""

from __future__ import annotations

import smtplib
from email.message import Message

import pytest

from app.notifications.run_completion_email import (
    EMAIL_SEND_MAX_ATTEMPTS,
    EmailNotificationConfig,
    GmailEmailSender,
    _is_transient_smtp_error,
)


def _config() -> EmailNotificationConfig:
    return EmailNotificationConfig(
        gmail_account="sender@gmail.com",
        gmail_app_password="abcd efgh ijkl mnop",
        recipients_by_system={"hom": ("user@company.com",)},
        operator_recipients=(),
        gemini_api_key=None,
        gemini_models=(),
        gemini_enabled=False,
    )


def test_transient_predicate_classifies_errors():
    # 일시(재시도 대상)
    assert _is_transient_smtp_error(smtplib.SMTPServerDisconnected("끊김"))
    assert _is_transient_smtp_error(smtplib.SMTPConnectError(421, "busy"))
    assert _is_transient_smtp_error(TimeoutError())
    assert _is_transient_smtp_error(ConnectionResetError())
    # 영구(재시도 금지)
    assert not _is_transient_smtp_error(smtplib.SMTPAuthenticationError(535, b"bad creds"))
    assert not _is_transient_smtp_error(smtplib.SMTPRecipientsRefused({}))
    assert not _is_transient_smtp_error(smtplib.SMTPSenderRefused(550, b"no", "s@x.com"))
    assert not _is_transient_smtp_error(ValueError("무관한 오류"))


def test_send_retries_transient_error_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)  # tenacity 대기 즉시 통과
    attempts = {"n": 0}

    class _FakeSMTP:
        def __init__(self, *_a, **_k) -> None:
            attempts["n"] += 1
            if attempts["n"] < EMAIL_SEND_MAX_ATTEMPTS:
                raise smtplib.SMTPServerDisconnected("일시적 연결 끊김")

        def __enter__(self):
            return self

        def __exit__(self, *_a) -> bool:
            return False

        def login(self, *_a, **_k) -> None:
            pass

        def send_message(self, *_a, **_k) -> None:
            pass

    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    GmailEmailSender(_config()).send(Message(), ["user@company.com"])
    assert attempts["n"] == EMAIL_SEND_MAX_ATTEMPTS  # 두 번 실패 후 세 번째 성공


def test_send_does_not_retry_auth_error(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
    attempts = {"n": 0}

    class _FakeSMTP:
        def __init__(self, *_a, **_k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a) -> bool:
            return False

        def login(self, *_a, **_k) -> None:
            attempts["n"] += 1
            raise smtplib.SMTPAuthenticationError(535, b"bad creds")

        def send_message(self, *_a, **_k) -> None:
            pass

    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    with pytest.raises(smtplib.SMTPAuthenticationError):
        GmailEmailSender(_config()).send(Message(), ["user@company.com"])
    assert attempts["n"] == 1  # 영구 오류는 재시도하지 않음
