from __future__ import annotations

import base64
import json
import mimetypes
import re
import smtplib
from dataclasses import dataclass
from datetime import UTC
from email.message import EmailMessage
from email.utils import parseaddr
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from app.ai.gemini_http import gemini_ssl_mode_detail, load_gemini_transport_settings, post_gemini_generate_content
from app.core.env_utils import (
    DEFAULT_ENV_FILE_PATH,
    env_flag,
    load_dotenv_file,
    resolve_env_value,
    resolve_env_with_source,
)
from app.core.enums import ModuleStatus, RunStatus
from app.core.models import Run
from app.runner.artifact_manager import ArtifactManager

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 465
KST = ZoneInfo("Asia/Seoul")
MAX_EMAIL_ATTACHMENT_BYTES = 17_500_000
MAX_GEMINI_ATTACHMENT_BYTES = 7_500_000
MAX_GEMINI_INLINE_IMAGE_BYTES = 2_500_000
MAX_GEMINI_LOG_BYTES = 180_000
HTML_FORBIDDEN_PATTERNS = (
    "<script",
    "<iframe",
    "<object",
    "<embed",
    "<form",
    "<input",
    "<button",
    "<textarea",
    "<link",
    "<meta",
    "<style",
    "javascript:",
    "data:text/html",
)


@dataclass(frozen=True)
class EmailNotificationStatus:
    state: str
    color: str
    title: str
    message: str
    detail: str
    model_value: str | None = None
    recipient_summary: str | None = None


