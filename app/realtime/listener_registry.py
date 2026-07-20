from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Generic, TypeVar

E = TypeVar("E")


class ListenerRegistry(Generic[E]):
    """key(run_id/suite_id) 별 WebSocket 리스너 큐 레지스트리.

    리스너 큐는 살아있는 WebSocket 연결에 묶인 프로세스-로컬 상태이므로 영속화 대상이
    아니다. 인메모리/SQLite 저장소가 공통으로 쓰는 휘발성 fan-out 구현을 한곳에 모은다.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[asyncio.Queue[E]]] = defaultdict(list)

    async def publish(self, key: str, event: E) -> None:
        for queue in list(self._listeners.get(key, [])):
            await queue.put(event)

    async def subscribe(self, key: str) -> asyncio.Queue[E]:
        queue: asyncio.Queue[E] = asyncio.Queue()
        self._listeners[key].append(queue)
        return queue

    async def unsubscribe(self, key: str, queue: asyncio.Queue[E]) -> None:
        listeners = self._listeners.get(key, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners and key in self._listeners:
            del self._listeners[key]
