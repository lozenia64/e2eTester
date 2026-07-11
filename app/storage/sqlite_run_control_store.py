from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.core.models import PendingExecution


class SqliteRunControlStore:
    """``RunControlStorePort`` 의 SQLite **컬럼형** 어댑터(기본 사용).

    Run blob(``JsonTableStore``)과 달리, 제어 상태를 JSON 문서 하나로 통째 저장하지 않고
    ``run_control`` 테이블의 **개별 컬럼**으로 둔다. 그래야 취소 플래그(``cancel_requested``)와
    재개 컨텍스트(``session_id``/``resume_index``/...)를 **서로 다른 컬럼만 갱신**해, 실행 중
    취소와 OTP 일시정지 기록이 같은 행을 통째로 덮어써 서로의 값을 잃는 일(lost-update)을 막는다.

    표준 라이브러리 ``sqlite3`` 를 ``asyncio.to_thread`` 로 감싸 별도 의존성 없이 동작하며,
    WAL 모드라 같은 DB 파일을 쓰는 다른 커넥션과 공존한다.
    """

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS run_control ("
            "run_id TEXT PRIMARY KEY, "
            "cancel_requested INTEGER NOT NULL DEFAULT 0, "
            "session_id TEXT, "
            "execution_mode TEXT, "
            "resume_index INTEGER, "
            "pending_module_id TEXT, "
            "paused_at TEXT)"
        )
        # 레거시 테이블(paused_at 컬럼 이전 생성) 마이그레이션 — 이미 있으면 무시.
        try:
            self._conn.execute("ALTER TABLE run_control ADD COLUMN paused_at TEXT")
        except sqlite3.OperationalError:
            pass
        self._conn.commit()
        self._lock = asyncio.Lock()

    async def set_cancel_requested(self, run_id: str) -> None:
        # cancel_requested 컬럼만 건드린다(재개 컨텍스트 컬럼은 보존).
        await self._run(
            "INSERT INTO run_control (run_id, cancel_requested) VALUES (?, 1) "
            "ON CONFLICT(run_id) DO UPDATE SET cancel_requested = 1",
            (run_id,),
        )

    async def is_cancel_requested(self, run_id: str) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self._is_cancel_sync, run_id)

    def _is_cancel_sync(self, run_id: str) -> bool:
        cursor = self._conn.execute(
            "SELECT cancel_requested FROM run_control WHERE run_id = ?", (run_id,)
        )
        row = cursor.fetchone()
        return bool(row[0]) if row else False

    async def set_pending(
        self,
        run_id: str,
        session_id: str,
        execution_mode: str,
        resume_index: int,
        module_id: str,
    ) -> None:
        # 재개 컨텍스트 컬럼만 건드린다(cancel_requested 는 보존). paused_at 은 이 기록 시점
        # = OTP 대기 진입 시각을 스토어가 스탬프한다(인메모리 어댑터와 동일 규약).
        await self._run(
            "INSERT INTO run_control "
            "(run_id, session_id, execution_mode, resume_index, pending_module_id, paused_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET "
            "session_id = excluded.session_id, "
            "execution_mode = excluded.execution_mode, "
            "resume_index = excluded.resume_index, "
            "pending_module_id = excluded.pending_module_id, "
            "paused_at = excluded.paused_at",
            (
                run_id,
                session_id,
                execution_mode,
                resume_index,
                module_id,
                datetime.now(UTC).isoformat(),
            ),
        )

    async def get_pending(self, run_id: str) -> PendingExecution | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_pending_sync, run_id)

    def _get_pending_sync(self, run_id: str) -> PendingExecution | None:
        cursor = self._conn.execute(
            "SELECT session_id, execution_mode, resume_index, pending_module_id, paused_at "
            "FROM run_control WHERE run_id = ?",
            (run_id,),
        )
        row = cursor.fetchone()
        if not row or row[0] is None:
            return None
        return PendingExecution(
            session_id=row[0],
            execution_mode=row[1],
            resume_index=row[2],
            module_id=row[3],
            paused_at=datetime.fromisoformat(row[4]) if row[4] else None,
        )

    async def clear_pending(self, run_id: str) -> None:
        await self._run(
            "UPDATE run_control SET session_id = NULL, execution_mode = NULL, "
            "resume_index = NULL, pending_module_id = NULL, paused_at = NULL WHERE run_id = ?",
            (run_id,),
        )

    async def delete(self, run_id: str) -> None:
        await self._run("DELETE FROM run_control WHERE run_id = ?", (run_id,))

    async def _run(self, sql: str, params: tuple) -> None:
        async with self._lock:
            await asyncio.to_thread(self._exec_commit, sql, params)

    def _exec_commit(self, sql: str, params: tuple) -> None:
        self._conn.execute(sql, params)
        self._conn.commit()
