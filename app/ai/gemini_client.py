"""Google GenAI SDK 클라이언트 — 구조화 출력 + 모델 fallback."""

from __future__ import annotations

import base64
import ssl
from collections.abc import Sequence

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.ai.gemini_http import (
    log_gemini_all_failed,
    log_gemini_attempt_start,
    log_gemini_fallback_next,
    log_gemini_fallback_success,
    log_gemini_http_failure,
)


def create_gemini_client(*, api_key: str, verify_ssl: bool = True) -> genai.Client:
    if verify_ssl:
        return genai.Client(api_key=api_key)
    unverified = ssl.create_default_context()
    unverified.check_hostname = False
    unverified.verify_mode = ssl.CERT_NONE
    http_options = types.HttpOptions(
        client_args={"verify": unverified},
        async_client_args={"verify": unverified},
    )
    return genai.Client(api_key=api_key, http_options=http_options)


def build_user_contents(
    prompt: str, extra_parts: Sequence[dict] | None = None
) -> list[types.Content]:
    parts: list[types.Part] = [types.Part.from_text(text=prompt)]
    for part in extra_parts or ():
        if "text" in part:
            parts.append(types.Part.from_text(text=str(part["text"])))
            continue
        inline = part.get("inline_data")
        if not isinstance(inline, dict):
            continue
        mime_type = str(inline.get("mime_type") or "application/octet-stream")
        raw_data = inline.get("data")
        if raw_data is None:
            continue
        if isinstance(raw_data, str):
            data = base64.b64decode(raw_data)
        else:
            data = bytes(raw_data)
        parts.append(types.Part.from_bytes(data=data, mime_type=mime_type))
    return [types.Content(role="user", parts=parts)]


def _parse_structured_response[T: BaseModel](
    response: types.GenerateContentResponse, schema: type[T]
) -> T:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    if parsed is not None:
        return schema.model_validate(parsed)
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini 응답 본문이 비어 있습니다.")
    return schema.model_validate_json(text)


def generate_structured_with_fallback[T: BaseModel](
    *,
    client: genai.Client,
    models: Sequence[str],
    contents: list[types.Content],
    schema: type[T],
    temperature: float = 0.2,
    timeout_seconds: int = 60,
    log_prefix: str = "[gemini]",
) -> tuple[T, str]:
    if not models:
        raise RuntimeError("Gemini 모델 목록이 비어 있습니다.")

    model_list = list(models)
    total = len(model_list)
    last_error: Exception | None = None
    http_options = types.HttpOptions(timeout=timeout_seconds * 1000)

    for index, model in enumerate(model_list):
        attempt = index + 1
        log_gemini_attempt_start(
            log_prefix=log_prefix,
            model=model,
            attempt=attempt,
            total=total,
            timeout_seconds=timeout_seconds,
        )
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                    response_schema=schema,
                    http_options=http_options,
                ),
            )
            result = _parse_structured_response(response, schema)
        except Exception as exc:
            last_error = exc
            log_gemini_http_failure(
                log_prefix=log_prefix,
                model=model,
                attempt=attempt,
                total=total,
                error=exc,
            )
            if index < total - 1:
                log_gemini_fallback_next(
                    log_prefix=log_prefix,
                    next_model=model_list[index + 1],
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
        print(f"{log_prefix} Gemini SDK 성공 model={model} ({attempt}/{total})")
        return result, model

    log_gemini_all_failed(log_prefix=log_prefix, total=total, last_error=last_error)
    message = f"Gemini API 호출이 {total}개 모델 모두 실패했습니다."
    if last_error is not None:
        raise RuntimeError(message) from last_error
    raise RuntimeError(message)
