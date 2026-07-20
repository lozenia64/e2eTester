"""Realtime BC composition — fan-out 분기 + 알림 어댑터."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.settings import E2ESettings
from app.realtime.adapter import RealtimeNotificationAdapter, SuiteRealtimeNotificationAdapter
from app.realtime.redis_fanout import RedisRealtimeFanOut


@dataclass(frozen=True)
class RealtimeContainer:
    realtime: RealtimeNotificationAdapter
    suite_realtime: SuiteRealtimeNotificationAdapter
    redis_fanout: RedisRealtimeFanOut | None


def should_use_redis_fanout(settings: E2ESettings) -> bool:
    """remote 실행 또는 명시 opt-in 일 때만 Redis fan-out 을 켠다."""
    if not settings.redis_url:
        return False
    return settings.execution_mode == "remote" or settings.realtime_fanout_enabled


def compose_realtime(settings: E2ESettings) -> RealtimeContainer:
    if should_use_redis_fanout(settings):
        redis_fanout = RedisRealtimeFanOut(settings.redis_url)
        return RealtimeContainer(
            realtime=RealtimeNotificationAdapter(redis_fanout),
            suite_realtime=SuiteRealtimeNotificationAdapter(redis_fanout),
            redis_fanout=redis_fanout,
        )
    return RealtimeContainer(
        realtime=RealtimeNotificationAdapter(),
        suite_realtime=SuiteRealtimeNotificationAdapter(),
        redis_fanout=None,
    )