@dataclass(frozen=True)
class EmailNotificationConfig:
    gmail_account: str
    gmail_app_password: str
    recipients_by_system: dict[str, tuple[str, ...]]
    gemini_api_key: str | None
    gemini_model: str
    gemini_enabled: bool
    gemini_verify_ssl: bool = True
    enabled: bool = True
    smtp_host: str = GMAIL_SMTP_HOST
    smtp_port: int = GMAIL_SMTP_PORT
    timeout_seconds: int = 20
    max_email_attachment_bytes: int = MAX_EMAIL_ATTACHMENT_BYTES
    max_gemini_attachment_bytes: int = MAX_GEMINI_ATTACHMENT_BYTES
    max_gemini_inline_image_bytes: int = MAX_GEMINI_INLINE_IMAGE_BYTES
    max_gemini_log_bytes: int = MAX_GEMINI_LOG_BYTES

    @classmethod
    def from_env(cls, system_codes: list[str]) -> "EmailNotificationConfig | None":
        dotenv_values = load_dotenv_file(DEFAULT_ENV_FILE_PATH)
        if not env_flag("E2E_EMAIL_ENABLED", dotenv_values, default=False):
            return None

        gmail_account = (resolve_env_value("E2E_EMAIL_GMAIL_ACCOUNT", dotenv_values) or "").strip()
        gmail_app_password = (resolve_env_value("E2E_EMAIL_GMAIL_APP_PASSWORD", dotenv_values) or "").strip()
        recipients_by_system, recipient_errors = _resolve_recipient_map(system_codes, dotenv_values)
        if not _gmail_account_looks_valid(gmail_account) or not _gmail_app_password_looks_valid(gmail_app_password):
            return None
        if recipient_errors:
            return None

        gemini_model = _resolve_gemini_model(dotenv_values)
        gemini_api_key = (resolve_env_value("GEMINI_API_KEY", dotenv_values) or "").strip()
        transport_settings = load_gemini_transport_settings(dotenv_values)
        gemini_enabled = _api_key_looks_valid(gemini_api_key) and _model_looks_valid(gemini_model)
        return cls(
            gmail_account=gmail_account,
            gmail_app_password=gmail_app_password,
            recipients_by_system=recipients_by_system,
            gemini_api_key=gemini_api_key if gemini_enabled else None,
            gemini_model=gemini_model,
            gemini_enabled=gemini_enabled,
            gemini_verify_ssl=transport_settings.verify_ssl,
        )

    @classmethod
    def inspect_env_status(cls, system_codes: list[str]) -> EmailNotificationStatus:
        dotenv_values = load_dotenv_file(DEFAULT_ENV_FILE_PATH)
        transport_settings = load_gemini_transport_settings(dotenv_values)
        enabled_raw, enabled_source = resolve_env_with_source("E2E_EMAIL_ENABLED", dotenv_values)
        if enabled_raw is None:
            return EmailNotificationStatus(
                state="missing",
                color="red",
                title="메일 알림 꺼짐",
                message="E2E_EMAIL_ENABLED 값이 없습니다.",
                detail=(
                    "터미널 환경 변수나 .env 파일에 E2E_EMAIL_ENABLED=true 를 설정해야 합니다. "
                    f"{gemini_ssl_mode_detail(transport_settings)}"
                ),
            )

        enabled = enabled_raw.strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return EmailNotificationStatus(
                state="disabled",
                color="orange",
                title="메일 알림 비활성",
                message=f"E2E_EMAIL_ENABLED={enabled_raw} 으로 설정되어 있습니다.",
                detail=(
                    f"현재 값은 {enabled_source or 'unknown'} 에서 읽혔습니다. 메일 알림을 쓰려면 true 로 바꿔야 합니다. "
                    f"{gemini_ssl_mode_detail(transport_settings)}"
                ),
            )

        gmail_account, gmail_account_source = resolve_env_with_source("E2E_EMAIL_GMAIL_ACCOUNT", dotenv_values)
        gmail_app_password, gmail_app_password_source = resolve_env_with_source("E2E_EMAIL_GMAIL_APP_PASSWORD", dotenv_values)
        recipients_by_system, recipient_errors = _resolve_recipient_map(system_codes, dotenv_values)
        errors: list[str] = []
        if not _gmail_account_looks_valid(gmail_account or ""):
            errors.append("E2E_EMAIL_GMAIL_ACCOUNT 값이 비어 있거나 Gmail 주소 형식이 아닙니다.")
        if not _gmail_app_password_looks_valid(gmail_app_password or ""):
            errors.append("E2E_EMAIL_GMAIL_APP_PASSWORD 값이 없거나 placeholder 값입니다.")
        errors.extend(recipient_errors)
        if errors:
            return EmailNotificationStatus(
                state="invalid",
                color="yellow",
                title="메일 알림 설정 필요",
                message="메일 발송 설정이 유효하지 않습니다.",
                detail=" ".join(errors + [gemini_ssl_mode_detail(transport_settings)]),
                recipient_summary=_recipient_summary(recipients_by_system),
            )

        gemini_model = _resolve_gemini_model(dotenv_values)
        gemini_api_key, gemini_api_key_source = resolve_env_with_source("GEMINI_API_KEY", dotenv_values)
        gemini_enabled = _api_key_looks_valid(gemini_api_key or "") and _model_looks_valid(gemini_model)
        if not gemini_enabled:
            return EmailNotificationStatus(
                state="degraded",
                color="yellow",
                title="메일 알림 부분 활성",
                message="메일 발송은 가능하지만 Gemini HTML 생성 설정이 유효하지 않습니다.",
                detail=(
                    f"발신 계정은 {gmail_account_source or 'unknown'}, 앱 비밀번호는 {gmail_app_password_source or 'unknown'} 에서 읽혔습니다. "
                    f"Gemini API 키는 {gemini_api_key_source or 'missing'}, 모델은 {_resolve_gemini_model_source(dotenv_values)} 에서 읽혔습니다. "
                    f"이 경우 기본 HTML 템플릿으로 메일을 보냅니다. {gemini_ssl_mode_detail(transport_settings)}"
                ),
                model_value=gemini_model,
                recipient_summary=_recipient_summary(recipients_by_system),
            )

        return EmailNotificationStatus(
            state="valid",
            color="blue",
            title="메일 알림 활성",
            message="메일 알림 기능이 활성화되어 있고 Gmail/Gemini 설정도 유효합니다.",
            detail=(
                f"발신 계정은 {gmail_account_source or 'unknown'}, Gemini API 키는 {gemini_api_key_source or 'unknown'}, "
                f"모델은 {_resolve_gemini_model_source(dotenv_values)} 에서 읽혔습니다. "
                f"{gemini_ssl_mode_detail(transport_settings)}"
            ),
            model_value=gemini_model,
            recipient_summary=_recipient_summary(recipients_by_system),
        )


