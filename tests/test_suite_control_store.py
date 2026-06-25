"""Suite 제어 스토어(취소 의도) 단위 테스트 — 인메모리·SQLite 어댑터 동작 동일성."""

from __future__ import annotations

import asyncio

from app.storage.sqlite_suite_control_store import SqliteSuiteControlStore
from app.storage.suite_control_store import InMemorySuiteControlStore


def _exercise(store) -> None:
    async def scenario():
        assert await store.is_cancel_requested("suite_1") is False
        await store.set_cancel_requested("suite_1")
        assert await store.is_cancel_requested("suite_1") is True
        # 다른 Suite 는 영향받지 않는다.
        assert await store.is_cancel_requested("suite_2") is False
        await store.delete("suite_1")
        assert await store.is_cancel_requested("suite_1") is False

    asyncio.run(scenario())


def test_in_memory_suite_control_store():
    _exercise(InMemorySuiteControlStore())


def test_sqlite_suite_control_store(tmp_path):
    _exercise(SqliteSuiteControlStore(tmp_path / "suite_control.db"))
