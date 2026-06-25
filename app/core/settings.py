"""애플리케이션 전역 설정 — pydantic-settings 기반 SSOT.

OS 환경 변수 > `.env` > 필드 기본값 순으로 로드한다(FastAPI 12-Factor).
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.env_utils import DEFAULT_ENV_FILE_PATH, resolve_env_with_source

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPE_SPLIT = re.compile(r"[|,]+")
_KNOWN_EMAIL_RECIPIENT_SYSTEMS = ("hom", "mhm", "fp", "hrp", "hwtc", "chbot")


def _parse_bool_flag(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _split_pipe_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in _PIPE_SPLIT.split(raw) if part.strip()]


class E2ESettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 인증
    jwt_secret: SecretStr = Field(
        default=SecretStr("change-me-in-production"),
        validation_alias="E2E_JWT_SECRET",
    )
    admin_email: str = Field(default="admin@example.com", validation_alias="E2E_ADMIN_EMAIL")
    admin_password: SecretStr = Field(
        default=SecretStr("admin1234"),
        validation_alias="E2E_ADMIN_PASSWORD",
    )

    # 영속 저장소·실행
    db_path: str = Field(default="data/e2etester.db", validation_alias="E2E_DB_PATH")
    run_concurrency: int = Field(default=4, ge=1, validation_alias="E2E_RUN_CONCURRENCY")

    # Gemini / AI 실패 분석
    failure_analyzer_enabled: bool = Field(
        default=False, validation_alias="E2E_FAILURE_ANALYZER_ENABLED"
    )
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_models: str | None = Field(default=None, validation_alias="GEMINI_MODELS")
    gemini_ssl_verify: bool = Field(default=True, validation_alias="E2E_GEMINI_SSL_VERIFY")

    # 종료 메일
    email_enabled: bool = Field(default=False, validation_alias="E2E_EMAIL_ENABLED")
    email_gmail_account: str | None = Field(
        default=None, validation_alias="E2E_EMAIL_GMAIL_ACCOUNT"
    )
    email_gmail_app_password: SecretStr | None = Field(
        default=None,
        validation_alias="E2E_EMAIL_GMAIL_APP_PASSWORD",
    )
    email_operator_recipients: str | None = Field(
        default=None,
        validation_alias="E2E_EMAIL_OPERATOR_RECIPIENTS",
    )
    email_recipients_hom: str | None = Field(
        default=None, validation_alias="E2E_EMAIL_RECIPIENTS_HOM"
    )
    email_recipients_mhm: str | None = Field(
        default=None, validation_alias="E2E_EMAIL_RECIPIENTS_MHM"
    )
    email_recipients_fp: str | None = Field(
        default=None, validation_alias="E2E_EMAIL_RECIPIENTS_FP"
    )
    email_recipients_hrp: str | None = Field(
        default=None, validation_alias="E2E_EMAIL_RECIPIENTS_HRP"
    )
    email_recipients_hwtc: str | None = Field(
        default=None, validation_alias="E2E_EMAIL_RECIPIENTS_HWTC"
    )
    email_recipients_chbot: str | None = Field(
        default=None, validation_alias="E2E_EMAIL_RECIPIENTS_CHBOT"
    )

    # 예약·보존
    schedule_tz: str = Field(default="Asia/Seoul", validation_alias="E2E_SCHEDULE_TZ")
    run_retention_enabled: bool = Field(default=True, validation_alias="E2E_RUN_RETENTION_ENABLED")
    run_retention_cron: str = Field(default="0 3 * * *", validation_alias="E2E_RUN_RETENTION_CRON")

    # 운영 로깅 (structlog)
    log_level: str = Field(default="INFO", validation_alias="E2E_LOG_LEVEL")
    log_format: str = Field(default="console", validation_alias="E2E_LOG_FORMAT")

    # OTP SMS 중계
    otp_relay_token: SecretStr | None = Field(default=None, validation_alias="E2E_OTP_RELAY_TOKEN")
    otp_relay_regex: str | None = Field(default=None, validation_alias="E2E_OTP_RELAY_REGEX")

    # Playwright 프로필
    user_data_dir: str | None = Field(default=None, validation_alias="E2E_USER_DATA_DIR")
    workspace_dir: str | None = Field(default=None, validation_alias="E2E_WORKSPACE_DIR")
    playwright_mcp_profile_dir: str | None = Field(
        default=None,
        validation_alias="E2E_PLAYWRIGHT_MCP_PROFILE_DIR",
    )

    @field_validator(
        "failure_analyzer_enabled",
        "email_enabled",
        "gemini_ssl_verify",
        "run_retention_enabled",
        mode="before",
    )
    @classmethod
    def _coerce_bool_flags(cls, value: Any) -> bool:
        return _parse_bool_flag(value, default=False)

    def gemini_api_key_str(self) -> str:
        if self.gemini_api_key is None:
            return ""
        return self.gemini_api_key.get_secret_value().strip()

    def email_gmail_app_password_str(self) -> str:
        if self.email_gmail_app_password is None:
            return ""
        return self.email_gmail_app_password.get_secret_value().strip()

    def otp_relay_token_str(self) -> str | None:
        if self.otp_relay_token is None:
            return None
        value = self.otp_relay_token.get_secret_value().strip()
        return value or None

    def operator_recipient_list(self) -> list[str]:
        return _split_pipe_list(self.email_operator_recipients)

    def email_recipients_for(self, system_code: str) -> list[str]:
        code = system_code.lower()
        attr = f"email_recipients_{code}"
        raw: str | None = None
        if code in _KNOWN_EMAIL_RECIPIENT_SYSTEMS and hasattr(self, attr):
            raw = getattr(self, attr)
        if not raw:
            env_name = f"E2E_EMAIL_RECIPIENTS_{system_code.upper()}"
            raw = os.getenv(env_name)
        return _split_pipe_list(raw)

    def env_source(self, env_name: str) -> str | None:
        """설정값 출처(terminal / .env) — 관리자 상태 패널용."""
        from app.core.env_utils import load_dotenv_file

        _, source = resolve_env_with_source(env_name, load_dotenv_file())
        return source


@lru_cache
def get_settings() -> E2ESettings:
    return E2ESettings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