@dataclass(frozen=True)
class RunArtifact:
    module_id: str
    module_name: str
    order: int
    kind: str
    path: Path
    relative_path: str
    size_bytes: int

    @property
    def attachment_name(self) -> str:
        safe_module_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.module_id)
        return f"{safe_module_id}-{self.path.name}"


@dataclass(frozen=True)
class OmittedArtifact:
    relative_path: str
    reason: str


@dataclass(frozen=True)
class AttachmentSelection:
    included: list[RunArtifact]
    omitted: list[OmittedArtifact]
    total_bytes: int


@dataclass(frozen=True)
class GeminiPromptSelection:
    parts: list[dict]
    omitted: list[OmittedArtifact]
    included_labels: list[str]


class GmailEmailSender:
    def __init__(self, config: EmailNotificationConfig) -> None:
        self._config = config

    def send(self, message: EmailMessage, recipients: list[str]) -> None:
        with smtplib.SMTP_SSL(self._config.smtp_host, self._config.smtp_port, timeout=self._config.timeout_seconds) as smtp:
            smtp.login(self._config.gmail_account, self._normalize_password(self._config.gmail_app_password))
            smtp.send_message(message, to_addrs=recipients)

    @staticmethod
    def _normalize_password(raw_password: str) -> str:
        return re.sub(r"\s+", "", raw_password)


class GeminiEmailHtmlComposer:
    def __init__(self, api_key: str, model: str, timeout_seconds: int = 20, verify_ssl: bool = True) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._endpoint = "https://generativelanguage.googleapis.com/v1beta"
        self._verify_ssl = verify_ssl

    def compose(self, context: dict, gemini_parts: list[dict]) -> str:
        prompt = self._build_prompt(context)
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}, *gemini_parts],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "html": {
                            "type": "STRING",
                        }
                    },
                    "required": ["html"],
                },
            },
        }
        response_json = self._post_generate_content(payload)
        parsed = self._extract_response_json(response_json)
        if parsed is None:
            raise RuntimeError("Gemini HTML 응답을 JSON으로 파싱하지 못했습니다.")
        html = str(parsed.get("html") or "").strip()
        if not _html_looks_safe(html):
            raise RuntimeError("Gemini HTML 응답이 Gmail용 안전 규칙을 만족하지 않습니다.")
        return html

    def _build_prompt(self, context: dict) -> str:
        prompt_context = {
            "run": context["run"],
            "module_summary": context["module_summary"],
            "failed_modules": context["failed_modules"],
            "email_attachment_summary": context["email_attachment_summary"],
            "gemini_input_summary": context["gemini_input_summary"],
        }
        return "\n".join(
            [
                "당신은 한국어 Gmail HTML 이메일 작성기다.",
                "아래 JSON을 바탕으로 Gmail에서 바로 렌더링 가능한 HTML 본문 조각만 작성하라.",
                "반드시 div/table/p/h2/ul/li/span 정도의 안전한 태그만 사용하고 모든 스타일은 inline style 로 작성하라.",
                "script, style, iframe, form, 외부 이미지, 외부 CSS, 외부 링크를 사용하지 마라.",
                "개인정보(이름, 생년월일, 전화번호, OTP)를 새로 추론하거나 노출하지 마라.",
                "성공이면 차분한 완료 메일, 실패면 핵심 실패 모듈과 다음 조치를 강조하라.",
                "첨부 누락이 있으면 별도 경고 박스를 넣어라.",
                "응답은 JSON 하나만 반환하고 html 필드에 HTML 문자열을 넣어라.",
                json.dumps(prompt_context, ensure_ascii=False, indent=2),
            ]
        )

    def _post_generate_content(self, payload: dict) -> dict:
        return post_gemini_generate_content(
            api_key=self._api_key,
            model=self._model,
            payload=payload,
            timeout_seconds=self._timeout_seconds,
            verify_ssl=self._verify_ssl,
            endpoint=self._endpoint,
        )

    @staticmethod
    def _extract_response_json(response_json: dict) -> dict | None:
        candidates = response_json.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                text = part.get("text")
                if not text:
                    continue
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue
        return None


