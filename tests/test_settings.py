"""E2ESettings(pydantic-settings) 단위 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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
    monkeypatch.setenv("E2E_FAILURE_ANALYZER_ENABLED", raw)
    settings = get_settings()
    assert settings.failure_analyzer_enabled is expected


def test_get_settings_reads_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_RUN_CONCURRENCY", "2")
    settings = get_settings()
    assert settings.run_concurrency == 2


def test_email_env_is_not_owned_by_settings() -> None:
    # 종료 메일 설정(E2E_EMAIL_*)은 registry 시스템 코드 기반으로 notifier 가 직접 해석한다.
    # settings 에 시스템 코드를 하드코딩한 수신자 필드를 되살리지 않도록 고정하는 회귀 테스트.
    settings = E2ESettings(_env_file=None)
    assert not any(name.startswith("email_") for name in type(settings).model_fields)


def test_secret_str_masks_in_repr() -> None:
    settings = E2ESettings(_env_file=None, E2E_JWT_SECRET="super-secret-value")
    dumped = repr(settings.jwt_secret)
    assert "super-secret-value" not in dumped
    assert settings.jwt_secret.get_secret_value() == "super-secret-value"


def test_run_concurrency_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_RUN_CONCURRENCY", "0")
    with pytest.raises(ValidationError):
        get_settings()
