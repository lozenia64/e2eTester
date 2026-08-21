"""일간 리포트 메일 발송 — 수신자 해석 · 하루 한 통 보장 · 실패 처리.

발송 자체는 기존 ``GmailEmailSender``(tenacity 재시도 포함)를 그대로 쓴다.
첨부·인라인 이미지가 없으므로 메시지는 여기서 간단히 만든다 —
``run_completion_email`` 의 비공개 ``_build_email_message`` 를 임포트하지 않는다.
"""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Any, Protocol

from app.core.env_utils import resolve_env_value
from app.core.logging import get_logger
from app.notifications.daily_report import build_daily_report
from app.notifications.report_renderer import render_daily_report_html
from app.notifications.run_completion_email import GmailEmailSender, _parse_recipients

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)

RECIPIENTS_ENV = "E2E_EMAIL_DAILY_REPORT_RECIPIENTS"
DEDUP_SCOPE = "daily_report"


class _DedupStore(Protocol):
    def try_claim_sync(self, scope: str, entity_id: str) -> bool: ...

    def release_sync(self, scope: str, entity_id: str) -> None: ...


def resolve_daily_report_recipients(values: dict[str, str | None]) -> tuple[str, ...]:
    """파이프 구분 수신자 문자열 → 튜플. 기존 메일 수신자 형식과 같다."""
    raw = (resolve_env_value("E2E_EMAIL_DAILY_REPORT_RECIPIENTS", values) or "").strip()
    if not raw:
        return ()
    recipients, _invalid_entries = _parse_recipients(raw)
    return tuple(recipients)


def _build_message(*, subject: str, from_addr: str, html_body: str, plain_body: str):
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = from_addr
    message.attach(MIMEText(plain_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))
    return message


class DailyReportEmailService:
    def __init__(
        self,
        *,
        summary_queries: Any,
        dedup_store: _DedupStore,
        config: Any,
        recipients: tuple[str, ...],
        sender_factory: Callable[[Any], Any] = GmailEmailSender,
    ) -> None:
        self._summary_queries = summary_queries
        self._dedup_store = dedup_store
        self._config = config
        self._recipients = recipients
        self._sender_factory = sender_factory

    async def send_for(self, date_label: str) -> bool:
        """지정일 리포트를 보낸다. 실제로 보냈으면 True."""
        if not self._recipients:
            logger.info(
                "일간 리포트 수신자가 없어 발송하지 않음",
                log_event="daily_report.no_recipients",
                date_label=date_label,
            )
            return False

        if not self._dedup_store.try_claim_sync(DEDUP_SCOPE, date_label):
            logger.info(
                "일간 리포트가 이미 발송됨",
                log_event="daily_report.already_sent",
                date_label=date_label,
            )
            return False

        try:
            summary = await self._summary_queries.get_daily_summary(
                user_id=None,  # 리포트에 개인 기여분은 의미가 없다
                allowed_system_codes=None,  # 전사 리포트
                is_admin=False,
                date_label=date_label,
            )
            report = build_daily_report(summary, date_label=date_label)
            html = render_daily_report_html(report)
            subject = f"[E2E] {date_label} 점검 결과 — {report['headline']}"
            plain = f"{date_label} 점검 결과: {report['headline']}"

            message = _build_message(
                subject=subject,
                from_addr=self._config.gmail_account,
                html_body=html,
                plain_body=plain,
            )
        except Exception as exc:
            self._dedup_store.release_sync(DEDUP_SCOPE, date_label)
            logger.exception(
                "일간 리포트 준비 실패 — claim 해제 후 재시도 가능",
                log_event="daily_report.prepare_failed",
                date_label=date_label,
                error=str(exc),
            )
            return False

        try:
            self._sender_factory(self._config).send(message, list(self._recipients))
        except Exception as exc:
            # claim 을 해제하지 않는다 — 같은 날 실패 메일을 반복 시도하는 것보다
            # 하루를 건너뛰고 다음 날 다시 시도하는 편이 낫다(설계 §3.7).
            logger.exception(
                "일간 리포트 발송 실패 — 오늘은 건너뛴다",
                log_event="daily_report.send_failed",
                date_label=date_label,
                error=str(exc),
            )
            return False

        logger.info(
            "일간 리포트 발송",
            log_event="daily_report.sent",
            date_label=date_label,
            recipient_count=len(self._recipients),
        )
        return True
