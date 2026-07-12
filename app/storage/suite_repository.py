from __future__ import annotations

import asyncio

from app.core.suite_models import SuiteRun
from app.storage.records import SuiteRecord


class InMemorySuiteRepository:
    """``SuiteReadRepositoryPort`` 의 인메모리 어댑터(서버 재시작 시 휘발)."""

    def __init__(self) -> None:
        self._suites: dict[str, SuiteRecord] = {}
        self._lock = asyncio.Lock()

    async def get_suite(self, suite_id: str) -> SuiteRun:
        async with self._lock:
            return self._suites[suite_id].to_domain()

    async def list_suites(self) -> list[SuiteRun]:
        async with self._lock:
            return [record.to_domain() for record in self._suites.values()]

    async def list_suites_by_user(self, user_id: str) -> list[SuiteRun]:
        return [suite for suite in await self.list_suites() if suite.created_by_user_id == user_id]

    async def _upsert(self, suite: SuiteRun) -> None:
        async with self._lock:
            self._suites[suite.suite_id] = SuiteRecord.from_domain(suite)
