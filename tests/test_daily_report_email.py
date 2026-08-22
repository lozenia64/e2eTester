"""일간 리포트 발송 — 수신자·중복 방어·실패 처리.

SMTP 는 스텁한다. 실제 발송은 테스트하지 않는다(docs/CI.md 의 "메일은 CI 밖").
"""

from __future__ import annotations

import smtplib
from typing import Any

import pytest

from app.notifications.daily_report_email import (
    DailyReportEmailService,
    resolve_daily_report_recipients,
)

SUMMARY: dict[str, Any] = {
    "cards": [
        {
            "key": "pass_rate",
            "label": "통과율",
            "value": 94,
            "unit": "%",
            "period": "오늘",
            "note": "34/36",
            "tone": "passed",
            "href": "",
            "estimated": False,
        },
    ],
    "systems": [
        {
            "system_code": "HOM",
            "system_name": "대표홈",
            "module_total": 6,
            "pass_rate": 100,
            "counts": {
                "passed": 6,
                "anomaly": 0,
                "error": 0,
                "running": 0,
                "other": 0,
                "not_inspected": 0,
            },
            "modules": [],
        },
    ],
    "totals": {
        "modules": 6,
        "passed": 6,
        "pass_rate": 100,
        "error": 0,
        "anomaly": 0,
        "running": 0,
        "not_inspected": 0,
    },
    "attention": [],
    "date_label": "2026-08-20",
    "generated_at": "2026-08-21T08:00:00+00:00",
}


class _Queries:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get_daily_summary(
        self, *, user_id, allowed_system_codes, is_admin=False, date_label=None
    ):
        self.calls.append(
            {
                "user_id": user_id,
                "allowed": allowed_system_codes,
                "is_admin": is_admin,
                "date_label": date_label,
            }
        )
        return SUMMARY


class _FailingQueries:
    async def get_daily_summary(self, **_kwargs):
        raise RuntimeError("summary unavailable")


class _Dedup:
    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.claims: list[tuple[str, str]] = []
        self.releases: list[tuple[str, str]] = []

    def try_claim_sync(self, scope: str, entity_id: str) -> bool:
        self.claims.append((scope, entity_id))
        return self.allow

    def release_sync(self, scope: str, entity_id: str) -> None:
        self.releases.append((scope, entity_id))


class _Sender:
    def __init__(self, config) -> None:
        self.config = config
        self.sent: list[list[str]] = []

    def send(self, message, recipients: list[str]) -> None:
        self.sent.append(list(recipients))


class _FailingSender(_Sender):
    def __init__(self, config, exc: Exception) -> None:
        super().__init__(config)
        self.exc = exc

    def send(self, message, recipients):
        raise self.exc


class _Config:
    gmail_account = "sender@test.local"
    gmail_app_password = "pw"
    smtp_host = "smtp.test"
    smtp_port = 465
    timeout_seconds = 5


def _service(*, dedup=None, sender_cls=_Sender, recipients=("a@test.local",), queries=None):
    holder: dict[str, Any] = {}

    def factory(config):
        holder["sender"] = sender_cls(config)
        return holder["sender"]

    service = DailyReportEmailService(
        summary_queries=queries or _Queries(),
        dedup_store=dedup or _Dedup(),
        config=_Config(),
        recipients=tuple(recipients),
        sender_factory=factory,
    )
    return service, holder


def test_recipients_parse_pipe_separated():
    values = {"E2E_EMAIL_DAILY_REPORT_RECIPIENTS": " a@x.com | b@x.com "}
    recipients, errors = resolve_daily_report_recipients(values)
    assert recipients == ("a@x.com", "b@x.com")
    assert errors == []


def test_recipients_empty_when_unset():
    assert resolve_daily_report_recipients({}) == ((), [])


def test_recipients_drop_blank_entries():
    values = {"E2E_EMAIL_DAILY_REPORT_RECIPIENTS": "a@x.com||b@x.com|"}
    recipients, errors = resolve_daily_report_recipients(values)
    assert recipients == ("a@x.com", "b@x.com")
    assert errors == []


def test_recipients_deduplicate_case_insensitive():
    values = {"E2E_EMAIL_DAILY_REPORT_RECIPIENTS": "a@x.com|A@x.com|a@x.com"}
    recipients, _errors = resolve_daily_report_recipients(values)
    assert recipients == ("a@x.com",)


def test_recipients_drop_invalid_entries():
    values = {"E2E_EMAIL_DAILY_REPORT_RECIPIENTS": "a@x.com|not-an-email|b@x.com"}
    recipients, _errors = resolve_daily_report_recipients(values)
    assert recipients == ("a@x.com", "b@x.com")


