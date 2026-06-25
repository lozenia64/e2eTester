"""환경 변수 유틸 — 레거시 호환 및 출처(terminal/.env) 추적.

애플리케이션 설정의 SSOT는 ``app.core.settings.E2ESettings`` (pydantic-settings)이다.
새 코드는 ``get_settings()`` 를 사용하고, 이 모듈은 관리자 상태 패널의 env 출처 표시 등에만 쓴다.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE_PATH = _REPO_ROOT / ".env"


def load_dotenv_file(env_path: Path = DEFAULT_ENV_FILE_PATH) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def resolve_env_value(name: str, dotenv_values: dict[str, str]) -> str | None:
    raw = os.getenv(name)
    if raw is not None:
        return raw
    return dotenv_values.get(name)


def resolve_env_with_source(
    name: str, dotenv_values: dict[str, str]
) -> tuple[str | None, str | None]:
    raw = os.getenv(name)
    if raw is not None:
        return raw, "terminal"
    fallback = dotenv_values.get(name)
    if fallback is not None:
        return fallback, ".env"
    return None, None


def env_flag(name: str, dotenv_values: dict[str, str], default: bool = False) -> bool:
    raw = resolve_env_value(name, dotenv_values)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
