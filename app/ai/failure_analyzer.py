from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from app.ai.gemini_client import (
    build_user_contents,
    create_gemini_client,
    generate_structured_with_fallback,
)
from app.ai.gemini_http import gemini_ssl_mode_detail, load_gemini_transport_settings
from app.ai.gemini_models import (
    api_key_looks_valid,
    gemini_models_look_valid,
    resolve_gemini_models,
    resolve_gemini_models_source,
)
from app.ai.gemini_schemas import FailureAnalysisGeminiOutput
from app.core.env_utils import (
    DEFAULT_ENV_FILE_PATH,
    load_dotenv_file,
    resolve_env_with_source,
)
from app.core.models import FailureAnalysis, FailureAnalysisRequest
from app.core.settings import get_settings


@dataclass(frozen=True)
class GeminiFailureAnalyzerStatus:
    state: str
    color: str
    title: str
    message: str
    detail: str
    enabled_value: str | None = None
    model_value: str | None = None
    api_key_source: str | None = None
    model_source: str | None = None


@dataclass(frozen=True)
class GeminiFailureAnalyzer:
    api_key: str
    models: tuple[str, ...]
    enabled: bool = True
    timeout_seconds: int = 20
    max_inline_image_bytes: int = 2_500_000
    verify_ssl: bool = True

    @property
    def model(self) -> str:
        return self.models[0]

    @classmethod
    def from_env(cls) -> GeminiFailureAnalyzer | None:
        settings = get_settings()
        if not settings.failure_analyzer_enabled:
            return None
        api_key = settings.gemini_api_key_str()
        models = resolve_gemini_models(settings)
        transport_settings = load_gemini_transport_settings()
        if not api_key:
            return None
        return cls(
            api_key=api_key,
            models=tuple(models),
            enabled=True,
            verify_ssl=transport_settings.verify_ssl,
        )

    @classmethod
    def inspect_env_status(cls) -> GeminiFailureAnalyzerStatus:
        dotenv_values = load_dotenv_file(DEFAULT_ENV_FILE_PATH)
        transport_settings = load_gemini_transport_settings(dotenv_values)
        enabled_raw, enabled_source = resolve_env_with_source(
            "E2E_FAILURE_ANALYZER_ENABLED", dotenv_values
        )
        if enabled_raw is None:
            return GeminiFailureAnalyzerStatus(
                state="missing",
                color="red",
                title="AI 분석 꺼짐",
                message="E2E_FAILURE_ANALYZER_ENABLED 값이 없습니다.",
                detail=(
                    "터미널 환경 변수나 .env 파일에 E2E_FAILURE_ANALYZER_ENABLED=true 를 설정해야 합니다. "
                    f"{gemini_ssl_mode_detail(transport_settings)}"
                ),
            )

        enabled = enabled_raw.strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return GeminiFailureAnalyzerStatus(
                state="disabled",
                color="orange",
                title="AI 분석 비활성",
                message=f"E2E_FAILURE_ANALYZER_ENABLED={enabled_raw} 으로 설정되어 있습니다.",
                detail=(
                    f"현재 값은 {enabled_source or 'unknown'} 에서 읽혔습니다. AI 분석을 쓰려면 true 로 바꿔야 합니다. "
                    f"{gemini_ssl_mode_detail(transport_settings)}"
                ),
                enabled_value=enabled_raw,
            )

        api_key, api_key_source = resolve_env_with_source("GEMINI_API_KEY", dotenv_values)
        models = resolve_gemini_models()
        model_source = resolve_gemini_models_source()
        api_key_valid = api_key_looks_valid(api_key or "")
        models_valid = gemini_models_look_valid(models)
        if not api_key_valid or not models_valid:
            problems: list[str] = []
            if not api_key_valid:
                problems.append("GEMINI_API_KEY 값이 없거나 placeholder 값입니다.")
            if not models_valid:
                problems.append(
                    "GEMINI_MODELS 값이 비어 있거나 gemini-/gemma- 로 시작하는 모델이 없습니다."
                )
            return GeminiFailureAnalyzerStatus(
                state="invalid",
                color="yellow",
                title="AI 분석 설정 필요",
                message="AI 분석은 활성화되어 있지만 Gemini 설정이 유효하지 않습니다.",
                detail=" ".join(problems + [gemini_ssl_mode_detail(transport_settings)]),
                enabled_value=enabled_raw,
                model_value=" -> ".join(models),
                api_key_source=api_key_source,
                model_source=model_source,
            )

        return GeminiFailureAnalyzerStatus(
            state="valid",
            color="blue",
            title="AI 분석 활성",
            message="AI 분석 기능이 활성화되어 있고 Gemini 설정도 유효합니다.",
            detail=(
                f"API 키는 {api_key_source or 'unknown'}, 모델 체인은 {model_source or 'default'} "
                f"({', '.join(models)}) 에서 읽혔습니다. "
                f"{gemini_ssl_mode_detail(transport_settings)}"
            ),
            enabled_value=enabled_raw,
            model_value=" -> ".join(models),
            api_key_source=api_key_source,
            model_source=model_source,
        )

    def analyze(self, analysis_request: FailureAnalysisRequest) -> FailureAnalysis | None:
        prompt = self._build_prompt(analysis_request)
        extra_parts: list[dict] = []
        inline_image = self._build_inline_image_part(analysis_request.screenshot_path)
        if inline_image is not None:
            extra_parts.append(inline_image)
        contents = build_user_contents(prompt, extra_parts)
        client = create_gemini_client(api_key=self.api_key, verify_ssl=self.verify_ssl)
        try:
            result, model = generate_structured_with_fallback(
                client=client,
                models=self.models,
                contents=contents,
                schema=FailureAnalysisGeminiOutput,
                temperature=0.1,
                timeout_seconds=self.timeout_seconds,
                log_prefix="[failure-analyzer]",
            )
        except RuntimeError:
            return None
        return FailureAnalysis(
            **result.model_dump(),
            provider="gemini",
            model=model,
        )

    def _build_prompt(self, analysis_request: FailureAnalysisRequest) -> str:
        request_dict = analysis_request.model_dump(mode="json")
        request_dict["recent_logs"] = request_dict.get("recent_logs", [])[-30:]
        request_dict["dialog_messages"] = request_dict.get("dialog_messages", [])[-10:]
        return "\n".join(
            [
                "당신은 Playwright 기반 E2E 실패 분석기다.",
                "주어진 정보를 바탕으로 실패 원인을 보수적으로 추정하고, 한국어로 간결하게 답하라.",
                "추정이 불충분하면 단정하지 말고 가능성이 높은 원인을 한 가지로 좁혀라.",
                "recommended_action에는 운영자가 다음에 바로 해볼 수 있는 단일 조치만 적어라.",
                "category는 selector_changed, popup_blocking, invalid_input, timeout, auth_failure, environment, unknown 중 하나를 우선 사용하라.",
                "developer_details에는 로그와 다이얼로그를 근거로 판단 이유를 적어라.",
                "다음은 분석 대상 JSON이다.",
                json.dumps(request_dict, ensure_ascii=False, indent=2),
            ]
        )

    def _build_inline_image_part(self, screenshot_path: str | None) -> dict | None:
        if not screenshot_path:
            return None
        image_path = Path(screenshot_path)
        if not image_path.exists() or not image_path.is_file():
            return None
        image_bytes = image_path.read_bytes()
        if len(image_bytes) > self.max_inline_image_bytes:
            return None
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        return {
            "inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(image_bytes).decode("ascii"),
            }
        }