class RunCompletionEmailBuilder:
    def __init__(self, config: EmailNotificationConfig) -> None:
        self._config = config
        self._composer = (
            GeminiEmailHtmlComposer(
                config.gemini_api_key,
                config.gemini_model,
                timeout_seconds=config.timeout_seconds,
                verify_ssl=config.gemini_verify_ssl,
            )
            if config.gemini_enabled and config.gemini_api_key
            else None
        )

    def build(
        self,
        run: Run,
        recipients: list[str],
        email_selection: AttachmentSelection,
        gemini_selection: GeminiPromptSelection,
    ) -> EmailMessage:
        context = _build_email_context(run, email_selection, gemini_selection)
        html_body = self._build_html_body(context, gemini_selection.parts)
        text_body = self._build_plain_text(context)

        message = EmailMessage()
        message["Subject"] = _build_subject(run)
        message["From"] = self._config.gmail_account
        message["To"] = "undisclosed-recipients:;"
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

        for artifact in email_selection.included:
            mime_type = mimetypes.guess_type(artifact.path.name)[0] or "application/octet-stream"
            maintype, subtype = mime_type.split("/", 1)
            message.add_attachment(
                artifact.path.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                filename=artifact.attachment_name,
            )
        return message

    def _build_html_body(self, context: dict, gemini_parts: list[dict]) -> str:
        if self._composer is None:
            return self._build_fallback_html(context)
        try:
            return self._composer.compose(context, gemini_parts)
        except Exception as exc:
            print(f"[email] Gemini HTML 생성 실패: {exc}")
            return self._build_fallback_html(context)

    @staticmethod
    def _build_plain_text(context: dict) -> str:
        run_info = context["run"]
        lines = [
            f"[E2E] {run_info['system_code']} 테스트 {run_info['status_label']}",
            f"Run ID: {run_info['run_id']}",
            f"시스템: {run_info['system_name']}",
            f"요청 시각(KST): {run_info['requested_at_kst']}",
            f"시작 시각(KST): {run_info['started_at_kst']}",
            f"종료 시각(KST): {run_info['ended_at_kst']}",
            f"총 소요시간: {run_info['duration_text']}",
            "",
            "모듈 요약:",
        ]
        for status, count in context["module_summary"].items():
            lines.append(f"- {status}: {count}")
        if context["failed_modules"]:
            lines.append("")
            lines.append("실패 모듈:")
            for failed_module in context["failed_modules"]:
                lines.append(
                    f"- {failed_module['module_id']} ({failed_module['module_name']}): {failed_module['message']}"
                )
                if failed_module["analysis_summary"]:
                    lines.append(f"  요약: {failed_module['analysis_summary']}")
                if failed_module["recommended_action"]:
                    lines.append(f"  권장 조치: {failed_module['recommended_action']}")
        attachment_summary = context["email_attachment_summary"]
        lines.extend(
            [
                "",
                f"첨부 파일: 스크린샷 {attachment_summary['screenshot_count']}건, 로그 {attachment_summary['log_count']}건",
            ]
        )
        if attachment_summary["omitted"]:
            lines.append("메일 첨부에서 제외된 파일:")
            for omitted in attachment_summary["omitted"]:
                lines.append(f"- {omitted['path']}: {omitted['reason']}")
        if context["gemini_input_summary"]["omitted"]:
            lines.append("Gemini 본문 생성에서 제외된 파일:")
            for omitted in context["gemini_input_summary"]["omitted"]:
                lines.append(f"- {omitted['path']}: {omitted['reason']}")
        return "\n".join(lines)

    @staticmethod
    def _build_fallback_html(context: dict) -> str:
        run_info = context["run"]
        tone_color = "#17804b" if run_info["status"] == RunStatus.PASSED.value else "#c44536"
        failed_items = "".join(
            [
                (
                    "<li style=\"margin-bottom:12px;\">"
                    f"<strong>{escape(item['module_name'])}</strong> "
                    f"(<code>{escape(item['module_id'])}</code>)<br>"
                    f"<span>{escape(item['message'])}</span>"
                    + (
                        f"<br><span>AI 요약: {escape(item['analysis_summary'])}</span>"
                        if item["analysis_summary"]
                        else ""
                    )
                    + (
                        f"<br><span>권장 조치: {escape(item['recommended_action'])}</span>"
                        if item["recommended_action"]
                        else ""
                    )
                    + "</li>"
                )
                for item in context["failed_modules"]
            ]
        )
        omitted_sections: list[str] = []
        for section_title, omitted_entries in (
            ("메일 첨부에서 제외된 파일", context["email_attachment_summary"]["omitted"]),
            ("Gemini HTML 생성에서 제외된 파일", context["gemini_input_summary"]["omitted"]),
        ):
            if not omitted_entries:
                continue
            items = "".join(
                f"<li><code>{escape(entry['path'])}</code> - {escape(entry['reason'])}</li>" for entry in omitted_entries
            )
            omitted_sections.append(
                (
                    "<div style=\"margin-top:16px;padding:14px 16px;border-radius:14px;"
                    "background:#fff6dd;border:1px solid rgba(196,127,25,0.25);\">"
                    f"<strong style=\"display:block;margin-bottom:8px;\">{escape(section_title)}</strong>"
                    f"<ul style=\"margin:0;padding-left:18px;\">{items}</ul>"
                    "</div>"
                )
            )

        module_rows = "".join(
            f"<li><strong>{escape(status)}</strong>: {count}</li>"
            for status, count in context["module_summary"].items()
        )
        failed_section = (
            "<div style=\"margin-top:20px;\">"
            "<h3 style=\"margin:0 0 10px;font-size:16px;\">실패 모듈</h3>"
            f"<ul style=\"margin:0;padding-left:18px;\">{failed_items}</ul>"
            "</div>"
            if failed_items
            else ""
        )
        return (
            "<div style=\"font-family:Arial,'Noto Sans KR',sans-serif;color:#1e1a16;line-height:1.6;\">"
            "<div style=\"max-width:760px;margin:0 auto;padding:24px;background:#fffaf4;border:1px solid rgba(30,26,22,0.08);"
            "border-radius:20px;\">"
            f"<h2 style=\"margin:0 0 12px;font-size:24px;color:{tone_color};\">"
            f"[E2E] {escape(run_info['system_code'])} 테스트 {escape(run_info['status_label'])}</h2>"
            f"<p style=\"margin:0 0 18px;\">{escape(run_info['system_name'])} 테스트가 {escape(run_info['status_label'])} 상태로 종료되었습니다.</p>"
            "<table style=\"width:100%;border-collapse:collapse;font-size:14px;\">"
            f"<tr><td style=\"padding:6px 0;color:#665f57;\">Run ID</td><td style=\"padding:6px 0;\"><code>{escape(run_info['run_id'])}</code></td></tr>"
            f"<tr><td style=\"padding:6px 0;color:#665f57;\">요청 시각</td><td style=\"padding:6px 0;\">{escape(run_info['requested_at_kst'])}</td></tr>"
            f"<tr><td style=\"padding:6px 0;color:#665f57;\">시작 시각</td><td style=\"padding:6px 0;\">{escape(run_info['started_at_kst'])}</td></tr>"
            f"<tr><td style=\"padding:6px 0;color:#665f57;\">종료 시각</td><td style=\"padding:6px 0;\">{escape(run_info['ended_at_kst'])}</td></tr>"
            f"<tr><td style=\"padding:6px 0;color:#665f57;\">총 소요시간</td><td style=\"padding:6px 0;\">{escape(run_info['duration_text'])}</td></tr>"
            "</table>"
            "<div style=\"margin-top:20px;\">"
            "<h3 style=\"margin:0 0 10px;font-size:16px;\">모듈 요약</h3>"
            f"<ul style=\"margin:0;padding-left:18px;\">{module_rows}</ul>"
            "</div>"
            f"{failed_section}"
            "<div style=\"margin-top:20px;padding:14px 16px;border-radius:14px;background:#f6f3ef;\">"
            "<strong style=\"display:block;margin-bottom:8px;\">첨부 요약</strong>"
            f"<div>스크린샷 {context['email_attachment_summary']['screenshot_count']}건 / "
            f"로그 {context['email_attachment_summary']['log_count']}건</div>"
            "</div>"
            + "".join(omitted_sections)
            + "</div></div>"
        )


