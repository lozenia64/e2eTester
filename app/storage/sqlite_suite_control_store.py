from __future__ import annotations

import asyncio
from pathlib import Path

from app.platform.sqlite_connection import connect_sqlite


class SqliteSuiteControlStore:
    """``SuiteControlStorePort`` 의 SQLite 어댑터(기본 사용).

    ``suite_control`` 테이블에 Suite 취소 의도를 영속한다(``SqliteRunControlStore`` 의 취소
    컬럼과 같은 방식). 표준 라이브러리 ``sqlite3`` 를 ``asyncio.to_thread`` 로 감싸 별도
    의존성 없이 동작하며, WAL 모드라 같은 DB 파일을 쓰는 다른 커넥션과 공존한다.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._conn = connect_sqlite(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS suite_control ("
            "suite_id TEXT PRIMARY KEY, "
            "cancel_requested INTEGER NOT NULL DEFAULT 0)"
        )
        self._conn.commit()
        self._lock = asyncio.Lock()

    async def set_cancel_requested(self, suite_id: str) -> None:
        await self._run(
            "INSERT INTO suite_control (suite_id, cancel_requested) VALUES (?, 1) "
            "ON CONFLICT(suite_id) DO UPDATE SET cancel_requested = 1",
            (suite_id,),
        )

    async def is_cancel_requested(self, suite_id: str) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self._is_cancel_sync, suite_id)

    def _is_cancel_sync(self, suite_id: str) -> bool:
        cursor = self._conn.execute(
            "SELECT cancel_requested FROM suite_control WHERE suite_id = ?", (suite_id,)
        )
        row = cursor.fetchone()
        return bool(row[0]) if row else False

    async def delete(self, suite_id: str) -> None:
        await self._run("DELETE FROM suite_control WHERE suite_id = ?", (suite_id,))

    async def _run(self, sql: str, params: tuple) -> None:
        async with self._lock:
            await asyncio.to_thread(self._exec_commit, sql, params)

    def _exec_commit(self, sql: str, params: tuple) -> None:
        self._conn.execute(sql, params)
        self._conn.commit()
