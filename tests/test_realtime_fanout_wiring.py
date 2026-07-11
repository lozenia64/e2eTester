"""Redis fan-out 배선 정책 — local 모드에서 Redis 미필수."""

from __future__ import annotations

from app.composition.container import AppContainer
from app.core.settings import E2ESettings


def test_local_mode_skips_redis_fanout_by_default() -> None:
    settings = E2ESettings(
        E2E_EXECUTION_MODE="local",
        E2E_REDIS_URL="redis://127.0.0.1:6379/0",
        E2E_REALTIME_FANOUT="0",
    )
    container = AppContainer.build(settings)
    assert container._should_use_redis_fanout() is False
    assert container.redis_fanout is None


def test_remote_mode_enables_redis_fanout() -> None:
    settings = E2ESettings(
        E2E_EXECUTION_MODE="remote",
        E2E_REDIS_URL="redis://127.0.0.1:6379/0",
    )
    container = AppContainer.build(settings)
    assert container._should_use_redis_fanout() is True
    assert container.redis_fanout is not None


def test_local_mode_opt_in_enables_redis_fanout() -> None:
    settings = E2ESettings(
        E2E_EXECUTION_MODE="local",
        E2E_REDIS_URL="redis://127.0.0.1:6379/0",
        E2E_REALTIME_FANOUT="1",
    )
    container = AppContainer.build(settings)
    assert container._should_use_redis_fanout() is True
