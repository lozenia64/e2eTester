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
from app.runner.artifact_manager import ArtifactManager

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
    gemini_models: tuple[str, ...]
    gemini_enabled: bool
    gemini_verify_ssl: bool = True
    enabled: bool = True
    smtp_host: str = GMAIL_SMTP_HOST
    smtp_port: int = GMAIL_SMTP_PORT
    timeout_seconds: int = 20
    gemini_timeout_seconds: int = 90
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


class GeminiEmailHtmlComposer:
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

    def compose(self, context: dict, gemini_parts: list[dict]) -> str:
        prompt = self._build_suite_prompt(context) if context.get("report_type") == "suite" else self._build_prompt(context)
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
        html, _model = post_gemini_generate_content_with_fallback(
            api_key=self._api_key,
            models=list(self._models),
            payload=payload,
            timeout_seconds=self._timeout_seconds,
            verify_ssl=self._verify_ssl,
            endpoint=self._endpoint,
            log_prefix="[email]",
            transform=self._parse_html_response,
        )
        return html

    def _parse_html_response(self, response_json: dict, _model: str) -> str:
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
            "comparison": context["comparison"],
            "module_summary": context["module_summary"],
            "modules": context["modules"],
            "failed_modules": context["failed_modules"],
            "email_attachment_summary": context["email_attachment_summary"],
            "gemini_input_summary": context["gemini_input_summary"],
        }
        return "\n".join(
            [
                "# 역할",
                "당신은 웹 브라우저 기반 E2E 자동화 테스트 결과를 보고하는 시니어 QA 엔지니어이자 한국어 Gmail HTML 이메일 작성기다.",
                "운영 담당자가 이 메일 하나만 읽어도 테스트가 무엇을 검증했고 결과가 어떠했는지 완전히 파악할 수 있는,",
                "공식 문서 수준의 '테스트 결과 보고서' HTML 본문을 작성하라.",
                "",
                "# 입력 자료",
                "이 프롬프트와 함께 다음 자료가 제공된다. 모든 자료를 실제로 읽고 분석한 뒤 보고서에 반영하라.",
                "1. 실행 메타데이터 JSON(아래 첨부): 실행(run) 정보, 모듈별 실행 결과(modules), 실패 모듈 분석(failed_modules), 첨부/제외 파일 요약.",
                "2. 모듈별 스크린샷 이미지: 각 이미지 바로 앞에 '[screenshot] seq=... module_id=... module_name=... order=... path=...' 형식의 레이블 텍스트가 붙어 있다. seq 가 모듈별 결과 표의 순번과 동일한 1부터 시작하는 실행 순서다.",
                "3. 모듈별 실행 로그 텍스트: '[execution_log] seq=... module_id=... module_name=... order=... path=...' 레이블 뒤에 로그 본문이 이어진다.",
                "",
                "# 분석 지침",
                "- 스크린샷: 레이블의 module_id 로 어느 모듈의 최종 화면인지 식별하고, 화면에 실제로 무엇이 보이는지(페이지 제목, 주요 UI 상태, 조회 결과, 완료 표시, 오류 팝업/빈 화면 등 이상 징후) 직접 확인하라.",
                "  모듈 상태(PASSED/FAILED)와 화면 내용이 일치하는지 검증하고, 관찰한 내용을 보고서의 화면 검증 섹션에 모듈별로 1~2문장으로 기술하라.",
                "- 실행 로그: 시간 흐름에 따라 어떤 단계가 수행되었는지 파악하고, 경고/오류/재시도/타임아웃 등 특이 이벤트를 추출하라.",
                "  실패가 있으면 실패 직전 로그를 근거로 원인을 분석하고, 근거가 된 로그 메시지를 보고서에 짧게 인용하라.",
                "- 추측 금지: 스크린샷이나 로그에서 직접 확인되지 않는 사실을 만들어내지 마라. 자료가 제공되지 않은 모듈은 '자료 없음'으로 표기하라.",
                "- 직전 실행 대비: comparison 자료의 newly_failed(이번에 새로 실패)/recovered(이번에 복구)/still_failing(계속 실패) 모듈명을 활용하라. has_baseline 이 true 면 '직전 실행 대비 변화' 섹션을 만들어 새로 실패한 모듈을 가장 눈에 띄게 강조하고 복구·지속 실패도 정리하라. false 면 비교 대상이 없다고만 적어라.",
                "",
                "# 보고서 구성 (아래 순서를 따르라)",
                "1. 제목 헤더: '[E2E] {시스템명} 테스트 결과 보고서' 형태의 제목과 상태 배지(성공/실패). 성공은 #17804b, 실패는 #c44536 계열 색상 사용.",
                "2. 실행 개요: Run ID, 시스템, 요청/시작/종료 시각(KST), 총 소요시간, 최종 상태를 표(table)로 정리.",
                "3. 핵심 요약: 전체 결과를 2~3문장으로 요약. 실패 시 어떤 모듈에서 무엇이 실패했는지, 성공 시 어떤 업무 흐름이 검증되었는지 서술.",
                "4. 모듈별 결과: modules 배열 전체를 순번/모듈명/상태/소요시간/비고 컬럼의 표로 정리. 순번 컬럼은 각 모듈의 seq 값(1부터 시작하는 실제 실행 순서: 1, 2, 3, ...)을 그대로 사용하고, manifest의 order 값(10, 20, 40 등)은 순번으로 쓰거나 표에 노출하지 마라. 상태는 색상으로 구분(성공 녹색, 실패 적색, 그 외 회색).",
                "5. 화면 검증(스크린샷 분석): 제공된 스크린샷을 모듈 순서대로 분석한 관찰 결과. 각 항목에 모듈명과 관찰 내용을 기술.",
                "6. 로그 분석: 로그에서 확인한 주요 진행 이벤트와 특이사항 요약. 로그가 제공되지 않았으면 이 섹션은 생략.",
                "7. 실패 상세 분석(실패 시에만): 실패 모듈별로 증상, 로그/화면 근거, 추정 원인, 권장 조치를 정리. failed_modules 의 AI 분석 내용이 있으면 함께 반영.",
                "8. 첨부 안내: 메일에 첨부된 스크린샷/로그 건수. 용량 한도로 제외된 파일이 있으면 눈에 띄는 경고 박스로 목록과 사유를 표시.",
                "9. 푸터: 시스템 자동 발송 메일이라는 안내 문구를 작은 회색 글씨로 추가.",
                "",
                "# HTML 작성 규칙",
                "- Gmail에서 바로 렌더링 가능한 HTML 본문 조각만 작성하라(html/head/body 태그 없이 최상위 div 하나로 시작).",
                "- 허용 태그: div, table, thead, tbody, tr, td, th, p, h2, h3, ul, li, span, strong, code, hr, br 만 사용하라.",
                "- 모든 스타일은 inline style 로 작성하고, 전체를 max-width:760px 의 카드형 레이아웃으로 구성하라.",
                "- 글꼴은 Arial,'Noto Sans KR',sans-serif 를 사용하고 본문 line-height 는 1.6 정도로 유지하라.",
                "- script, style, iframe, form, input, button, 외부 이미지(src), 외부 CSS, 외부 링크(href)를 절대 사용하지 마라.",
                "- 개인정보(이름, 생년월일, 전화번호, OTP, 계약번호 등)를 새로 추론하거나 노출하지 마라. 화면에 보이더라도 보고서에는 옮기지 마라.",
                "",
                "# 출력 형식",
                "응답은 JSON 하나만 반환하고 html 필드에 완성된 HTML 문자열을 넣어라.",
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
            "email_attachment_summary": context["email_attachment_summary"],
            "gemini_input_summary": context["gemini_input_summary"],
        }
        return "\n".join(
            [
                "# 역할",
                "당신은 여러 시스템을 순차 실행한 E2E 전체 점검(Suite) 결과를 보고하는 시니어 QA 엔지니어이자 한국어 Gmail HTML 이메일 작성기다.",
                "운영 담당자가 이 메일 하나만 읽어도 전체 점검 결과와 각 시스템·모듈별 실행 결과를 완전히 파악할 수 있는 공식 보고서 HTML 본문을 작성하라.",
                "",
                "# 입력 자료",
                "1. Suite 메타데이터 JSON (suite)",
                "2. 시스템별 Run 결과 JSON (system_runs) — 각 항목에 modules 배열(모듈별 seq/이름/상태/소요시간/비고)이 포함됨",
                "3. 모듈별 스크린샷·실행 로그(레이블에 system_code, run_id, module_id 포함)",
                "",
                "# 보고서 구성 (순서 준수)",
                "1. 제목 헤더: '[E2E] 전체 시스템 순차 점검 결과 보고서' + Suite 최종 상태 배지",
                "2. Suite 개요 표: suite_id, 요청/시작/종료(KST), 총 소요, 통과/실패 시스템 수, browser_mode",
                "3. 시스템 요약 표: 순서, 시스템명, Run ID, 시스템 상태, 모듈 통과 수(예: 8/8)",
                "4. 시스템별 상세 섹션 (필수, system_runs 순서대로 각각 작성):",
                "   - 섹션 제목: '{순번}. {system_name} ({system_code})' + 시스템 상태 배지",
                "   - Run ID, 시스템 Run 상태, 소요시간(있으면) 한 줄 요약",
                "   - **모듈별 실행 결과 표 (필수)**: 해당 system_runs[].modules 전체를 빠짐없이 표로 작성.",
                "     컬럼: 순번(seq), 모듈명, 모듈 ID, 상태(색상 구분), 소요시간, 비고(message).",
                "     PASSED=녹색, FAILED=적색, BLOCKED/CANCELLED/SKIPPED=회색·주황.",
                "   - 실패 모듈이 있으면 failed_modules 기반으로 원인·권장 조치 소절 추가",
                "   - comparison.has_baseline 이 true 면 해당 시스템 직전 Run 대비 변화 요약",
                "5. 화면·로그 분석: 제공된 스크린샷/로그만 근거로, 시스템·모듈 단위로 관찰 내용 기술(추측 금지)",
                "6. 첨부 안내 및 제외 파일 경고(있을 때)",
                "7. 푸터: 자동 발송 안내",
                "",
                "# HTML 작성 규칙",
                "- inline style, max-width 760px, Gmail 안전 태그만(div/table/thead/tbody/tr/td/th/p/h2/h3/ul/li/span/strong/code/hr/br)",
                "- script/style/iframe/form/외부 리소스 금지",
                "- system_runs[].modules 의 seq 를 표 순번으로 그대로 사용 (manifest order 값은 순번으로 쓰지 마라)",
                "- 모듈 표는 각 시스템 섹션 안에 반드시 포함. 요약 표만으로 대체하지 마라.",
                "",
                "# 출력 형식",
                "응답은 JSON 하나만 반환하고 html 필드에 HTML 문자열을 넣어라.",
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
            GeminiEmailHtmlComposer(
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
        if self._composer is None:
            if context.get("report_type") == "suite":
                return self._build_suite_fallback_html(context)
            return self._build_fallback_html(context)
        try:
            return self._composer.compose(context, gemini_parts)
        except Exception as exc:
            print(f"[email] Gemini HTML 생성 실패: {exc}")
            if context.get("report_type") == "suite":
                return self._build_suite_fallback_html(context)
            return self._build_fallback_html(context)

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

        comparison = context["comparison"]
        comparison_section = ""
        if comparison["has_baseline"]:
            def _comparison_rows(title: str, names: list[str], color: str) -> str:
                if not names:
                    return ""
                items = "".join(f"<li>{escape(name)}</li>" for name in names)
                return (
                    f"<div style=\"margin-top:8px;\"><strong style=\"color:{color};\">{escape(title)}</strong>"
                    f"<ul style=\"margin:4px 0 0;padding-left:18px;\">{items}</ul></div>"
                )

            comparison_body = (
                _comparison_rows(f"새로 실패 {len(comparison['newly_failed'])}건", comparison["newly_failed"], "#c44536")
                + _comparison_rows(f"복구됨 {len(comparison['recovered'])}건", comparison["recovered"], "#17804b")
                + _comparison_rows(f"계속 실패 {len(comparison['still_failing'])}건", comparison["still_failing"], "#9a6700")
            ) or "<div style=\"margin-top:8px;\">직전 실행과 비교해 모듈 상태 변화가 없습니다.</div>"
            comparison_section = (
                "<div style=\"margin-top:20px;padding:14px 16px;border-radius:14px;background:#f1f5ff;"
                "border:1px solid rgba(37,99,235,0.18);\">"
                "<h3 style=\"margin:0 0 6px;font-size:16px;\">직전 실행 대비 변화</h3>"
                f"<div style=\"font-size:13px;color:#555;\">기준 Run: <code>{escape(str(comparison['baseline_run_id'] or '-'))}</code> "
                f"({escape(comparison['baseline_requested_at'])})</div>"
                f"{comparison_body}"
                "</div>"
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
            f"{comparison_section}"
            "<div style=\"margin-top:20px;padding:14px 16px;border-radius:14px;background:#f6f3ef;\">"
            "<strong style=\"display:block;margin-bottom:8px;\">첨부 요약</strong>"
            f"<div>스크린샷 {context['email_attachment_summary']['screenshot_count']}건 / "
            f"로그 {context['email_attachment_summary']['log_count']}건</div>"
            "</div>"
            + "".join(omitted_sections)
            + "</div></div>"
        )

    @staticmethod
    def _build_suite_fallback_html(context: dict) -> str:
        suite_info = context["suite"]
        tone_color = "#17804b" if suite_info["status"] == SuiteStatus.PASSED.value else "#c44536"
        step_rows = "".join(
            (
                "<tr>"
                f"<td style=\"padding:8px 6px;border-bottom:1px solid #eee;\">{item['order'] + 1}</td>"
                f"<td style=\"padding:8px 6px;border-bottom:1px solid #eee;\">{escape(item['system_name'])} "
                f"(<code>{escape(item['system_code'])}</code>)</td>"
                f"<td style=\"padding:8px 6px;border-bottom:1px solid #eee;\"><code>{escape(item['run_id'] or '-')}</code></td>"
                f"<td style=\"padding:8px 6px;border-bottom:1px solid #eee;\">{escape(item['status'])}</td>"
                f"<td style=\"padding:8px 6px;border-bottom:1px solid #eee;\">{item['module_passed']}/{item['module_total']}</td>"
                "</tr>"
            )
            for item in context["step_summary"]
        )

        system_sections: list[str] = []
        for index, system_run in enumerate(context["system_runs"], start=1):
            system_tone = "#17804b" if system_run["status"] == RunStatus.PASSED.value else "#c44536"
            if system_run["status"] == RunStatus.CANCELLED.value:
                system_tone = "#71717a"

            module_rows = "".join(
                (
                    "<tr>"
                    f"<td style=\"padding:8px 6px;border-bottom:1px solid #f0f0f0;text-align:center;\">{module['seq']}</td>"
                    f"<td style=\"padding:8px 6px;border-bottom:1px solid #f0f0f0;\">{escape(module['module_name'])}</td>"
                    f"<td style=\"padding:8px 6px;border-bottom:1px solid #f0f0f0;\"><code>{escape(module['module_id'])}</code></td>"
                    f"<td style=\"padding:8px 6px;border-bottom:1px solid #f0f0f0;"
                    f"color:{_suite_module_status_color(module['status'])};font-weight:600;\">"
                    f"{escape(module['status_label'])}</td>"
                    f"<td style=\"padding:8px 6px;border-bottom:1px solid #f0f0f0;\">{escape(module['duration_text'])}</td>"
                    f"<td style=\"padding:8px 6px;border-bottom:1px solid #f0f0f0;color:#555;\">{escape(module['message'])}</td>"
                    "</tr>"
                )
                for module in system_run.get("modules", [])
            )
            if not module_rows:
                module_rows = (
                    "<tr><td colspan=\"6\" style=\"padding:12px 6px;color:#888;\">"
                    f"{escape(system_run.get('note', '실행된 모듈이 없습니다.'))}"
                    "</td></tr>"
                )

            failed_block = ""
            if system_run.get("failed_modules"):
                failed_items = "".join(
                    (
                        "<li style=\"margin-bottom:8px;\">"
                        f"<strong>{escape(item['module_name'])}</strong> "
                        f"(<code>{escape(item['module_id'])}</code>)<br>"
                        f"<span>{escape(item['message'])}</span>"
                        + (
                            f"<br><span>AI 요약: {escape(item['analysis_summary'])}</span>"
                            if item.get("analysis_summary")
                            else ""
                        )
                        + (
                            f"<br><span>권장 조치: {escape(item['recommended_action'])}</span>"
                            if item.get("recommended_action")
                            else ""
                        )
                        + "</li>"
                    )
                    for item in system_run["failed_modules"]
                )
                failed_block = (
                    "<div style=\"margin-top:12px;padding:12px 14px;border-radius:12px;background:#fff5f5;"
                    "border:1px solid rgba(196,69,54,0.2);\">"
                    "<strong style=\"color:#c44536;\">실패 모듈</strong>"
                    f"<ul style=\"margin:8px 0 0;padding-left:18px;\">{failed_items}</ul>"
                    "</div>"
                )

            comparison = system_run.get("comparison") or {}
            comparison_block = ""
            if comparison.get("has_baseline"):
                comparison_block = (
                    "<div style=\"margin-top:12px;padding:12px 14px;border-radius:12px;background:#f1f5ff;"
                    "border:1px solid rgba(37,99,235,0.18);font-size:13px;\">"
                    f"<strong>직전 실행 대비</strong> (기준 Run: <code>{escape(str(comparison.get('baseline_run_id') or '-'))}</code>)"
                    + (
                        f"<div style=\"margin-top:6px;color:#c44536;\">새로 실패: {escape(', '.join(comparison.get('newly_failed') or []))}</div>"
                        if comparison.get("newly_failed")
                        else ""
                    )
                    + (
                        f"<div style=\"margin-top:4px;color:#17804b;\">복구됨: {escape(', '.join(comparison.get('recovered') or []))}</div>"
                        if comparison.get("recovered")
                        else ""
                    )
                    + (
                        f"<div style=\"margin-top:4px;color:#9a6700;\">계속 실패: {escape(', '.join(comparison.get('still_failing') or []))}</div>"
                        if comparison.get("still_failing")
                        else ""
                    )
                    + "</div>"
                )

            system_sections.append(
                (
                    "<div style=\"margin-top:20px;padding:16px;border:1px solid rgba(30,26,22,0.08);"
                    "border-radius:16px;background:#fff;\">"
                    f"<h3 style=\"margin:0 0 8px;font-size:17px;color:{system_tone};\">"
                    f"{index}. {escape(system_run['system_name'])} "
                    f"(<code>{escape(system_run['system_code'])}</code>)</h3>"
                    f"<p style=\"margin:0 0 12px;font-size:13px;color:#665f57;\">"
                    f"Run ID: <code>{escape(system_run.get('run_id') or '-')}</code> · "
                    f"상태: <strong>{escape(system_run.get('status_label', system_run['status']))}</strong> · "
                    f"모듈 통과: {system_run.get('module_passed', 0)}/{system_run.get('module_total', 0)} · "
                    f"소요: {escape(system_run.get('duration_text', '-'))}"
                    "</p>"
                    "<table style=\"width:100%;border-collapse:collapse;font-size:12px;\">"
                    "<thead><tr style=\"background:#f9fafb;\">"
                    "<th style=\"text-align:center;padding:8px 6px;border-bottom:2px solid #e5e7eb;width:40px;\">#</th>"
                    "<th style=\"text-align:left;padding:8px 6px;border-bottom:2px solid #e5e7eb;\">모듈명</th>"
                    "<th style=\"text-align:left;padding:8px 6px;border-bottom:2px solid #e5e7eb;\">모듈 ID</th>"
                    "<th style=\"text-align:left;padding:8px 6px;border-bottom:2px solid #e5e7eb;width:72px;\">상태</th>"
                    "<th style=\"text-align:left;padding:8px 6px;border-bottom:2px solid #e5e7eb;width:80px;\">소요</th>"
                    "<th style=\"text-align:left;padding:8px 6px;border-bottom:2px solid #e5e7eb;\">비고</th>"
                    "</tr></thead>"
                    f"<tbody>{module_rows}</tbody></table>"
                    f"{failed_block}{comparison_block}"
                    "</div>"
                )
            )

        return (
            "<div style=\"font-family:Arial,'Noto Sans KR',sans-serif;color:#1e1a16;line-height:1.6;\">"
            "<div style=\"max-width:760px;margin:0 auto;padding:24px;background:#fffaf4;border:1px solid rgba(30,26,22,0.08);"
            "border-radius:20px;\">"
            f"<h2 style=\"margin:0 0 12px;font-size:24px;color:{tone_color};\">"
            f"[E2E] 전체 시스템 순차 점검 {escape(suite_info['status_label'])}</h2>"
            "<table style=\"width:100%;border-collapse:collapse;font-size:14px;margin-bottom:18px;\">"
            f"<tr><td style=\"padding:6px 0;color:#665f57;\">Suite ID</td><td style=\"padding:6px 0;\"><code>{escape(suite_info['suite_id'])}</code></td></tr>"
            f"<tr><td style=\"padding:6px 0;color:#665f57;\">요청 시각</td><td style=\"padding:6px 0;\">{escape(suite_info['requested_at_kst'])}</td></tr>"
            f"<tr><td style=\"padding:6px 0;color:#665f57;\">종료 시각</td><td style=\"padding:6px 0;\">{escape(suite_info['ended_at_kst'])}</td></tr>"
            f"<tr><td style=\"padding:6px 0;color:#665f57;\">총 소요시간</td><td style=\"padding:6px 0;\">{escape(suite_info['duration_text'])}</td></tr>"
            f"<tr><td style=\"padding:6px 0;color:#665f57;\">시스템 통과</td><td style=\"padding:6px 0;\">{suite_info['step_passed']}/{suite_info['step_total']}</td></tr>"
            "</table>"
            "<h3 style=\"margin:0 0 10px;font-size:16px;\">시스템 요약</h3>"
            "<table style=\"width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px;\">"
            "<thead><tr>"
            "<th style=\"text-align:left;padding:8px 6px;border-bottom:2px solid #ddd;\">#</th>"
            "<th style=\"text-align:left;padding:8px 6px;border-bottom:2px solid #ddd;\">시스템</th>"
            "<th style=\"text-align:left;padding:8px 6px;border-bottom:2px solid #ddd;\">Run ID</th>"
            "<th style=\"text-align:left;padding:8px 6px;border-bottom:2px solid #ddd;\">상태</th>"
            "<th style=\"text-align:left;padding:8px 6px;border-bottom:2px solid #ddd;\">모듈</th>"
            "</tr></thead>"
            f"<tbody>{step_rows}</tbody></table>"
            "<h3 style=\"margin:24px 0 12px;font-size:16px;\">시스템별 모듈 실행 결과</h3>"
            + "".join(system_sections)
            + "<div style=\"margin-top:20px;padding:14px 16px;border-radius:14px;background:#f6f3ef;\">"
            "<strong style=\"display:block;margin-bottom:8px;\">첨부 요약</strong>"
            f"<div>스크린샷 {context['email_attachment_summary']['screenshot_count']}건 / "
            f"로그 {context['email_attachment_summary']['log_count']}건</div>"
            "</div>"
            "</div></div>"
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


def _suite_module_status_color(status: str) -> str:
    colors = {
        ModuleStatus.PASSED.value: "#17804b",
        ModuleStatus.FAILED.value: "#c44536",
        ModuleStatus.BLOCKED.value: "#f97316",
        ModuleStatus.SKIPPED.value: "#64748b",
        ModuleStatus.CANCELLED.value: "#71717a",
        ModuleStatus.WAITING_INPUT.value: "#d97706",
        RunStatus.PASSED.value: "#17804b",
        RunStatus.FAILED.value: "#c44536",
        RunStatus.CANCELLED.value: "#71717a",
        SuiteStatus.SKIPPED.value: "#64748b",
    }
    return colors.get(status, "#6b7280")


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
