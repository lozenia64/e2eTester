from __future__ import annotations

import re

from app.core.env_utils import resolve_env_value, resolve_env_with_source

DEFAULT_GEMINI_MODEL_CHAIN: tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-latest",
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


def resolve_gemini_models(dotenv_values: dict[str, str]) -> list[str]:
    raw_models = (resolve_env_value("GEMINI_MODELS", dotenv_values) or "").strip()
    if raw_models:
        return _split_models(raw_models)
    return list(DEFAULT_GEMINI_MODEL_CHAIN)


def resolve_gemini_models_source(dotenv_values: dict[str, str]) -> str:
    _, models_source = resolve_env_with_source("GEMINI_MODELS", dotenv_values)
    if models_source:
        return models_source
    return "default"
