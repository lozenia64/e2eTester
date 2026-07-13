"""SQLite 연결 PRAGMA SSOT — WAL·busy_timeout 등 프로덕션 embedded DB 권장 설정."""

from __future__ import annotations

import sqlite3


def apply_sqlite_pragmas(conn: sqlite3.Connection) -> None:
    """모든 SQLite 연결에 동일 PRAGMA 를 적용한다.

    WAL + busy_timeout 은 동일 ``E2E_DB_PATH`` 를 여러 프로세스/worktree 가 공유할 때
    짧은 lock 경합을 완화한다. 다중 writer 는 여전히 피해야 한다(문서 참고).
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
