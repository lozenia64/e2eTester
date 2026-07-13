from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.core.run_models import PendingExecution


class InMemoryRunControlStore:
    """``RunControlStorePort`` 의 인메모리 어댑터(테스트·기본 대체용).

    SQLite 어댑터와 동작이 같도록, 취소 플래그와 pending(재개) 컨텍스트를 분리해 보관한다.
    프로세스-로컬이라 재기동 후에는 비어 있다(SQLite 어댑터를 쓰면 영속).
    """

    def __init__(self) -> None:
        self._cancel: set[str] = set()
        self._pending: dict[str, PendingExecution] = {}
        self._lock = asyncio.Lock()

    async def set_cancel_requested(self, run_id: str) -> None:
        async with self._lock:
            self._cancel.add(run_id)

    async def is_cancel_requested(self, run_id: str) -> bool:
        async with self._lock:
            return run_id in self._cancel

    async def set_pending(
        self,
        run_id: str,
        session_id: str,
        execution_mode: str,
        resume_index: int,
        module_id: str,
    ) -> None:
        async with self._lock:
            self._pending[run_id] = PendingExecution(
                session_id=session_id,
                execution_mode=execution_mode,
                resume_index=resume_index,
                module_id=module_id,
                # 기록 시점 = OTP 대기 진입 시각(SQLite 어댑터와 동일 규약).
                paused_at=datetime.now(UTC),
            )

    async def get_pending(self, run_id: str) -> PendingExecution | None:
        async with self._lock:
            return self._pending.get(run_id)

    async def clear_pending(self, run_id: str) -> None:
        async with self._lock:
            self._pending.pop(run_id, None)

    async def delete(self, run_id: str) -> None:
        async with self._lock:
            self._cancel.discard(run_id)
            self._pending.pop(run_id, None)