class RunCompletionEmailNotifier:
    def __init__(self, config: EmailNotificationConfig) -> None:
        self._config = config
        self._artifact_manager = ArtifactManager()
        self._builder = RunCompletionEmailBuilder(config)
        self._sender = GmailEmailSender(config)

    @classmethod
    def from_env(cls, system_codes: list[str]) -> "RunCompletionEmailNotifier | None":
        config = EmailNotificationConfig.from_env(system_codes)
        if config is None:
            return None
        return cls(config)

    @classmethod
    def inspect_env_status(cls, system_codes: list[str]) -> EmailNotificationStatus:
        return EmailNotificationConfig.inspect_env_status(system_codes)

    def send_run_completion(self, run: Run) -> None:
        recipients = list(self._config.recipients_by_system.get(run.system_code, ()))
        if not recipients:
            raise RuntimeError(f"메일 수신자를 찾지 못했습니다: {run.system_code}")

        artifacts = self._collect_artifacts(run)
        email_selection = self._select_email_attachments(run, artifacts)
        gemini_selection = self._select_gemini_prompt_inputs(run, artifacts)
        message = self._builder.build(run, recipients, email_selection, gemini_selection)
        self._sender.send(message, recipients)
        print(
            f"[email] run={run.run_id} recipients={len(recipients)} "
            f"attachments={len(email_selection.included)} status={run.status}"
        )

    def _collect_artifacts(self, run: Run) -> list[RunArtifact]:
        collected: list[RunArtifact] = []
        seen_paths: set[str] = set()
        for module in sorted(run.modules, key=lambda item: item.order):
            for relative_path in module.artifacts:
                path = self._artifact_manager.path_from_relative(relative_path)
                if not path.exists() or not path.is_file():
                    continue
                resolved = path.as_posix()
                if resolved in seen_paths:
                    continue
                kind = _artifact_kind(path)
                if kind is None:
                    continue
                seen_paths.add(resolved)
                collected.append(
                    RunArtifact(
                        module_id=module.module_id,
                        module_name=module.name,
                        order=module.order,
                        kind=kind,
                        path=path,
                        relative_path=relative_path,
                        size_bytes=path.stat().st_size,
                    )
                )
        return collected

    def _select_email_attachments(self, run: Run, artifacts: list[RunArtifact]) -> AttachmentSelection:
        wanted_kinds = _wanted_kinds(run)
        included: list[RunArtifact] = []
        omitted: list[OmittedArtifact] = []
        total_bytes = 0
        for artifact in artifacts:
            if artifact.kind not in wanted_kinds:
                continue
            if total_bytes + artifact.size_bytes > self._config.max_email_attachment_bytes:
                omitted.append(
                    OmittedArtifact(
                        relative_path=artifact.relative_path,
                        reason=f"Gmail 첨부 한도({self._config.max_email_attachment_bytes} bytes)를 초과합니다.",
                    )
                )
                continue
            included.append(artifact)
            total_bytes += artifact.size_bytes
        return AttachmentSelection(included=included, omitted=omitted, total_bytes=total_bytes)

    def _select_gemini_prompt_inputs(self, run: Run, artifacts: list[RunArtifact]) -> GeminiPromptSelection:
        wanted_kinds = _wanted_kinds(run)
        parts: list[dict] = []
        omitted: list[OmittedArtifact] = []
        included_labels: list[str] = []
        total_bytes = 0

        for artifact in artifacts:
            if artifact.kind not in wanted_kinds:
                continue

            if artifact.kind == "screenshot":
                if artifact.size_bytes > self._config.max_gemini_inline_image_bytes:
                    omitted.append(
                        OmittedArtifact(
                            relative_path=artifact.relative_path,
                            reason=f"이미지 파일이 Gemini inline 한도({self._config.max_gemini_inline_image_bytes} bytes)를 초과합니다.",
                        )
                    )
                    continue
                if total_bytes + artifact.size_bytes > self._config.max_gemini_attachment_bytes:
                    omitted.append(
                        OmittedArtifact(
                            relative_path=artifact.relative_path,
                            reason=f"Gemini 입력 한도({self._config.max_gemini_attachment_bytes} bytes)를 초과합니다.",
                        )
                    )
                    continue
                mime_type = mimetypes.guess_type(artifact.path.name)[0] or "image/png"
                parts.append(
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(artifact.path.read_bytes()).decode("ascii"),
                        }
                    }
                )
                included_labels.append(f"image:{artifact.relative_path}")
                total_bytes += artifact.size_bytes
                continue

            log_bytes = min(artifact.size_bytes, self._config.max_gemini_log_bytes)
            if total_bytes + log_bytes > self._config.max_gemini_attachment_bytes:
                omitted.append(
                    OmittedArtifact(
                        relative_path=artifact.relative_path,
                        reason=f"Gemini 입력 한도({self._config.max_gemini_attachment_bytes} bytes)를 초과합니다.",
                    )
                )
                continue
            log_text = artifact.path.read_text(encoding="utf-8", errors="ignore")
            if len(log_text.encode("utf-8")) > self._config.max_gemini_log_bytes:
                log_text = log_text.encode("utf-8")[-self._config.max_gemini_log_bytes :].decode("utf-8", errors="ignore")
                log_text = "[truncated_tail]\n" + log_text.lstrip()
            parts.append({"text": f"[execution_log]\npath={artifact.relative_path}\n{log_text}"})
            included_labels.append(f"log:{artifact.relative_path}")
            total_bytes += min(len(log_text.encode("utf-8")), self._config.max_gemini_log_bytes)

        return GeminiPromptSelection(parts=parts, omitted=omitted, included_labels=included_labels)


