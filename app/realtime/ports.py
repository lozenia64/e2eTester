"""실시간 알림(WebSocket fan-out) 포트."""

from __future__ import annotations

import asyncio
from typing import Protocol

from app.core.models import DashboardEvent


class RealtimeNotificationPort(Protocol):
    """Run 대시보드 WebSocket 이벤트의 프로세스-로컬 fan-out 경계.

    리스너 큐는 살아있는 WebSocket 연결에 묶인 휘발성 상태이므로 영속 저장소와 분리한다.
    """

    async def publish(self, event: DashboardEvent) -> None: ...
    async def subscribe(self, run_id: str) -> asyncio.Queue[DashboardEvent]: ...
    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[DashboardEvent]) -> None: ...