def test_invalid_entries_are_reported_not_silently_dropped():
    """오타 난 주소가 신호 없이 사라지면 그 사람만 리포트를 못 받는다.

    형제 리졸버(_resolve_operator_recipients·_resolve_recipient_map)는 잘못된 항목을
    오류 문자열로 돌려준다. 일간 리포트 경로만 버리고 있었다.
    """
    values = {"E2E_EMAIL_DAILY_REPORT_RECIPIENTS": "a@x.com|exec@company,com"}
    recipients, errors = resolve_daily_report_recipients(values)
    assert recipients == ("a@x.com",)
    assert len(errors) == 1
    assert "exec@company,com" in errors[0]
    assert "E2E_EMAIL_DAILY_REPORT_RECIPIENTS" in errors[0]


def test_every_invalid_entry_is_named():
    values = {"E2E_EMAIL_DAILY_REPORT_RECIPIENTS": "bad1|bad2|ok@x.com"}
    _recipients, errors = resolve_daily_report_recipients(values)
    assert "bad1" in errors[0]
    assert "bad2" in errors[0]


def test_parse_recipients_is_public_api():
    """소비자가 둘이 됐다 — 비공개 이름을 모듈 밖에서 임포트하지 않는다."""
    from app.notifications import run_completion_email

    assert hasattr(run_completion_email, "parse_recipients")
    recipients, invalid = run_completion_email.parse_recipients("a@x.com|nope")
    assert recipients == ["a@x.com"]
    assert invalid == ["nope"]


@pytest.mark.asyncio
async def test_sends_once_to_all_recipients():
    service, holder = _service(recipients=("a@x.com", "b@x.com"))
    assert await service.send_for("2026-08-20") is True
    assert holder["sender"].sent == [["a@x.com", "b@x.com"]]


@pytest.mark.asyncio
async def test_queries_the_requested_date_company_wide():
    queries = _Queries()
    service, _ = _service(queries=queries)
    await service.send_for("2026-08-20")
    assert queries.calls == [
        {"user_id": None, "allowed": None, "is_admin": False, "date_label": "2026-08-20"}
    ]


@pytest.mark.asyncio
async def test_no_recipients_means_no_send():
    service, holder = _service(recipients=())
    assert await service.send_for("2026-08-20") is False
    assert "sender" not in holder


@pytest.mark.asyncio
async def test_claim_is_scoped_to_the_date():
    dedup = _Dedup()
    service, _ = _service(dedup=dedup)
    await service.send_for("2026-08-20")
    assert dedup.claims == [("daily_report", "2026-08-20")]


@pytest.mark.asyncio
async def test_second_call_for_same_date_does_not_send():
    dedup = _Dedup(allow=False)
    service, holder = _service(dedup=dedup)
    assert await service.send_for("2026-08-20") is False
    assert "sender" not in holder


@pytest.mark.asyncio
async def test_pre_send_failure_releases_claim():
    dedup = _Dedup()
    service, holder = _service(dedup=dedup, queries=_FailingQueries())
    assert await service.send_for("2026-08-20") is False
    assert dedup.claims == [("daily_report", "2026-08-20")]
    assert dedup.releases == [("daily_report", "2026-08-20")]
    assert "sender" not in holder


@pytest.mark.asyncio
async def test_permanent_failure_keeps_the_claim():
    """인증 실패로 하루를 건너뛴다 — 같은 날 실패 메일을 반복 시도하지 않는다(설계 §3.7)."""
    dedup = _Dedup()

    def failing(config):
        return _FailingSender(config, smtplib.SMTPAuthenticationError(535, b"bad"))

    service = DailyReportEmailService(
        summary_queries=_Queries(),
        dedup_store=dedup,
        config=_Config(),
        recipients=("a@x.com",),
        sender_factory=failing,
    )
    assert await service.send_for("2026-08-20") is False
    assert dedup.releases == []


@pytest.mark.asyncio
async def test_permanent_failure_does_not_raise():
    """스케줄러 루프를 죽이지 않는다."""

    def failing(config):
        return _FailingSender(config, smtplib.SMTPAuthenticationError(535, b"bad"))

    service = DailyReportEmailService(
        summary_queries=_Queries(),
        dedup_store=_Dedup(),
        config=_Config(),
        recipients=("a@x.com",),
        sender_factory=failing,
    )
    await service.send_for("2026-08-20")  # 예외가 전파되면 테스트 실패
