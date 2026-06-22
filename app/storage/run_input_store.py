from __future__ import annotations

import asyncio


class InMemoryRunInputStore:
    """``RunInputStorePort`` 의 휘발성 어댑터(Phase 1 기본).

    Run 의 해석된 입력값(PII)을 프로세스 메모리에만 보관한다 — 오늘 ``RunService`` 의
    ``_run_inputs`` dict 와 동일한 내구성이되, 포트 뒤로 옮겨 입력값을 단일 경계로 모은다.
    재기동 후 rerun 까지 필요하면 암호화 SQLite 어댑터로 교체한다(Phase 2). 보관 시 복사본을
    두어 호출자 쪽 변경(예: 실행 루프의 input_data 변형)이 저장본을 오염시키지 않게 한다.
    """

    def __init__(self) -> None:
        self._inputs: dict[str, dict[str, str]] = {}
        self._lock = asyncio.Lock()

    async def put(self, run_id: str, input_data: dict[str, str]) -> None:
        async with self._lock:
            self._inputs[run_id] = dict(input_data)

    async def get(self, run_id: str) -> dict[str, str] | None:
        async with self._lock:
            stored = self._inputs.get(run_id)
            return dict(stored) if stored is not None else None

    async def delete(self, run_id: str) -> None:
        async with self._lock:
            self._inputs.pop(run_id, None)
