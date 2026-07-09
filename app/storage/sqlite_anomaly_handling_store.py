from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

from app.core.enums import AnomalyState
from app.core.models import AnomalyHandling


class SqliteAnomalyHandlingStore:
    """``AnomalyHandlingStorePort`` 의 SQLite **컬럼형** 어댑터(기본 사용).

    이상징후 인박스의 처리 레코드(상태·담당자·메모)를 ``module_run_id`` 키의 개별 컬럼으로
    보관한다. ``RunControlStorePort`` 어댑터와 동일하게 표준 라이브러리 ``sqlite3`` 를
    ``asyncio.to_thread`` 로 감싸 별도 의존성 없이 동작하며, WAL 모드로 같은 DB 파일을 쓰는
    다른 커넥션과 공존한다.
    """

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS anomaly_handling ("
            "module_run_id TEXT PRIMARY KEY, "
            "state TEXT NOT NULL DEFAULT 'UNRESOLVED', "
            "assignee_user_id TEXT, "
            "assignee_name TEXT, "
            "memo TEXT NOT NULL DEFAULT '', "
            "updated_at TEXT, "
            "updated_by_user_id TEXT)"
        )
        self._conn.commit()
        self._lock = asyncio.Lock()

    async def get(self, module_run_id: str) -> AnomalyHandling | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_sync, module_run_id)

    def _get_sync(self, module_run_id: str) -> AnomalyHandling | None:
        cursor = self._conn.execute(
            "SELECT module_run_id, state, assignee_user_id, assignee_name, memo, "
            "updated_at, updated_by_user_id FROM anomaly_handling WHERE module_run_id = ?",
            (module_run_id,),
        )
        row = cursor.fetchone()
        return self._row_to_model(row) if row else None

    async def list(self) -> list[AnomalyHandling]:
        async with self._lock:
            return await asyncio.to_thread(self._list_sync)

    def _list_sync(self) -> list[AnomalyHandling]:
        cursor = self._conn.execute(
            "SELECT module_run_id, state, assignee_user_id, assignee_name, memo, "
            "updated_at, updated_by_user_id FROM anomaly_handling"
        )
        return [self._row_to_model(row) for row in cursor.fetchall()]

    async def upsert(self, handling: AnomalyHandling) -> AnomalyHandling:
        async with self._lock:
            await asyncio.to_thread(self._upsert_sync, handling)
        return handling

    def _upsert_sync(self, handling: AnomalyHandling) -> None:
        updated_at = handling.updated_at.isoformat() if handling.updated_at else None
        self._conn.execute(
            "INSERT INTO anomaly_handling "
            "(module_run_id, state, assignee_user_id, assignee_name, memo, "
            "updated_at, updated_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(module_run_id) DO UPDATE SET "
            "state = excluded.state, "
            "assignee_user_id = excluded.assignee_user_id, "
            "assignee_name = excluded.assignee_name, "
            "memo = excluded.memo, "
            "updated_at = excluded.updated_at, "
            "updated_by_user_id = excluded.updated_by_user_id",
            (
                handling.module_run_id,
                str(handling.state),
                handling.assignee_user_id,
                handling.assignee_name,
                handling.memo,
                updated_at,
                handling.updated_by_user_id,
            ),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_model(row: tuple) -> AnomalyHandling:
        return AnomalyHandling(
            module_run_id=row[0],
            state=AnomalyState(row[1]) if row[1] else AnomalyState.UNRESOLVED,
            assignee_user_id=row[2],
            assignee_name=row[3],
            memo=row[4] or "",
            updated_at=datetime.fromisoformat(row[5]) if row[5] else None,
            updated_by_user_id=row[6],
        )
