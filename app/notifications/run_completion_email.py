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
from pathlib import Path
from zoneinfo import ZoneInfo

from app.ai.gemini_http import (
    gemini_ssl_mode_detail,
    load_gemini_transport_settings,
    post_gemini_generate_content_with_fallback,
)
from app.ai.gemini_models import (
    api_key_looks_valid,
    gemini_models_look_valid,
    resolve_gemini_models,
    resolve_gemini_models_source,
)
from app.core.env_utils import (
    DEFAULT_ENV_FILE_PATH,
    env_flag,
    load_dotenv_file,
    resolve_env_value,
    resolve_env_with_source,
)
from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.models import Run, SuiteRun
from app.notifications.report_renderer import render_run_report_html, render_suite_report_html
from app.runner.artifact_manager import ArtifactManager

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 465
KST = ZoneInfo("Asia/Seoul")
MAX_EMAIL_ATTACHMENT_BYTES = 17_500_000
MAX_GEMINI_ATTACHMENT_BYTES = 7_500_000
MAX_GEMINI_INLINE_IMAGE_BYTES = 2_500_000
MAX_GEMINI_LOG_BYTES = 180_000


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
    gemini_models: tuple[str, ...]
    gemini_enabled: bool
    gemini_verify_ssl: bool = True
    enabled: bool = True
    smtp_host: str = GMAIL_SMTP_HOST
    smtp_port: int = GMAIL_SMTP_PORT
    timeout_seconds: int = 20
    gemini_timeout_seconds: int = 60
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

        gemini_models = tuple(resolve_gemini_models(dotenv_values))
        gemini_api_key = (resolve_env_value("GEMINI_API_KEY", dotenv_values) or "").strip()
        transport_settings = load_gemini_transport_settings(dotenv_values)
        gemini_enabled = api_key_looks_valid(gemini_api_key) and gemini_models_look_valid(list(gemini_models))
        return cls(
            gmail_account=gmail_account,
            gmail_app_password=gmail_app_password,
            recipients_by_system=recipients_by_system,
            gemini_api_key=gemini_api_key if gemini_enabled else None,
            gemini_models=gemini_models,
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

        gemini_models = tuple(resolve_gemini_models(dotenv_values))
        gemini_api_key, gemini_api_key_source = resolve_env_with_source("GEMINI_API_KEY", dotenv_values)
        gemini_enabled = api_key_looks_valid(gemini_api_key or "") and gemini_models_look_valid(list(gemini_models))
        models_label = " -> ".join(gemini_models)
        models_source = resolve_gemini_models_source(dotenv_values)
        if not gemini_enabled:
            return EmailNotificationStatus(
                state="degraded",
                color="yellow",
                title="메일 알림 부분 활성",
                message="메일 발송은 가능하지만 Gemini HTML 생성 설정이 유효하지 않습니다.",
                detail=(
                    f"발신 계정은 {gmail_account_source or 'unknown'}, 앱 비밀번호는 {gmail_app_password_source or 'unknown'} 에서 읽혔습니다. "
                    f"Gemini API 키는 {gemini_api_key_source or 'missing'}, 모델 체인은 {models_source} 에서 읽혔습니다. "
                    f"이 경우 기본 HTML 템플릿으로 메일을 보냅니다. {gemini_ssl_mode_detail(transport_settings)}"
                ),
                model_value=models_label,
                recipient_summary=_recipient_summary(recipients_by_system),
            )

        return EmailNotificationStatus(
            state="valid",
            color="blue",
            title="메일 알림 활성",
            message="메일 알림 기능이 활성화되어 있고 Gmail/Gemini 설정도 유효합니다.",
            detail=(
                f"발신 계정은 {gmail_account_source or 'unknown'}, Gemini API 키는 {gemini_api_key_source or 'unknown'}, "
                f"모델 체인은 {models_source} ({models_label}) 에서 읽혔습니다. "
                f"{gemini_ssl_mode_detail(transport_settings)}"
            ),
            model_value=models_label,
            recipient_summary=_recipient_summary(recipients_by_system),
        )


@dataclass(frozen=True)
class RunArtifact:
    module_id: str
    module_name: str
    order: int
    seq: int
    kind: str
    path: Path
    relative_path: str
    size_bytes: int
    system_code: str = ""
    run_id: str = ""

    @property
    def attachment_name(self) -> str:
        safe_module_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.module_id)
        prefix = f"{self.system_code}_" if self.system_code else ""
        return f"{prefix}{safe_module_id}-{self.path.name}"


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


