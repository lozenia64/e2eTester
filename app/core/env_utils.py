"""환경 변수 유틸 — 레거시 호환 및 출처(terminal/.env) 추적.

애플리케이션 설정의 SSOT는 ``app.core.settings.E2ESettings`` (pydantic-settings)이다.
새 코드는 ``get_settings()`` 를 사용하고, 이 모듈은 관리자 상태 패널의 env 출처 표시 등에만 쓴다.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE_PATH = _REPO_ROOT / ".env"


def load_dotenv_file(env_path: Path = DEFAULT_ENV_FILE_PATH) -> dict[str, str]:
    """`.env` 파일을 ``{이름: 값}`` 으로 읽는다(출처 추적용 보조 경로).

    표준 ``python-dotenv`` 로 파싱한다. ``interpolate=False`` 로 두어 토큰/비밀번호에
    들어갈 수 있는 ``$`` 가 변수 확장으로 변형되지 않게 하고(과거 자체 파서와 동일한 리터럴
    동작 유지), 값이 없는 키(``KEY`` 단독 줄)는 과거처럼 제외해 반환 타입을 ``dict[str, str]``
    로 유지한다.
    """
    if not env_path.exists():
        return {}
    values = dotenv_values(env_path, interpolate=False, encoding="utf-8")
    return {key: value for key, value in values.items() if value is not None}


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
