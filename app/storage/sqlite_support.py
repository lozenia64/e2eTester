from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = "data/e2etester.db"


class JsonTableStore:
    """단일 JSON blob 테이블(``id`` PK + ``data``) 위의 비동기 영속 저장 헬퍼.

    표준 라이브러리 ``sqlite3`` 를 ``asyncio.to_thread`` 로 감싸 별도 의존성 없이 동작한다.
    이 도구는 단일 프로세스·저부하이므로 커넥션 1개 + ``asyncio.Lock`` 으로 접근을 직렬화한다.
    저장 모델은 모두 Pydantic 이라 본문은 ``model_dump_json`` 결과(JSON 문자열)를 그대로 담고,
    조회 시 ``model_validate_json`` 으로 복원한다(테이블당 인덱스 컬럼은 ``id`` PK 하나로 충분).

    ``table`` 은 코드 내부 상수이며 외부 입력이 아니므로 식별자 보간은 안전하다.
    """

    def __init__(self, db_path: str | Path, table: str) -> None:
        self._table = table
        path = Path(db_path)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, data TEXT NOT NULL)"
        )
        self._conn.commit()
        self._lock = asyncio.Lock()

    async def upsert(self, key: str, data: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._upsert_sync, key, data)

    def _upsert_sync(self, key: str, data: str) -> None:
        self._conn.execute(
            f"INSERT INTO {self._table} (id, data) VALUES (?, ?) "
            f"ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            (key, data),
        )
        self._conn.commit()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_sync, key)

    def _get_sync(self, key: str) -> str | None:
        cursor = self._conn.execute(
            f"SELECT data FROM {self._table} WHERE id = ?", (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    async def list_all(self) -> list[str]:
        async with self._lock:
            return await asyncio.to_thread(self._list_sync)

    def _list_sync(self) -> list[str]:
        cursor = self._conn.execute(f"SELECT data FROM {self._table}")
        return [row[0] for row in cursor.fetchall()]

    async def delete(self, key: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._delete_sync, key)

    def _delete_sync(self, key: str) -> None:
        self._conn.execute(f"DELETE FROM {self._table} WHERE id = ?", (key,))
        self._conn.commit()
