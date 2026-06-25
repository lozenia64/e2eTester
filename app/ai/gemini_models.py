from __future__ import annotations

import re

from app.core.env_utils import load_dotenv_file, resolve_env_with_source
from app.core.settings import E2ESettings, get_settings

DEFAULT_GEMINI_MODEL_CHAIN: tuple[str, ...] = (
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
)
_MODEL_SPLIT_PATTERN = re.compile(r"[|,]+")


def api_key_looks_valid(api_key: str) -> bool:
    candidate = api_key.strip()
    if not candidate:
        return False
    if candidate in {"your_actual_api_key", "your_api_key"}:
        return False
    return len(candidate) >= 16


def model_looks_valid(model: str) -> bool:
    candidate = model.strip()
    if not candidate:
        return False
    if candidate in {"your_model", "your_actual_model"}:
        return False
    return candidate.startswith(("gemini-", "gemma-"))


def gemini_models_look_valid(models: list[str]) -> bool:
    return bool(models) and all(model_looks_valid(model) for model in models)


def _split_models(raw_value: str) -> list[str]:
    models: list[str] = []
    seen: set[str] = set()
    for chunk in _MODEL_SPLIT_PATTERN.split(raw_value):
        model = chunk.strip()
        if not model or model in seen:
            continue
        seen.add(model)
        models.append(model)
    return models


def resolve_gemini_models(settings: E2ESettings | None = None) -> list[str]:
    settings = settings or get_settings()
    raw_models = (settings.gemini_models or "").strip()
    if not raw_models:
        return list(DEFAULT_GEMINI_MODEL_CHAIN)
    return _split_models(raw_models)


def resolve_gemini_models_source() -> str:
    _, models_source = resolve_env_with_source("GEMINI_MODELS", load_dotenv_file())
    return models_source or "default"