class GeminiReportContentComposer:
    """Gemini 로 보고서 '콘텐츠'(분석 텍스트)만 구조화 JSON 으로 생성한다.

    HTML/CSS 는 일절 생성하지 않는다. 레이아웃은 `report_renderer` 가 결정적으로
    찍어내고, 여기서 받은 콘텐츠(핵심 요약/화면·로그 관찰/실패 분석)만 그 안에 채워
    넣는다. 그래서 응답이 매번 달라도 메일 디자인은 항상 동일하게 유지된다.
    """

    # Run/Suite 콘텐츠 응답 스키마 — 모든 텍스트 필드. module_id 로 모듈을 식별한다.
    _MODULE_FINDING_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "module_id": {"type": "STRING"},
            "screen_observation": {"type": "STRING"},
            "log_observation": {"type": "STRING"},
        },
        "required": ["module_id"],
    }
    _FAILURE_DETAIL_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "module_id": {"type": "STRING"},
            "symptom": {"type": "STRING"},
            "evidence": {"type": "STRING"},
            "probable_cause": {"type": "STRING"},
            "recommended_action": {"type": "STRING"},
        },
        "required": ["module_id"],
    }
    _RUN_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "headline": {"type": "STRING"},
            "comparison_comment": {"type": "STRING"},
            "module_findings": {"type": "ARRAY", "items": _MODULE_FINDING_SCHEMA},
            "failure_details": {"type": "ARRAY", "items": _FAILURE_DETAIL_SCHEMA},
        },
        "required": ["headline", "module_findings"],
    }
    _SUITE_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "headline": {"type": "STRING"},
            "systems": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "system_code": {"type": "STRING"},
                        "summary": {"type": "STRING"},
                        "module_findings": {"type": "ARRAY", "items": _MODULE_FINDING_SCHEMA},
                        "failure_details": {"type": "ARRAY", "items": _FAILURE_DETAIL_SCHEMA},
                    },
                    "required": ["system_code"],
                },
            },
        },
        "required": ["headline", "systems"],
    }

    def __init__(
        self,
        api_key: str,
        models: tuple[str, ...],
        timeout_seconds: int = 20,
        verify_ssl: bool = True,
    ) -> None:
        self._api_key = api_key
        self._models = models
        self._timeout_seconds = timeout_seconds
        self._endpoint = "https://generativelanguage.googleapis.com/v1beta"
        self._verify_ssl = verify_ssl

    def compose(self, context: dict, gemini_parts: list[dict]) -> dict:
        is_suite = context.get("report_type") == "suite"
        prompt = self._build_suite_prompt(context) if is_suite else self._build_prompt(context)
        schema = self._SUITE_SCHEMA if is_suite else self._RUN_SCHEMA
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
                "responseSchema": schema,
            },
        }
        content, _model = post_gemini_generate_content_with_fallback(
            api_key=self._api_key,
            models=list(self._models),
            payload=payload,
            timeout_seconds=self._timeout_seconds,
            verify_ssl=self._verify_ssl,
            endpoint=self._endpoint,
            log_prefix="[email]",
            transform=self._parse_content_response,
        )
        return content

    def _parse_content_response(self, response_json: dict, _model: str) -> dict:
        parsed = self._extract_response_json(response_json)
        if parsed is None:
            raise RuntimeError("Gemini 콘텐츠 응답을 JSON으로 파싱하지 못했습니다.")
        return parsed

    def _build_prompt(self, context: dict) -> str:
        prompt_context = {
            "run": context["run"],
            "comparison": context["comparison"],
            "module_summary": context["module_summary"],
            "modules": context["modules"],
            "failed_modules": context["failed_modules"],
            "gemini_input_summary": context["gemini_input_summary"],
        }
        return "\n".join(
            [
                "# 역할",
                "당신은 웹 브라우저 기반 E2E 자동화 테스트 결과를 분석하는 시니어 QA 엔지니어다.",
                "운영 담당자에게 보낼 한국어 '테스트 결과 보고서'에 들어갈 분석 '내용'만 작성한다.",
                "중요: HTML, CSS, 마크다운, 표, 레이아웃은 절대 만들지 마라. 보고서의 시각 디자인은 별도 시스템이",
                "고정 템플릿으로 렌더링하므로, 당신은 정해진 JSON 스키마의 텍스트 필드만 정확히 채우면 된다.",
                "",
                "# 입력 자료",
                "1. 실행 메타데이터 JSON(아래 첨부): run 정보, modules(모듈별 결과), failed_modules, comparison.",
                "2. 모듈별 스크린샷 이미지: 각 이미지 앞에 '[screenshot] seq=... module_id=... module_name=... order=... path=...' 레이블이 붙어 있다.",
                "3. 모듈별 실행 로그 텍스트: '[execution_log] seq=... module_id=... module_name=... order=... path=...' 레이블 뒤에 로그 본문이 이어진다.",
                "",
                "# 분석 지침",
                "- 스크린샷: 레이블의 module_id 로 어느 모듈의 최종 화면인지 식별하고, 화면에 실제로 무엇이 보이는지(페이지 제목, 주요 UI 상태, 조회 결과, 완료 표시, 오류 팝업/빈 화면 등)를 직접 확인하라. 모듈 상태와 화면 내용이 일치하는지 검증하라.",
                "- 실행 로그: 시간 흐름상 어떤 단계가 수행됐는지 파악하고, 경고/오류/재시도/타임아웃 등 특이 이벤트를 추출하라. 실패 시 실패 직전 로그를 근거로 원인을 좁혀라.",
                "- 추측 금지: 스크린샷·로그에서 직접 확인되지 않는 사실을 지어내지 마라. 자료가 없는 모듈은 해당 필드를 빈 문자열로 두어라.",
                "- 개인정보(이름, 생년월일, 전화번호, OTP, 계약번호 등)는 새로 추론하거나 본문에 옮기지 마라. 일부만 보이면 마스킹된 형태 그대로만 언급하라.",
                "",
                "# 채워야 할 JSON 필드",
                "- headline: 전체 결과를 2~3문장으로 요약한 핵심 요약. 실패 시 어떤 모듈에서 무엇이 실패했는지, 성공 시 어떤 업무 흐름이 검증되었는지 서술.",
                "- comparison_comment: comparison.has_baseline 이 true 일 때만, 직전 실행 대비 변화를 1~2문장으로 서술(newly_failed/recovered/still_failing 활용). baseline 이 없으면 빈 문자열.",
                "- module_findings: 자료가 있는 모듈마다 한 항목. module_id 는 입력의 module_id 와 정확히 일치시킬 것.",
                "    screen_observation: 해당 모듈 스크린샷에서 관찰한 내용 1~2문장(자료 없으면 빈 문자열).",
                "    log_observation: 해당 모듈 로그에서 확인한 주요 진행/특이 이벤트 1~2문장(자료 없으면 빈 문자열).",
                "- failure_details: status 가 FAILED 인 모듈마다 한 항목(없으면 빈 배열). symptom(증상), evidence(로그/화면 근거), probable_cause(추정 원인), recommended_action(운영자가 바로 해볼 단일 조치). failed_modules 의 기존 AI 분석이 있으면 반영해 보강하라.",
                "",
                "# 작성 규칙",
                "- 순번은 modules 의 seq 값(1부터)을 기준으로 말하고, manifest order 값(10,20,40)은 언급하지 마라.",
                "- 모든 텍스트는 한국어 존댓말, 간결한 보고서 문체로 작성하라.",
                "",
                "## 실행 메타데이터",
                json.dumps(prompt_context, ensure_ascii=False, indent=2),
            ]
        )

    def _build_suite_prompt(self, context: dict) -> str:
        prompt_context = {
            "suite": context["suite"],
            "step_summary": context["step_summary"],
            "system_runs": context["system_runs"],
            "gemini_input_summary": context["gemini_input_summary"],
        }
        return "\n".join(
            [
                "# 역할",
                "당신은 여러 시스템을 순차 실행한 E2E 전체 점검(Suite) 결과를 분석하는 시니어 QA 엔지니어다.",
                "운영 담당자에게 보낼 한국어 전체 점검 보고서에 들어갈 분석 '내용'만 작성한다.",
                "중요: HTML, CSS, 마크다운, 표, 레이아웃은 절대 만들지 마라. 시각 디자인은 고정 템플릿이 렌더링하므로",
                "당신은 정해진 JSON 스키마의 텍스트 필드만 정확히 채운다.",
                "",
                "# 입력 자료",
                "1. Suite 메타데이터 JSON (suite)",
                "2. 시스템별 Run 결과 JSON (system_runs) — 각 항목에 system_code, modules(seq/이름/상태/소요/비고), failed_modules, comparison 포함.",
                "3. 모듈별 스크린샷·실행 로그(레이블에 system_code, run_id, module_id 포함)",
                "",
                "# 채워야 할 JSON 필드",
                "- headline: 전체 점검 결과를 2~3문장으로 요약(통과/실패 시스템 수, 두드러진 실패 시스템 등).",
                "- systems: system_runs 의 각 시스템마다 한 항목. system_code 는 입력값과 정확히 일치시킬 것.",
                "    summary: 해당 시스템 결과 1~2문장 요약.",
                "    module_findings: 자료가 있는 모듈마다 {module_id, screen_observation, log_observation}. 자료 없는 필드는 빈 문자열.",
                "    failure_details: FAILED 모듈마다 {module_id, symptom, evidence, probable_cause, recommended_action}. 없으면 빈 배열.",
                "",
                "# 분석 지침",
                "- 스크린샷·로그 레이블의 system_code/module_id 로 어느 시스템·모듈인지 식별하라.",
                "- 추측 금지: 직접 확인되지 않은 사실은 지어내지 말고 빈 문자열로 두어라.",
                "- 개인정보는 새로 추론·노출하지 마라. 순번은 modules 의 seq 기준으로만 말하라.",
                "- 모든 텍스트는 한국어 존댓말, 간결한 보고서 문체.",
                "",
                "## 실행 메타데이터",
                json.dumps(prompt_context, ensure_ascii=False, indent=2),
            ]
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
            GeminiReportContentComposer(
                config.gemini_api_key,
                config.gemini_models,
                timeout_seconds=config.gemini_timeout_seconds,
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

    def build_suite(
        self,
        suite: SuiteRun,
        runs: list[Run],
        recipients: list[str],
        email_selection: AttachmentSelection,
        gemini_selection: GeminiPromptSelection,
    ) -> EmailMessage:
        context = _build_suite_email_context(suite, runs, email_selection, gemini_selection)
        html_body = self._build_html_body(context, gemini_selection.parts)
        text_body = self._build_plain_text(context)

        message = EmailMessage()
        message["Subject"] = _build_suite_subject(suite)
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
        # 레이아웃은 report_renderer 가 결정적으로 찍어내고, Gemini 는 분석 콘텐츠만 채운다.
        # Gemini 가 비활성/실패면 ai_content=None 으로 동일 템플릿이 AI 서술 없이 렌더링된다.
        ai_content = self._compose_ai_content(context, gemini_parts)
        if context.get("report_type") == "suite":
            return render_suite_report_html(context, ai_content)
        return render_run_report_html(context, ai_content)

    def _compose_ai_content(self, context: dict, gemini_parts: list[dict]) -> dict | None:
        if self._composer is None:
            return None
        try:
            return self._composer.compose(context, gemini_parts)
        except Exception as exc:
            print(f"[email] Gemini 보고서 콘텐츠 생성 실패(기본 템플릿으로 발송): {exc}")
            return None

    @staticmethod
    def _build_plain_text(context: dict) -> str:
        if context.get("report_type") == "suite":
            return _build_suite_plain_text(context)
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
        comparison = context["comparison"]
        if comparison["has_baseline"]:
            lines.append("")
            lines.append(f"직전 실행 대비 변화 (기준 Run: {comparison['baseline_run_id'] or '-'}):")
            if comparison["newly_failed"]:
                lines.append(f"- 새로 실패: {', '.join(comparison['newly_failed'])}")
            if comparison["recovered"]:
                lines.append(f"- 복구됨: {', '.join(comparison['recovered'])}")
            if comparison["still_failing"]:
                lines.append(f"- 계속 실패: {', '.join(comparison['still_failing'])}")
            if not (comparison["newly_failed"] or comparison["recovered"] or comparison["still_failing"]):
                lines.append("- 모듈 상태 변화 없음")
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
        if run.suite_id:
            return
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

    def send_suite_completion(self, suite: SuiteRun, runs: list[Run]) -> None:
        recipients = self._resolve_suite_recipients(suite)
        if not recipients:
            raise RuntimeError(f"메일 수신자를 찾지 못했습니다: suite={suite.suite_id}")

        ordered_runs = self._order_runs_for_suite(suite, runs)
        artifacts = self._collect_artifacts_for_runs(ordered_runs)
        email_selection = self._select_suite_email_attachments(suite, ordered_runs, artifacts)
        gemini_selection = self._select_gemini_prompt_inputs_for_artifacts(artifacts)
        message = self._builder.build_suite(suite, ordered_runs, recipients, email_selection, gemini_selection)
        self._sender.send(message, recipients)
        print(
            f"[email] suite={suite.suite_id} recipients={len(recipients)} "
            f"attachments={len(email_selection.included)} status={suite.status}"
        )

    def _resolve_suite_recipients(self, suite: SuiteRun) -> list[str]:
        seen: set[str] = set()
        recipients: list[str] = []
        for step in suite.steps:
            for address in self._config.recipients_by_system.get(step.system_code, ()):
                if address in seen:
                    continue
                seen.add(address)
                recipients.append(address)
        return recipients

    @staticmethod
    def _order_runs_for_suite(suite: SuiteRun, runs: list[Run]) -> list[Run]:
        run_by_id = {run.run_id: run for run in runs}
        ordered: list[Run] = []
        for step in sorted(suite.steps, key=lambda item: item.order):
            if step.run_id and step.run_id in run_by_id:
                ordered.append(run_by_id[step.run_id])
        return ordered

    def _collect_artifacts_for_runs(self, runs: list[Run]) -> list[RunArtifact]:
        collected: list[RunArtifact] = []
        seen_paths: set[str] = set()
        for run in runs:
            for artifact in self._collect_artifacts(run):
                if artifact.relative_path in seen_paths:
                    continue
                seen_paths.add(artifact.relative_path)
                collected.append(artifact)
        return collected

    def _select_suite_email_attachments(
        self,
        suite: SuiteRun,
        runs: list[Run],
        artifacts: list[RunArtifact],
    ) -> AttachmentSelection:
        failed_run_ids = {run.run_id for run in runs if run.status == RunStatus.FAILED}
        wanted_logs = suite.status == SuiteStatus.FAILED
        included: list[RunArtifact] = []
        omitted: list[OmittedArtifact] = []
        total_bytes = 0
        for artifact in artifacts:
            if artifact.kind == "screenshot":
                accept = True
            elif artifact.kind == "log":
                accept = wanted_logs and artifact.run_id in failed_run_ids
            else:
                accept = False
            if not accept:
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

    def _select_gemini_prompt_inputs_for_artifacts(self, artifacts: list[RunArtifact]) -> GeminiPromptSelection:
        parts: list[dict] = []
        omitted: list[OmittedArtifact] = []
        included_labels: list[str] = []
        total_bytes = 0

        for artifact in artifacts:
            system_prefix = f"system_code={artifact.system_code} run_id={artifact.run_id} " if artifact.system_code else ""
            label = (
                f"{system_prefix}seq={artifact.seq} module_id={artifact.module_id} "
                f"module_name={artifact.module_name} order={artifact.order} path={artifact.relative_path}"
            )
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
                parts.append({"text": f"[screenshot] {label}"})
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
            parts.append({"text": f"[execution_log] {label}\n{log_text}"})
            included_labels.append(f"log:{artifact.relative_path}")
            total_bytes += min(len(log_text.encode("utf-8")), self._config.max_gemini_log_bytes)

        return GeminiPromptSelection(parts=parts, omitted=omitted, included_labels=included_labels)

    def _collect_artifacts(self, run: Run) -> list[RunArtifact]:
        collected: list[RunArtifact] = []
        seen_paths: set[str] = set()
        for seq, module in enumerate(sorted(run.modules, key=lambda item: item.order), start=1):
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
                        seq=seq,
                        kind=kind,
                        path=path,
                        relative_path=relative_path,
                        size_bytes=path.stat().st_size,
                        system_code=run.system_code,
                        run_id=run.run_id,
                    )
                )
        return collected

    def _select_email_attachments(self, run: Run, artifacts: list[RunArtifact]) -> AttachmentSelection:
        wanted_kinds = _wanted_email_kinds(run)
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
        # 메일 첨부와 달리 Gemini 입력에는 성공/실패와 무관하게 스크린샷과 로그를 모두 제공한다.
        # 보고서 품질이 화면·로그 분석에 의존하기 때문이다.
        parts: list[dict] = []
        omitted: list[OmittedArtifact] = []
        included_labels: list[str] = []
        total_bytes = 0

        for artifact in artifacts:
            label = (
                f"seq={artifact.seq} module_id={artifact.module_id} module_name={artifact.module_name} "
                f"order={artifact.order} path={artifact.relative_path}"
            )
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
                parts.append({"text": f"[screenshot] {label}"})
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
            parts.append({"text": f"[execution_log] {label}\n{log_text}"})
            included_labels.append(f"log:{artifact.relative_path}")
            total_bytes += min(len(log_text.encode("utf-8")), self._config.max_gemini_log_bytes)

        return GeminiPromptSelection(parts=parts, omitted=omitted, included_labels=included_labels)


