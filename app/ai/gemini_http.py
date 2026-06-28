"""Gemini 전송 설정(SSL) + 호출 로깅 헬퍼.

실제 Gemini HTTP 호출은 google-genai SDK(``app.ai.gemini_client``, 내부적으로 httpx 사용)가
담당한다. 과거 이 모듈에 있던 ``urllib.request`` 기반 직접 호출 경로
(``post_gemini_generate_content`` 등)는 SDK 도입(0895c09)으로 대체되어 죽은 코드가
되었으므로 제거했다. 남은 것은 두 갈래가 아닌 단일 SDK 경로가 공유하는
전송 설정(``E2E_GEMINI_SSL_VERIFY``)과 모델 fallback 로깅뿐이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.env_utils import resolve_env_with_source
from app.core.settings import get_settings


@dataclass(frozen=True)
class GeminiTransportSettings:
    verify_ssl: bool
    verify_ssl_source: str | None


def load_gemini_transport_settings(
    dotenv_values: dict[str, str] | None = None,
) -> GeminiTransportSettings:
    if dotenv_values is None:
        settings = get_settings()
        return GeminiTransportSettings(
            verify_ssl=settings.gemini_ssl_verify,
            verify_ssl_source=settings.env_source("E2E_GEMINI_SSL_VERIFY"),
        )
    raw_value, source = resolve_env_with_source("E2E_GEMINI_SSL_VERIFY", dotenv_values)
    if raw_value is None:
        return GeminiTransportSettings(verify_ssl=True, verify_ssl_source=None)
    verify_ssl = raw_value.strip().lower() in {"1", "true", "yes", "on"}
    return GeminiTransportSettings(verify_ssl=verify_ssl, verify_ssl_source=source)


def gemini_ssl_mode_detail(settings: GeminiTransportSettings) -> str:
    if settings.verify_ssl:
        if settings.verify_ssl_source is None:
            return "Gemini SSL 인증서 검증은 기본값(true)으로 동작합니다."
        return f"Gemini SSL 인증서 검증은 {settings.verify_ssl_source} 에서 읽은 값(true)으로 동작합니다."
    if settings.verify_ssl_source is None:
        return "Gemini SSL 인증서 검증은 비활성화되어 있습니다."
    return f"Gemini SSL 인증서 검증은 {settings.verify_ssl_source} 에서 읽은 값(false)으로 비활성화되어 있습니다."


def log_gemini_attempt_start(
    *, log_prefix: str, model: str, attempt: int, total: int, timeout_seconds: int
) -> None:
    print(
        f"{log_prefix} Gemini API 호출 시작 model={model} ({attempt}/{total}), timeout={timeout_seconds}s"
    )


def log_gemini_http_failure(
    *, log_prefix: str, model: str, attempt: int, total: int, error: Exception
) -> None:
    print(f"{log_prefix} Gemini API HTTP 실패 model={model} ({attempt}/{total}): {error}")


def log_gemini_fallback_next(*, log_prefix: str, next_model: str, attempt: int, total: int) -> None:
    print(f"{log_prefix} 다음 모델로 fallback 합니다: model={next_model} ({attempt}/{total})")


def log_gemini_fallback_success(*, log_prefix: str, model: str, attempt: int, total: int) -> None:
    print(f"{log_prefix} fallback 성공 model={model} ({attempt}/{total})")


def log_gemini_all_failed(*, log_prefix: str, total: int, last_error: Exception | None) -> None:
    detail = f": {last_error}" if last_error is not None else ""
    print(f"{log_prefix} Gemini API 호출 {total}개 모델 모두 실패{detail}")
