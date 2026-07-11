"""애플리케이션 전역 설정 — pydantic-settings 기반 SSOT.

OS 환경 변수 > `.env` > 필드 기본값 순으로 로드한다(FastAPI 12-Factor).

종료 메일 서브시스템의 설정(`E2E_EMAIL_ENABLED`/`E2E_EMAIL_GMAIL_*`/
`E2E_EMAIL_RECIPIENTS_{SYSTEM_CODE}`/`E2E_EMAIL_OPERATOR_RECIPIENTS`)은 여기 필드로 두지
않는다 — 수신자 env 이름이 registry 에 등록된 시스템 코드로 동적으로 정해지므로,
`app/notifications/run_completion_email.py` 의 ``EmailNotificationConfig.from_env`` 가
``env_utils``(터미널 > .env 우선순위)로 직접 해석하는 것이 단일 경로다. 과거 이 파일에
시스템 코드 6종을 하드코딩한 수신자 필드가 있었으나, 실제로 읽히지 않는 중복 경로였고
새 시스템 추가 시 manifest 밖 수정을 강요해 제거했다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.env_utils import DEFAULT_ENV_FILE_PATH, resolve_env_with_source

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse_bool_flag(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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

    def otp_relay_token_str(self) -> str | None:
        if self.otp_relay_token is None:
            return None
        value = self.otp_relay_token.get_secret_value().strip()
        return value or None

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