def _build_subject(run: Run) -> str:
    status_label = "테스트 완료" if run.status == RunStatus.PASSED else "테스트 중단"
    return f"[E2E][{run.system_code.upper()}][{run.status.value}] {run.run_id} {status_label}"


def _build_email_context(run: Run, email_selection: AttachmentSelection, gemini_selection: GeminiPromptSelection) -> dict:
    module_summary = _module_status_counts(run)
    failed_modules = []
    for module in sorted(run.modules, key=lambda item: item.order):
        if module.status != ModuleStatus.FAILED:
            continue
        failed_modules.append(
            {
                "module_id": module.module_id,
                "module_name": module.name,
                "message": module.message,
                "analysis_summary": module.failure_analysis.user_summary if module.failure_analysis else "",
                "recommended_action": module.failure_analysis.recommended_action if module.failure_analysis else "",
            }
        )

    return {
        "run": {
            "run_id": run.run_id,
            "system_code": run.system_code.upper(),
            "system_name": run.system_name,
            "status": run.status.value,
            "status_label": "성공" if run.status == RunStatus.PASSED else "실패",
            "requested_at_kst": _format_datetime(run.requested_at),
            "started_at_kst": _format_datetime(run.started_at),
            "ended_at_kst": _format_datetime(run.ended_at),
            "duration_text": _format_duration(run),
        },
        "module_summary": module_summary,
        "failed_modules": failed_modules,
        "email_attachment_summary": {
            "screenshot_count": sum(1 for artifact in email_selection.included if artifact.kind == "screenshot"),
            "log_count": sum(1 for artifact in email_selection.included if artifact.kind == "log"),
            "omitted": [
                {"path": item.relative_path, "reason": item.reason}
                for item in email_selection.omitted
            ],
        },
        "gemini_input_summary": {
            "included": list(gemini_selection.included_labels),
            "omitted": [
                {"path": item.relative_path, "reason": item.reason}
                for item in gemini_selection.omitted
            ],
        },
    }


