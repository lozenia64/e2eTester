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
    sqlite_busy_timeout_ms: int = Field(
        default=5000,
        ge=0,
        validation_alias="E2E_SQLITE_BUSY_TIMEOUT_MS",
    )
    run_concurrency: int = Field(default=4, ge=1, validation_alias="E2E_RUN_CONCURRENCY")
    run_concurrency_heavy: int = Field(
        default=2, ge=1, validation_alias="E2E_RUN_CONCURRENCY_HEAVY"
    )
    run_concurrency_light: int = Field(
        default=4, ge=1, validation_alias="E2E_RUN_CONCURRENCY_LIGHT"
    )
    run_concurrency_interactive: int = Field(
        default=2, ge=1, validation_alias="E2E_RUN_CONCURRENCY_INTERACTIVE"
    )
    # 원격 실행(Phase 2): local=API 프로세스 in-process, remote=워커+Redis
    execution_mode: str = Field(default="local", validation_alias="E2E_EXECUTION_MODE")
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", validation_alias="E2E_REDIS_URL")
    # 다중 API 인스턴스 WS fan-out. remote 모드에서는 자동 활성; local 에서는 명시 opt-in.
    realtime_fanout_enabled: bool = Field(default=False, validation_alias="E2E_REALTIME_FANOUT")
    worker_concurrency: int = Field(default=2, ge=1, validation_alias="E2E_WORKER_CONCURRENCY")
    session_lease_ttl: int = Field(default=60, ge=5, validation_alias="E2E_SESSION_LEASE_TTL")
    worker_base_url: str = Field(
        default="http://127.0.0.1:8100",
        validation_alias="E2E_WORKER_BASE_URL",
    )
    # 워커 프로세스(`worker.main`) 자신의 바인드 주소. API 는 `worker_base_url` 로 접속한다.
    # 이 도구는 한 PC 에서 API·워커를 함께 띄우므로 루프백이 기본 — 과거 기본값 `0.0.0.0`
    # 은 워커 실행 호스트를 같은 네트워크에 불필요하게 노출했다. 워커를 다른 PC 에 두는
    # 구성에서만 `0.0.0.0` 으로 되돌린다.
    worker_http_host: str = Field(default="127.0.0.1", validation_alias="E2E_WORKER_HTTP_HOST")
    worker_http_port: int = Field(
        default=8100, ge=1, le=65535, validation_alias="E2E_WORKER_HTTP_PORT"
    )

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
    # 상황판(/wall)은 로그인 없이 열리는 공개 읽기 라우트다(P3-2 설계 D1).
    # 사내망 전제이므로 기본은 켜 두고, 앱이 외부에서 접근 가능한 배포에서는
    # false 로 즉시 차단한다. false 면 /wall·/wall/fragment 가 404 다.
    wall_enabled: bool = Field(default=True, validation_alias="E2E_WALL_ENABLED")
    # 메일에 넣을 공개 주소(예: https://e2e.example.com). 기본은 빈 문자열 —
    # 배포 환경마다 다르고, 잘못된 URL 이 든 메일은 회수할 수 없다(P3-4 D6).
    # 비어 있으면 일간 리포트는 링크 없이 지금처럼 자족적으로 나간다.
    public_base_url: str = Field(default="", validation_alias="E2E_PUBLIC_BASE_URL")
    run_retention_cron: str = Field(default="0 3 * * *", validation_alias="E2E_RUN_RETENTION_CRON")
    # 일간 리포트 메일(P3-3). 메일은 되돌릴 수 없는 부수효과라 기본은 꺼 둔다 —
    # 상황판(E2E_WALL_ENABLED, 기본 true)과 반대 판단이다.
    daily_report_enabled: bool = Field(
        default=False, validation_alias="E2E_EMAIL_DAILY_REPORT_ENABLED"
    )
    # 발송 시각(스케줄 타임존 기준 5필드 cron). None 이면 기본값 08:00.
    daily_report_cron: str | None = Field(
        default=None, validation_alias="E2E_EMAIL_DAILY_REPORT_CRON"
    )

    # 운영 로깅 (structlog)
    log_level: str = Field(default="INFO", validation_alias="E2E_LOG_LEVEL")
    log_format: str = Field(default="console", validation_alias="E2E_LOG_FORMAT")

    # OTP SMS 중계
    otp_relay_token: SecretStr | None = Field(default=None, validation_alias="E2E_OTP_RELAY_TOKEN")
    otp_relay_regex: str | None = Field(default=None, validation_alias="E2E_OTP_RELAY_REGEX")

    # 텔레그램 봇(예약 즉시 실행). 사용자별 연결은 계정 화면에서 하고 DB 에 저장한다.
    telegram_bot_token: SecretStr | None = Field(
        default=None, validation_alias="E2E_TELEGRAM_BOT_TOKEN"
    )

    # 자동 재실행(설계 §3.6)
    # 예약 Run 이 도구 오류(ERROR)로 끝났을 때 1회 자동 재실행할지.
    auto_rerun_enabled: bool = Field(default=False, validation_alias="E2E_AUTO_RERUN_ENABLED")
    # Run 총 실행 시간 상한(초). None 이면 무제한 — 기본값이 기존 동작을 유지한다.
    run_max_duration_s: int | None = Field(default=None, validation_alias="E2E_RUN_MAX_DURATION_S")
    # Run 당 로그인 재주행(tier 2) 허용 횟수(설계 §3.6).
    recovery_tier2_budget: int = Field(default=2, validation_alias="E2E_RECOVERY_TIER2_BUDGET")

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
        "auto_rerun_enabled",
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