def _build_subject(run: Run) -> str:
    status_label = "테스트 완료" if run.status == RunStatus.PASSED else "테스트 중단"
    return f"[E2E][{run.system_code.upper()}][{run.status.value}] {run.run_id} {status_label}"


def _build_suite_subject(suite: SuiteRun) -> str:
    status_label = "전체 점검 완료" if suite.status == SuiteStatus.PASSED else "전체 점검 중단"
    return f"[E2E][SUITE][{suite.status.value}] {suite.suite_id} {status_label}"


def _format_suite_duration(suite: SuiteRun) -> str:
    if suite.started_at is None or suite.ended_at is None:
        return "-"
    seconds = int((suite.ended_at - suite.started_at).total_seconds())
    if seconds < 60:
        return f"{seconds}초"
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}분 {remainder}초"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}시간 {minutes}분"


def _module_status_label(status: str) -> str:
    labels = {
        ModuleStatus.PASSED.value: "성공",
        ModuleStatus.FAILED.value: "실패",
        ModuleStatus.BLOCKED.value: "차단",
        ModuleStatus.SKIPPED.value: "제외",
        ModuleStatus.CANCELLED.value: "취소",
        ModuleStatus.RUNNING.value: "실행 중",
        ModuleStatus.QUEUED.value: "대기",
        ModuleStatus.PENDING.value: "대기",
        ModuleStatus.WAITING_INPUT.value: "입력 대기",
        SuiteStatus.PASSED.value: "성공",
        SuiteStatus.FAILED.value: "실패",
        SuiteStatus.SKIPPED.value: "제외",
        SuiteStatus.CANCELLED.value: "취소",
        SuiteStatus.RUNNING.value: "실행 중",
        SuiteStatus.PENDING.value: "대기",
        SuiteStatus.WAITING_INPUT.value: "입력 대기",
    }
    return labels.get(status, status)


