from __future__ import annotations

import asyncio
from collections import defaultdict


class InMemoryRunLogStore:
    """``RunLogStorePort`` 의 인메모리 어댑터(서버 재시작 시 휘발).

    ``(run_id, module_id)`` 별 append-only 라인 버퍼. 단위 테스트나 영속이 필요 없는
    실행에서 쓴다. 영속이 필요하면 ``SqliteRunLogStore`` 로 교체한다(동일 포트).
    """

    def __init__(self) -> None:
        self._logs: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self._lock = asyncio.Lock()

    async def append(self, run_id: str, module_id: str, line: str) -> None:
        async with self._lock:
            self._logs[run_id][module_id].append(line)

    async def get(self, run_id: str, module_id: str) -> list[str]:
        async with self._lock:
            return list(self._logs[run_id][module_id])

    async def get_all(self, run_id: str) -> dict[str, list[str]]:
        async with self._lock:
            return {module_id: list(lines) for module_id, lines in self._logs.get(run_id, {}).items()}

    async def delete_by_run_id(self, run_id: str) -> None:
        async with self._lock:
            self._logs.pop(run_id, None)
