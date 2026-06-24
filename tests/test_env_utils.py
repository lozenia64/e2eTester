"""env_utils 단위 테스트 — env_flag·우선순위·기본 .env 경로."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.env_utils import DEFAULT_ENV_FILE_PATH, env_flag, resolve_env_value


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("off", False),
    ],
)
def test_env_flag_truthy_and_falsy_values(raw: str, expected: bool) -> None:
    assert env_flag("E2E_EMAIL_ENABLED", {"E2E_EMAIL_ENABLED": raw}) is expected


def test_env_flag_missing_uses_default() -> None:
    assert env_flag("E2E_EMAIL_ENABLED", {}, default=False) is False
    assert env_flag("E2E_EMAIL_ENABLED", {}, default=True) is True


def test_terminal_env_overrides_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_EMAIL_ENABLED", "true")
    dotenv = {"E2E_EMAIL_ENABLED": "false"}
    assert resolve_env_value("E2E_EMAIL_ENABLED", dotenv) == "true"
    assert env_flag("E2E_EMAIL_ENABLED", dotenv, default=False) is True


def test_dotenv_used_when_terminal_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E2E_EMAIL_ENABLED", raising=False)
    dotenv = {"E2E_EMAIL_ENABLED": "false"}
    assert resolve_env_value("E2E_EMAIL_ENABLED", dotenv) == "false"
    assert env_flag("E2E_EMAIL_ENABLED", dotenv, default=True) is False


def test_default_env_file_path_is_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    assert DEFAULT_ENV_FILE_PATH == repo_root / ".env"
    assert DEFAULT_ENV_FILE_PATH.is_absolute()
