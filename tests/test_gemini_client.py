from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from app.ai.gemini_client import (
    build_user_contents,
    generate_structured_with_fallback,
)


class _SampleSchema(BaseModel):
    headline: str


def test_build_user_contents_maps_text_and_inline_image() -> None:
    import base64

    contents = build_user_contents(
        "prompt",
        [
            {"text": "label"},
            {
                "inline_data": {
                    "mime_type": "image/png",
                    "data": base64.b64encode(b"png").decode("ascii"),
                }
            },
        ],
    )
    assert len(contents) == 1
    assert len(contents[0].parts) == 3


@patch("app.ai.gemini_client.log_gemini_attempt_start")
@patch("app.ai.gemini_client.log_gemini_all_failed")
def test_generate_structured_with_fallback_returns_parsed_model(
    _log_all_failed: MagicMock,
    _log_attempt: MagicMock,
) -> None:
    client = MagicMock()
    response = MagicMock()
    response.parsed = _SampleSchema(headline="ok")
    response.text = ""
    client.models.generate_content.return_value = response

    result, model = generate_structured_with_fallback(
        client=client,
        models=["gemini-2.0-flash"],
        contents=build_user_contents("hi"),
        schema=_SampleSchema,
        timeout_seconds=5,
        log_prefix="[test]",
    )
    assert result.headline == "ok"
    assert model == "gemini-2.0-flash"


@patch("app.ai.gemini_client.log_gemini_attempt_start")
@patch("app.ai.gemini_client.log_gemini_http_failure")
@patch("app.ai.gemini_client.log_gemini_fallback_next")
@patch("app.ai.gemini_client.log_gemini_all_failed")
def test_generate_structured_with_fallback_tries_next_model(
    _log_all_failed: MagicMock,
    _log_fallback: MagicMock,
    _log_failure: MagicMock,
    _log_attempt: MagicMock,
) -> None:
    client = MagicMock()
    ok_response = MagicMock()
    ok_response.parsed = None
    ok_response.text = '{"headline":"fallback"}'
    client.models.generate_content.side_effect = [RuntimeError("quota"), ok_response]

    result, model = generate_structured_with_fallback(
        client=client,
        models=["gemini-2.0-flash", "gemini-2.0-flash-lite"],
        contents=build_user_contents("hi"),
        schema=_SampleSchema,
        timeout_seconds=5,
        log_prefix="[test]",
    )
    assert result.headline == "fallback"
    assert model == "gemini-2.0-flash-lite"
    assert client.models.generate_content.call_count == 2


def test_generate_structured_with_fallback_raises_when_all_models_fail() -> None:
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("down")

    with pytest.raises(RuntimeError, match="모두 실패"):
        generate_structured_with_fallback(
            client=client,
            models=["gemini-2.0-flash"],
            contents=build_user_contents("hi"),
            schema=_SampleSchema,
            timeout_seconds=5,
            log_prefix="[test]",
        )
