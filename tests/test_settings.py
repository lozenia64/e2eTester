"""E2ESettings(pydantic-settings) 단위 테스트."""

from __future__ import annotations

import pytest

from app.core.settings import E2ESettings, clear_settings_cache, get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_settings_defaults() -> None:
    settings = E2ESettings(_env_file=None)
    assert settings.run_concurrency == 4
    assert settings.failure_analyzer_enabled is False
    assert settings.email_enabled is False
    assert settings.schedule_tz == "Asia/Seoul"
    assert settings.db_path == "data/e2etester.db"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
    ],
)
def test_bool_flag_coercion(raw: str, expected: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_EMAIL_ENABLED", raw)
    settings = get_settings()
    assert settings.email_enabled is expected


def test_get_settings_reads_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_RUN_CONCURRENCY", "2")
    settings = get_settings()
    assert settings.run_concurrency == 2


def test_email_recipients_pipe_split() -> None:
    settings = E2ESettings(
        _env_file=None,
        E2E_EMAIL_RECIPIENTS_HOM="a@x.com|b@x.com",
    )
    assert settings.email_recipients_for("hom") == ["a@x.com", "b@x.com"]


def test_secret_str_masks_in_repr() -> None:
    settings = E2ESettings(_env_file=None, E2E_JWT_SECRET="super-secret-value")
    dumped = repr(settings.jwt_secret)
    assert "super-secret-value" not in dumped
    assert settings.jwt_secret.get_secret_value() == "super-secret-value"


def test_run_concurrency_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_RUN_CONCURRENCY", "0")
    with pytest.raises(Exception):
        get_settings()
