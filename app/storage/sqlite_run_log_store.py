from __future__ import annotations

import asyncio
import sqlite3
from collections import defaultdict
from pathlib import Path


class SqliteRunLogStore:
    """``RunLogStorePort`` 의 SQLite append-only 어댑터(기본 사용).

    모듈 로그를 ``run_logs`` 테이블에 한 줄당 한 행으로 **추가만** 한다. Run blob 처럼
    문서를 통째로 다시 쓰지 않으므로 한 줄 기록이 O(1) INSERT 다(핫패스 쓰기 증폭 제거).
    ``id`` 오토인크리먼트가 곧 삽입(=시간) 순서이므로, 조회는 ``ORDER BY id`` 로 입력 순서를
    그대로 복원한다.

    표준 라이브러리 ``sqlite3`` 를 ``asyncio.to_thread`` 로 감싸 별도 의존성 없이 동작하며,
    WAL 모드라 같은 DB 파일을 쓰는 다른 커넥션(``JsonTableStore`` 등)과 공존한다.
    """

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS run_logs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "run_id TEXT NOT NULL, "
            "module_id TEXT NOT NULL, "
            "line TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_run_logs_run_module ON run_logs(run_id, module_id, id)"
        )
        self._conn.commit()
        self._lock = asyncio.Lock()

    async def append(self, run_id: str, module_id: str, line: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._append_sync, run_id, module_id, line)

    def _append_sync(self, run_id: str, module_id: str, line: str) -> None:
        self._conn.execute(
            "INSERT INTO run_logs (run_id, module_id, line) VALUES (?, ?, ?)",
            (run_id, module_id, line),
        )
        self._conn.commit()

    async def get(self, run_id: str, module_id: str) -> list[str]:
        async with self._lock:
            return await asyncio.to_thread(self._get_sync, run_id, module_id)

    def _get_sync(self, run_id: str, module_id: str) -> list[str]:
        cursor = self._conn.execute(
            "SELECT line FROM run_logs WHERE run_id = ? AND module_id = ? ORDER BY id",
            (run_id, module_id),
        )
        return [row[0] for row in cursor.fetchall()]

    async def get_all(self, run_id: str) -> dict[str, list[str]]:
        async with self._lock:
            return await asyncio.to_thread(self._get_all_sync, run_id)

    def _get_all_sync(self, run_id: str) -> dict[str, list[str]]:
        cursor = self._conn.execute(
            "SELECT module_id, line FROM run_logs WHERE run_id = ? ORDER BY id",
            (run_id,),
        )
        grouped: dict[str, list[str]] = defaultdict(list)
        for module_id, line in cursor.fetchall():
            grouped[module_id].append(line)
        return dict(grouped)
