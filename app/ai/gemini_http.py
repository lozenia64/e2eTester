from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar
from urllib import error, request

from app.core.env_utils import resolve_env_with_source
from app.core.settings import get_settings

DEFAULT_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"
T = TypeVar("T")


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


def summarize_gemini_response(response_json: dict) -> str:
    parts: list[str] = []
    prompt_feedback = response_json.get("promptFeedback") or {}
    block_reason = prompt_feedback.get("blockReason")
    if block_reason:
        parts.append(f"promptBlockReason={block_reason}")

    candidates = response_json.get("candidates") or []
    parts.append(f"candidates={len(candidates)}")
    for index, candidate in enumerate(candidates[:3]):
        finish_reason = candidate.get("finishReason") or "unknown"
        content = candidate.get("content") or {}
        text_parts = [
            str(part.get("text") or "")
            for part in content.get("parts") or []
            if isinstance(part, dict) and part.get("text")
        ]
        text_len = sum(len(text) for text in text_parts)
        text_preview = _truncate("".join(text_parts), 120)
        parts.append(f"candidate[{index}].finishReason={finish_reason}, text_len={text_len}")
        if text_preview:
            parts.append(f"candidate[{index}].preview={text_preview!r}")

    usage = response_json.get("usageMetadata") or {}
    total_tokens = usage.get("totalTokenCount")
    if total_tokens is not None:
        parts.append(f"totalTokenCount={total_tokens}")

    if response_json.get("error"):
        parts.append(
            f"error={_truncate(json.dumps(response_json['error'], ensure_ascii=False), 200)}"
        )

    return ", ".join(parts) if parts else "empty response body"


def log_gemini_attempt_start(
    *, log_prefix: str, model: str, attempt: int, total: int, timeout_seconds: int
) -> None:
    print(
        f"{log_prefix} Gemini API 호출 시작 model={model} ({attempt}/{total}), timeout={timeout_seconds}s"
    )


def log_gemini_http_success(
    *, log_prefix: str, model: str, attempt: int, total: int, response_json: dict
) -> None:
    print(
        f"{log_prefix} Gemini API HTTP 200 model={model} ({attempt}/{total}): "
        f"{summarize_gemini_response(response_json)}"
    )


def log_gemini_http_failure(
    *, log_prefix: str, model: str, attempt: int, total: int, error: Exception
) -> None:
    print(f"{log_prefix} Gemini API HTTP 실패 model={model} ({attempt}/{total}): {error}")


def log_gemini_response_rejected(
    *,
    log_prefix: str,
    model: str,
    attempt: int,
    total: int,
    response_json: dict,
    error: Exception,
) -> None:
    print(
        f"{log_prefix} Gemini API 응답 처리 실패 model={model} ({attempt}/{total}): {error} | "
        f"response={summarize_gemini_response(response_json)}"
    )


def log_gemini_fallback_next(*, log_prefix: str, next_model: str, attempt: int, total: int) -> None:
    print(f"{log_prefix} 다음 모델로 fallback 합니다: model={next_model} ({attempt}/{total})")


def log_gemini_fallback_success(*, log_prefix: str, model: str, attempt: int, total: int) -> None:
    print(f"{log_prefix} fallback 성공 model={model} ({attempt}/{total})")


def log_gemini_all_failed(*, log_prefix: str, total: int, last_error: Exception | None) -> None:
    detail = f": {last_error}" if last_error is not None else ""
    print(f"{log_prefix} Gemini API 호출 {total}개 모델 모두 실패{detail}")