def _build_comparison_context(run: Run) -> dict:
    comparison = run.comparison
    return {
        "has_baseline": bool(comparison and comparison.has_baseline),
        "baseline_run_id": comparison.baseline_run_id if comparison else None,
        "baseline_requested_at": (
            _format_datetime(comparison.baseline_requested_at)
            if comparison and comparison.baseline_requested_at
            else "-"
        ),
        "newly_failed": list(comparison.newly_failed) if comparison else [],
        "recovered": list(comparison.recovered) if comparison else [],
        "still_failing": list(comparison.still_failing) if comparison else [],
    }


def _serialize_run_for_suite_report(run: Run) -> dict:
    selected_ids = set(run.selected_module_ids) or {
        module.module_id for module in run.modules if module.status != ModuleStatus.SKIPPED
    }
    ordered_modules = sorted(run.modules, key=lambda item: item.order)
    modules: list[dict] = []
    failed_modules: list[dict] = []
    module_summary: dict[str, int] = {}
    seq = 0
    for module in ordered_modules:
        if module.module_id not in selected_ids:
            continue
        seq += 1
        status_value = module.status.value
        module_summary[status_value] = module_summary.get(status_value, 0) + 1
        modules.append(
            {
                "seq": seq,
                "order": module.order,
                "module_id": module.module_id,
                "module_name": module.name,
                "group": module.group,
                "status": status_value,
                "status_label": _module_status_label(status_value),
                "message": module.message,
                "duration_text": _format_module_duration(module.duration_ms),
                "retry_count": module.retry_count,
            }
        )
        if module.status == ModuleStatus.FAILED:
            failed_modules.append(
                {
                    "module_id": module.module_id,
                    "module_name": module.name,
                    "message": module.message,
                    "analysis_summary": module.failure_analysis.user_summary if module.failure_analysis else "",
                    "recommended_action": module.failure_analysis.recommended_action if module.failure_analysis else "",
                }
            )
    module_passed = sum(1 for module in modules if module["status"] == ModuleStatus.PASSED.value)
    return {
        "modules": modules,
        "module_summary": module_summary,
        "failed_modules": failed_modules,
        "comparison": _build_comparison_context(run),
        "module_passed": module_passed,
        "module_total": len(modules),
        "duration_text": _format_duration(run),
    }


