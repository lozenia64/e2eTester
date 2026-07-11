from __future__ import annotations

import asyncio
import os
import socket

from app.execution.redis_session_registry import RedisSessionRegistry


class SessionHeartbeatManager:
    """워커 세션의 Redis 리스·하트비트를 관리한다."""

    def __init__(
        self,
        registry: RedisSessionRegistry,
        *,
        worker_id: str | None = None,
        interval_seconds: float = 15.0,
    ) -> None:
        self._registry = registry
        self._worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self._interval = interval_seconds
        self._active_sessions: set[str] = set()
        self._task: asyncio.Task | None = None

    @property
    def worker_id(self) -> str:
        return self._worker_id

    async def register(self, session_id: str, *, run_id: str, execution_mode: str) -> None:
        await self._registry.register(
            session_id,
            worker_id=self._worker_id,
            run_id=run_id,
            execution_mode=execution_mode,
        )
        self._active_sessions.add(session_id)
        if self._task is None:
            self._task = asyncio.create_task(self._heartbeat_loop())

    async def heartbeat(self, session_id: str) -> bool:
        return await self._registry.heartbeat(session_id)

    async def unregister(self, session_id: str) -> None:
        self._active_sessions.discard(session_id)
        await self._registry.unregister(session_id)

    async def _heartbeat_loop(self) -> None:
        while self._active_sessions:
            for session_id in list(self._active_sessions):
                alive = await self._registry.heartbeat(session_id)
                if not alive:
                    self._active_sessions.discard(session_id)
            await asyncio.sleep(self._interval)
        self._task = None

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        for session_id in list(self._active_sessions):
            await self._registry.unregister(session_id)
        self._active_sessions.clear()