def _wanted_kinds(run: Run) -> set[str]:
    if run.status == RunStatus.PASSED:
        return {"screenshot"}
    return {"screenshot", "log"}


def _artifact_kind(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "screenshot"
    if suffix == ".log":
        return "log"
    return None


def _module_status_counts(run: Run) -> dict[str, int]:
    counts: dict[str, int] = {}
    for module in run.modules:
        counts[module.status.value] = counts.get(module.status.value, 0) + 1
    return counts


def _format_datetime(value) -> str:
    if value is None:
        return "-"
    local_dt = value.astimezone(KST)
    return local_dt.strftime("%Y-%m-%d %H:%M:%S KST")


def _format_duration(run: Run) -> str:
    if run.started_at is None or run.ended_at is None:
        return "-"
    duration_ms = int((run.ended_at.astimezone(UTC) - run.started_at.astimezone(UTC)).total_seconds() * 1000)
    if duration_ms < 1000:
        return f"{duration_ms} ms"
    seconds = duration_ms // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}시간 {minutes}분 {seconds}초"
    if minutes:
        return f"{minutes}분 {seconds}초"
    return f"{seconds}초"


def _resolve_gemini_model(dotenv_values: dict[str, str]) -> str:
    return (
        resolve_env_value("E2E_EMAIL_GEMINI_MODEL", dotenv_values)
        or resolve_env_value("GEMINI_MODEL", dotenv_values)
        or DEFAULT_GEMINI_MODEL
    ).strip()


def _resolve_gemini_model_source(dotenv_values: dict[str, str]) -> str:
    _, email_model_source = resolve_env_with_source("E2E_EMAIL_GEMINI_MODEL", dotenv_values)
    if email_model_source:
        return email_model_source
    _, gemini_model_source = resolve_env_with_source("GEMINI_MODEL", dotenv_values)
    if gemini_model_source:
        return gemini_model_source
    return "default"


def _resolve_recipient_map(system_codes: list[str], dotenv_values: dict[str, str]) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    recipient_map: dict[str, tuple[str, ...]] = {}
    errors: list[str] = []
    for system_code in system_codes:
        env_name = _recipient_env_name(system_code)
        raw_value = (resolve_env_value(env_name, dotenv_values) or "").strip()
        recipients, invalid_entries = _parse_recipients(raw_value)
        if invalid_entries:
            errors.append(f"{env_name} 에 유효하지 않은 메일 주소가 있습니다: {', '.join(invalid_entries)}")
        if not recipients:
            errors.append(f"{env_name} 값이 없거나 유효한 수신자가 없습니다.")
            continue
        recipient_map[system_code] = tuple(recipients)
    return recipient_map, errors


def _recipient_summary(recipients_by_system: dict[str, tuple[str, ...]]) -> str | None:
    if not recipients_by_system:
        return None
    parts = [f"{system_code.upper()} {len(recipients)}명" for system_code, recipients in sorted(recipients_by_system.items())]
    return ", ".join(parts)


def _recipient_env_name(system_code: str) -> str:
    suffix = re.sub(r"[^A-Z0-9]+", "_", system_code.upper()).strip("_") or "DEFAULT"
    return f"E2E_EMAIL_RECIPIENTS_{suffix}"


def _parse_recipients(raw_value: str) -> tuple[list[str], list[str]]:
    recipients: list[str] = []
    invalid_entries: list[str] = []
    seen: set[str] = set()
    for raw_part in raw_value.split("|"):
        part = raw_part.strip()
        if not part:
            continue
        parsed_address = parseaddr(part)[1].strip()
        if not _looks_like_email(parsed_address):
            invalid_entries.append(part)
            continue
        normalized = parsed_address.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        recipients.append(parsed_address)
    return recipients, invalid_entries


def _looks_like_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))


def _gmail_account_looks_valid(account: str) -> bool:
    return _looks_like_email(account) and account.lower().endswith("@gmail.com")


def _gmail_app_password_looks_valid(password: str) -> bool:
    normalized = re.sub(r"\s+", "", password)
    if not normalized:
        return False
    if normalized.lower() in {"yourapppassword", "your_actual_app_password"}:
        return False
    return len(normalized) >= 16


def _api_key_looks_valid(api_key: str) -> bool:
    candidate = api_key.strip()
    if not candidate:
        return False
    if candidate in {"your_actual_api_key", "your_api_key"}:
        return False
    return len(candidate) >= 16


def _model_looks_valid(model: str) -> bool:
    candidate = model.strip()
    if not candidate:
        return False
    if candidate in {"your_model", "your_actual_model"}:
        return False
    return candidate.startswith("gemini-")


def _html_looks_safe(html: str) -> bool:
    candidate = html.strip()
    if not candidate.startswith("<"):
        return False
    lowered = candidate.lower()
    if any(pattern in lowered for pattern in HTML_FORBIDDEN_PATTERNS):
        return False
    if re.search(r"""(?:src|href)\s*=\s*['"]https?://""", lowered):
        return False
    return True