def _build_suite_email_context(
    suite: SuiteRun,
    runs: list[Run],
    email_selection: AttachmentSelection,
    gemini_selection: GeminiPromptSelection,
) -> dict:
    run_by_id = {run.run_id: run for run in runs}
    step_passed = sum(1 for step in suite.steps if step.status == SuiteStatus.PASSED)
    step_failed = sum(1 for step in suite.steps if step.status == SuiteStatus.FAILED)
    step_skipped = sum(1 for step in suite.steps if step.status == SuiteStatus.SKIPPED)
    step_selected_total = len(suite.steps) - step_skipped
    step_summary = []
    system_runs = []
    for step in sorted(suite.steps, key=lambda item: item.order):
        run = run_by_id.get(step.run_id or "")
        module_passed = 0
        module_total = step.module_total
        if run is not None:
            report = _serialize_run_for_suite_report(run)
            module_passed = report["module_passed"]
            module_total = report["module_total"]
            system_runs.append(
                {
                    "order": step.order,
                    "system_code": run.system_code.upper(),
                    "system_name": run.system_name,
                    "run_id": run.run_id,
                    "status": run.status.value,
                    "status_label": "성공" if run.status == RunStatus.PASSED else "실패",
                    "duration_text": report["duration_text"],
                    "module_passed": module_passed,
                    "module_total": module_total,
                    "module_summary": report["module_summary"],
                    "modules": report["modules"],
                    "failed_modules": report["failed_modules"],
                    "comparison": report["comparison"],
                }
            )
        else:
            if step.status == SuiteStatus.SKIPPED:
                note = "건너뜀 (선택 제외)"
            elif step.status == SuiteStatus.FAILED:
                note = "Run이 생성되지 않았습니다."
            else:
                note = "실행되지 않음"
            system_runs.append(
                {
                    "order": step.order,
                    "system_code": step.system_code.upper(),
                    "system_name": step.system_name,
                    "run_id": step.run_id,
                    "status": step.status.value,
                    "status_label": _module_status_label(step.status.value),
                    "duration_text": "-",
                    "module_passed": 0,
                    "module_total": module_total,
                    "module_summary": {},
                    "modules": [],
                    "failed_modules": [],
                    "comparison": {"has_baseline": False},
                    "note": note,
                }
            )
        step_summary.append(
            {
                "order": step.order,
                "system_code": step.system_code.upper(),
                "system_name": step.system_name,
                "run_id": step.run_id,
                "status": step.status.value,
                "module_passed": module_passed,
                "module_total": module_total,
            }
        )

    return {
        "report_type": "suite",
        "suite": {
            "suite_id": suite.suite_id,
            "status": suite.status.value,
            "status_label": "성공" if suite.status == SuiteStatus.PASSED else "실패",
            "requested_at_kst": _format_datetime(suite.requested_at),
            "started_at_kst": _format_datetime(suite.started_at),
            "ended_at_kst": _format_datetime(suite.ended_at),
            "duration_text": _format_suite_duration(suite),
            "step_total": step_selected_total,
            "step_defined_total": len(suite.steps),
            "step_skipped": step_skipped,
            "step_passed": step_passed,
            "step_failed": step_failed,
            "browser_mode": suite.browser_mode,
        },
        "step_summary": step_summary,
        "system_runs": system_runs,
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


def _build_suite_plain_text(context: dict) -> str:
    suite_info = context["suite"]
    lines = [
        f"[E2E] 전체 시스템 순차 점검 {suite_info['status_label']}",
        f"Suite ID: {suite_info['suite_id']}",
        f"요청 시각(KST): {suite_info['requested_at_kst']}",
        f"종료 시각(KST): {suite_info['ended_at_kst']}",
        f"총 소요시간: {suite_info['duration_text']}",
        f"시스템 통과: {suite_info['step_passed']}/{suite_info['step_total']}"
        + (f" ({suite_info['step_skipped']}개 제외)" if suite_info.get("step_skipped") else ""),
        "",
        "=== 시스템 요약 ===",
    ]
    for step in context["step_summary"]:
        lines.append(
            f"- {step['order'] + 1}. {step['system_name']} ({step['system_code']}): {step['status']} "
            f"run={step['run_id'] or '-'} modules={step['module_passed']}/{step['module_total']}"
        )
    lines.append("")
    lines.append("=== 시스템별 모듈 실행 결과 ===")
    for system_run in context["system_runs"]:
        lines.append("")
        lines.append(
            f"[{system_run['order'] + 1}] {system_run['system_name']} ({system_run['system_code']}) "
            f"- {system_run.get('status_label', system_run['status'])} "
            f"run={system_run.get('run_id') or '-'}"
        )
        if not system_run.get("modules"):
            lines.append(f"  ({system_run.get('note', '모듈 없음')})")
            continue
        for module in system_run["modules"]:
            lines.append(
                f"  {module['seq']}. {module['module_name']} [{module['status_label']}] "
                f"{module['duration_text']} - {module['message']}"
            )
    attachment_summary = context["email_attachment_summary"]
    lines.extend(
        [
            "",
            f"첨부 파일: 스크린샷 {attachment_summary['screenshot_count']}건, 로그 {attachment_summary['log_count']}건",
        ]
    )
    return "\n".join(lines)


def _build_email_context(run: Run, email_selection: AttachmentSelection, gemini_selection: GeminiPromptSelection) -> dict:
    module_summary = _module_status_counts(run)
    ordered_modules = sorted(run.modules, key=lambda item: item.order)
    modules = [
        {
            "seq": index,
            "order": module.order,
            "module_id": module.module_id,
            "module_name": module.name,
            "group": module.group,
            "status": module.status.value,
            "message": module.message,
            "duration_text": _format_module_duration(module.duration_ms),
            "retry_count": module.retry_count,
        }
        for index, module in enumerate(ordered_modules, start=1)
    ]
    failed_modules = []
    for module in ordered_modules:
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

    comparison = run.comparison
    comparison_context = {
        "has_baseline": bool(comparison and comparison.has_baseline),
        "baseline_run_id": comparison.baseline_run_id if comparison else None,
        "baseline_requested_at": (
            _format_datetime(comparison.baseline_requested_at)
            if comparison and comparison.baseline_requested_at
            else "-"
        ),
        "newly_failed": list(comparison.newly_failed) if comparison else [],
        "recovered": list(comparison.recovered) if comparison else [],
        "still_failing": list(comparison.still_failing) if comparison else [],
    }

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
            "triggered_by": "예약" if run.triggered_by == "schedule" else "수동",
        },
        "comparison": comparison_context,
        "module_summary": module_summary,
        "modules": modules,
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


def _wanted_email_kinds(run: Run) -> set[str]:
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


def _format_module_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "-"
    if duration_ms < 1000:
        return f"{duration_ms} ms"
    seconds = duration_ms // 1000
    minutes, seconds = divmod(seconds, 60)
    if minutes:
        return f"{minutes}분 {seconds}초"
    return f"{seconds}초"


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
