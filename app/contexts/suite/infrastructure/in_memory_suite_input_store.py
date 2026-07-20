from __future__ import annotations

import asyncio


class InMemorySuiteInputStore:
    """``SuiteInputStorePort`` 의 인메모리 어댑터(기본 사용, Phase 1).

    Suite 의 시스템별 입력값을 프로세스-로컬로 보관한다(``InMemoryRunInputStore`` 와 동일한
    휘발성). PII 가 섞일 수 있어 Suite blob/이벤트 payload 로는 직렬화하지 않는다.
    """

    def __init__(self) -> None:
        self._inputs: dict[str, dict[str, dict[str, str]]] = {}
        self._lock = asyncio.Lock()

    async def put(self, suite_id: str, systems_input: dict[str, dict[str, str]]) -> None:
        async with self._lock:
            self._inputs[suite_id] = {key: dict(value) for key, value in systems_input.items()}

    async def get(self, suite_id: str) -> dict[str, dict[str, str]] | None:
        async with self._lock:
            stored = self._inputs.get(suite_id)
            if stored is None:
                return None
            return {key: dict(value) for key, value in stored.items()}

    async def delete(self, suite_id: str) -> None:
        async with self._lock:
            self._inputs.pop(suite_id, None)