def post_gemini_generate_content(
    *,
    api_key: str,
    model: str,
    payload: dict,
    timeout_seconds: int,
    verify_ssl: bool,
    endpoint: str = DEFAULT_GEMINI_ENDPOINT,
    log_prefix: str | None = None,
    attempt: int | None = None,
    total: int | None = None,
) -> dict:
    if log_prefix and attempt is not None and total is not None:
        log_gemini_attempt_start(
            log_prefix=log_prefix,
            model=model,
            attempt=attempt,
            total=total,
            timeout_seconds=timeout_seconds,
        )

    api_url = f"{endpoint}/models/{model}:generateContent?key={api_key}"
    http_request = request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ssl_context = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    try:
        with request.urlopen(
            http_request, timeout=timeout_seconds, context=ssl_context
        ) as response:
            response_json = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        http_error = RuntimeError(f"Gemini API HTTP {exc.code}: {detail}")
        if log_prefix and attempt is not None and total is not None:
            log_gemini_http_failure(
                log_prefix=log_prefix,
                model=model,
                attempt=attempt,
                total=total,
                error=http_error,
            )
        raise http_error from exc
    except error.URLError as exc:
        reason = exc.reason
        if _is_cert_verification_error(reason):
            ssl_error = RuntimeError(
                "Gemini API request failed: SSL 인증서 검증에 실패했습니다. "
                "회사망 환경에서 프록시/사설 인증서를 사용하는 경우 .env 또는 터미널 환경 변수에 "
                "E2E_GEMINI_SSL_VERIFY=false 를 설정해 Gemini SSL 검증을 우회하세요."
            )
            if log_prefix and attempt is not None and total is not None:
                log_gemini_http_failure(
                    log_prefix=log_prefix,
                    model=model,
                    attempt=attempt,
                    total=total,
                    error=ssl_error,
                )
            raise ssl_error from exc
        url_error = RuntimeError(f"Gemini API request failed: {reason}")
        if log_prefix and attempt is not None and total is not None:
            log_gemini_http_failure(
                log_prefix=log_prefix,
                model=model,
                attempt=attempt,
                total=total,
                error=url_error,
            )
        raise url_error from exc

    if log_prefix and attempt is not None and total is not None:
        log_gemini_http_success(
            log_prefix=log_prefix,
            model=model,
            attempt=attempt,
            total=total,
            response_json=response_json,
        )
    return response_json


def post_gemini_generate_content_with_fallback(
    *,
    api_key: str,
    models: list[str],
    payload: dict,
    timeout_seconds: int,
    verify_ssl: bool,
    endpoint: str = DEFAULT_GEMINI_ENDPOINT,
    log_prefix: str = "[gemini]",
    transform: Callable[[dict, str], T] | None = None,
) -> tuple[T | dict, str]:
    if not models:
        raise RuntimeError("Gemini 모델 목록이 비어 있습니다.")

    total = len(models)
    last_error: Exception | None = None
    for index, model in enumerate(models):
        attempt = index + 1
        try:
            response = post_gemini_generate_content(
                api_key=api_key,
                model=model,
                payload=payload,
                timeout_seconds=timeout_seconds,
                verify_ssl=verify_ssl,
                endpoint=endpoint,
                log_prefix=log_prefix,
                attempt=attempt,
                total=total,
            )
        except Exception as exc:
            last_error = exc
            if index < total - 1:
                log_gemini_fallback_next(
                    log_prefix=log_prefix,
                    next_model=models[index + 1],
                    attempt=attempt + 1,
                    total=total,
                )
            continue

        if transform is not None:
            try:
                result = transform(response, model)
            except Exception as exc:
                last_error = exc
                log_gemini_response_rejected(
                    log_prefix=log_prefix,
                    model=model,
                    attempt=attempt,
                    total=total,
                    response_json=response,
                    error=exc,
                )
                if index < total - 1:
                    log_gemini_fallback_next(
                        log_prefix=log_prefix,
                        next_model=models[index + 1],
                        attempt=attempt + 1,
                        total=total,
                    )
                continue
            if index > 0:
                log_gemini_fallback_success(
                    log_prefix=log_prefix,
                    model=model,
                    attempt=attempt,
                    total=total,
                )
            return result, model

        if index > 0:
            log_gemini_fallback_success(
                log_prefix=log_prefix,
                model=model,
                attempt=attempt,
                total=total,
            )
        return response, model

    log_gemini_all_failed(log_prefix=log_prefix, total=total, last_error=last_error)
    message = f"Gemini API 호출이 {total}개 모델 모두 실패했습니다."
    if last_error is not None:
        raise RuntimeError(message) from last_error
    raise RuntimeError(message)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _is_cert_verification_error(reason: object) -> bool:
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    return "CERTIFICATE_VERIFY_FAILED" in str(reason)
