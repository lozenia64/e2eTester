"""Redis 실시간 fan-out 통합 테스트(redis 미가용 시 skip)."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.core.enums import RunStatus
from app.core.run_models import DashboardEvent
from app.realtime.adapter import RealtimeNotificationAdapter
from app.realtime.redis_fanout import RedisRealtimeFanOut


def _redis_url() -> str | None:
    return os.environ.get("REDIS_URL") or os.environ.get("E2E_REDIS_URL")


@pytest.mark.asyncio
async def test_redis_fanout_delivers_to_local_subscriber() -> None:
    redis_url = _redis_url()
    if not redis_url:
        pytest.skip("Redis URL not configured")

    fanout = RedisRealtimeFanOut(redis_url)
    adapter_a = RealtimeNotificationAdapter(fanout)
    adapter_b = RealtimeNotificationAdapter(fanout)
    await fanout.start()
    await adapter_a.start()
    await adapter_b.start()

    try:
        queue = await adapter_b.subscribe("run_redis")
        event = DashboardEvent(
            event_type="run_created",
            run_id="run_redis",
            system_code="hom",
            run_status=RunStatus.PENDING,
            payload={"run_id": "run_redis"},
        )
        await adapter_a.publish(event)

        received = await asyncio.wait_for(queue.get(), timeout=3.0)
        assert received.run_id == "run_redis"
        assert received.event_type == "run_created"
    finally:
        await fanout.stop()
