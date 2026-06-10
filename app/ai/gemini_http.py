from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from urllib import error, request

from app.core.env_utils import resolve_env_with_source

DEFAULT_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"


@dataclass(frozen=True)
class GeminiTransportSettings:
    verify_ssl: bool
    verify_ssl_source: str | None


def load_gemini_transport_settings(dotenv_values: dict[str, str]) -> GeminiTransportSettings:
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


def post_gemini_generate_content(
    *,
    api_key: str,
    model: str,
    payload: dict,
    timeout_seconds: int,
    verify_ssl: bool,
    endpoint: str = DEFAULT_GEMINI_ENDPOINT,
) -> dict:
    api_url = f"{endpoint}/models/{model}:generateContent?key={api_key}"
    http_request = request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ssl_context = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    try:
        with request.urlopen(http_request, timeout=timeout_seconds, context=ssl_context) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        reason = exc.reason
        if _is_cert_verification_error(reason):
            raise RuntimeError(
                "Gemini API request failed: SSL 인증서 검증에 실패했습니다. "
                "회사망 환경에서 프록시/사설 인증서를 사용하는 경우 .env 또는 터미널 환경 변수에 "
                "E2E_GEMINI_SSL_VERIFY=false 를 설정해 Gemini SSL 검증을 우회하세요."
            ) from exc
        raise RuntimeError(f"Gemini API request failed: {reason}") from exc


def _is_cert_verification_error(reason: object) -> bool:
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    return "CERTIFICATE_VERIFY_FAILED" in str(reason)
