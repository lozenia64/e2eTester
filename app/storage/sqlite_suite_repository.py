from __future__ import annotations

from app.core.suite_models import SuiteRun
from app.storage.records import SuiteRecord
from app.storage.sqlite_support import JsonTableStore


class SqliteSuiteRepository:
    """SuiteRun 을 SQLite 에 영속하는 ``SuiteReadRepositoryPort`` 어댑터."""

    def __init__(self, db_path: str) -> None:
        self._store = JsonTableStore(db_path, "suites")

    async def get_suite(self, suite_id: str) -> SuiteRun:
        data = await self._store.get(suite_id)
        if data is None:
            raise KeyError(suite_id)
        return SuiteRecord.deserialize(data)

    async def list_suites(self) -> list[SuiteRun]:
        return [SuiteRecord.deserialize(data) for data in await self._store.list_all()]

    async def list_suites_by_user(self, user_id: str) -> list[SuiteRun]:
        return [suite for suite in await self.list_suites() if suite.created_by_user_id == user_id]
