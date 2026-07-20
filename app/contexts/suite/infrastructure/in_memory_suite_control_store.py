from __future__ import annotations

import asyncio


class InMemorySuiteControlStore:
    """``SuiteControlStorePort`` 의 인메모리 어댑터(테스트·기본 대체용).

    프로세스-로컬이라 재기동 후에는 비어 있다(SQLite 어댑터를 쓰면 영속).
    """

    def __init__(self) -> None:
        self._cancel: set[str] = set()
        self._lock = asyncio.Lock()

    async def set_cancel_requested(self, suite_id: str) -> None:
        async with self._lock:
            self._cancel.add(suite_id)

    async def is_cancel_requested(self, suite_id: str) -> bool:
        async with self._lock:
            return suite_id in self._cancel

    async def delete(self, suite_id: str) -> None:
        async with self._lock:
            self._cancel.discard(suite_id)
