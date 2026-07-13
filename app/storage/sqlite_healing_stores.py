from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from app.contexts.healing.models import (
    GLOBAL_POLICY_CODE,
    HealingAction,
    HealingEvent,
    HealingPatch,
    HealingPolicy,
    PatchStatus,
    ResolvedHealingPolicy,
)
from app.storage.sqlite_pragmas import apply_sqlite_pragmas


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    apply_sqlite_pragmas(conn)
    return conn


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _parse(moment: str | None) -> datetime | None:
    return datetime.fromisoformat(moment) if moment else None


class SqliteHealingEventStore:
    """``HealingEventStorePort`` 의 SQLite **컬럼형** 어댑터(기본 사용, append-only)."""

    def __init__(self, db_path: str | Path) -> None:
        self._conn = _connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS healing_events ("
            "event_id TEXT PRIMARY KEY, "
            "run_id TEXT NOT NULL, "
            "module_id TEXT NOT NULL, "
            "system_code TEXT NOT NULL, "
            "module_name TEXT NOT NULL DEFAULT '', "
            "workflow_step TEXT, "
            "broken_selector TEXT NOT NULL, "
            "healed_selector TEXT, "
            "strategy TEXT NOT NULL DEFAULT '', "
            "confidence REAL NOT NULL DEFAULT 0, "
            "action TEXT NOT NULL, "
            "retry_succeeded INTEGER, "
            "candidates_considered INTEGER NOT NULL DEFAULT 0, "
            "error_excerpt TEXT NOT NULL DEFAULT '', "
            "page_url TEXT, "
            "duration_ms INTEGER NOT NULL DEFAULT 0, "
            "created_at TEXT NOT NULL)"
        )
        self._conn.commit()
        self._lock = asyncio.Lock()

    async def append(self, event: HealingEvent) -> HealingEvent:
        async with self._lock:
            await asyncio.to_thread(self._append_sync, event)
        return event

    def _append_sync(self, event: HealingEvent) -> None:
        self._conn.execute(
            "INSERT INTO healing_events (event_id, run_id, module_id, system_code, "
            "module_name, workflow_step, broken_selector, healed_selector, strategy, confidence, "
            "action, retry_succeeded, candidates_considered, error_excerpt, page_url, duration_ms, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.run_id,
                event.module_id,
                event.system_code,
                event.module_name,
                event.workflow_step,
                event.broken_selector,
                event.healed_selector,
                event.strategy,
                event.confidence,
                str(event.action.value),
                None if event.retry_succeeded is None else int(event.retry_succeeded),
                event.candidates_considered,
                event.error_excerpt,
                event.page_url,
                event.duration_ms,
                event.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    async def list(self, limit: int | None = None) -> list[HealingEvent]:
        async with self._lock:
            return await asyncio.to_thread(self._list_sync, limit)

    def _list_sync(self, limit: int | None) -> list[HealingEvent]:
        sql = (
            "SELECT event_id, run_id, module_id, system_code, module_name, workflow_step, "
            "broken_selector, healed_selector, strategy, confidence, action, retry_succeeded, "
            "candidates_considered, error_excerpt, page_url, duration_ms, created_at "
            "FROM healing_events ORDER BY created_at DESC"
        )
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return [self._row_to_event(row) for row in self._conn.execute(sql, params).fetchall()]

    @staticmethod
    def _row_to_event(row: tuple) -> HealingEvent:
        return HealingEvent(
            event_id=row[0],
            run_id=row[1],
            module_id=row[2],
            system_code=row[3],
            module_name=row[4] or "",
            workflow_step=row[5],
            broken_selector=row[6],
            healed_selector=row[7],
            strategy=row[8] or "",
            confidence=row[9] or 0.0,
            action=HealingAction(row[10]),
            retry_succeeded=None if row[11] is None else bool(row[11]),
            candidates_considered=row[12] or 0,
            error_excerpt=row[13] or "",
            page_url=row[14],
            duration_ms=row[15] or 0,
            created_at=datetime.fromisoformat(row[16]),
        )


_POLICY_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS healing_policy ("
    "system_code TEXT PRIMARY KEY, "
    "auto_heal_enabled INTEGER NOT NULL DEFAULT 1, "
    "confidence_threshold REAL NOT NULL, "
    "updated_at TEXT, "
    "updated_by TEXT)"
)


class SqliteHealingPolicyStore:
    """``HealingPolicyStorePort`` 의 SQLite 컬럼형 어댑터(대시보드 정책 패널의 쓰기 경로)."""

    def __init__(self, db_path: str | Path) -> None:
        self._conn = _connect(db_path)
        self._conn.execute(_POLICY_TABLE_DDL)
        self._conn.commit()
        self._lock = asyncio.Lock()

    async def list(self) -> list[HealingPolicy]:
        async with self._lock:
            return await asyncio.to_thread(self._list_sync)

    def _list_sync(self) -> list[HealingPolicy]:
        rows = self._conn.execute(
            "SELECT system_code, auto_heal_enabled, confidence_threshold, updated_at, updated_by "
            "FROM healing_policy"
        ).fetchall()
        return [
            HealingPolicy(
                system_code=row[0],
                auto_heal_enabled=bool(row[1]),
                confidence_threshold=row[2],
                updated_at=_parse(row[3]),
                updated_by=row[4],
            )
            for row in rows
        ]

    async def upsert(self, policy: HealingPolicy) -> HealingPolicy:
        async with self._lock:
            await asyncio.to_thread(self._upsert_sync, policy)
        return policy

    def _upsert_sync(self, policy: HealingPolicy) -> None:
        self._conn.execute(
            "INSERT INTO healing_policy (system_code, auto_heal_enabled, confidence_threshold, "
            "updated_at, updated_by) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(system_code) DO UPDATE SET "
            "auto_heal_enabled = excluded.auto_heal_enabled, "
            "confidence_threshold = excluded.confidence_threshold, "
            "updated_at = excluded.updated_at, "
            "updated_by = excluded.updated_by",
            (
                policy.system_code,
                int(policy.auto_heal_enabled),
                policy.confidence_threshold,
                _iso(policy.updated_at),
                policy.updated_by,
            ),
        )
        self._conn.commit()


class SqliteHealingPolicyReader:
    """실행 스레드(게이트웨이 세션 풀)에서 **동기** 호출되는 정책 스냅샷 리더.

    비동기 스토어(``SqliteHealingPolicyStore``)와 같은 테이블을 자기 커넥션으로 읽는다
    (WAL 모드 공존). 여러 실행 스레드가 동시에 부르므로 ``threading.Lock`` 으로 직렬화하고,
    치유는 실패 경로에서만 일어나는 저빈도 조회라 짧은 TTL 캐시(5초)면 충분하다.
    시스템별 행 → ``*`` 전역 행 → 코드 기본값 순으로 해석한다.
    """

    _TTL_SECONDS = 5.0

    def __init__(self, db_path: str | Path) -> None:
        self._conn = _connect(db_path)
        self._conn.execute(_POLICY_TABLE_DDL)
        self._conn.commit()
        self._lock = threading.Lock()
        self._cache: dict[str, ResolvedHealingPolicy] = {}
        self._cache_at = 0.0

    def resolve(self, system_code: str) -> ResolvedHealingPolicy:
        with self._lock:
            if time.monotonic() - self._cache_at > self._TTL_SECONDS:
                self._reload()
            return (
                self._cache.get(system_code)
                or self._cache.get(GLOBAL_POLICY_CODE)
                or ResolvedHealingPolicy()
            )

    def _reload(self) -> None:
        rows = self._conn.execute(
            "SELECT system_code, auto_heal_enabled, confidence_threshold FROM healing_policy"
        ).fetchall()
        self._cache = {
            row[0]: ResolvedHealingPolicy(enabled=bool(row[1]), threshold=row[2]) for row in rows
        }
        self._cache_at = time.monotonic()


class SqliteHealingPatchStore:
    """``HealingPatchStorePort`` 의 SQLite 컬럼형 어댑터(승인 대기 패치 + 감사 이력)."""

    def __init__(self, db_path: str | Path) -> None:
        self._conn = _connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS healing_patches ("
            "patch_id TEXT PRIMARY KEY, "
            "event_id TEXT NOT NULL, "
            "run_id TEXT NOT NULL DEFAULT '', "
            "system_code TEXT NOT NULL, "
            "broken_selector TEXT NOT NULL, "
            "healed_selector TEXT NOT NULL, "
            "file_path TEXT NOT NULL, "
            "occurrences INTEGER NOT NULL DEFAULT 1, "
            "diff TEXT NOT NULL DEFAULT '', "
            "warnings TEXT NOT NULL DEFAULT '', "
            "status TEXT NOT NULL DEFAULT 'PROPOSED', "
            "created_at TEXT NOT NULL, "
            "decided_at TEXT, "
            "decided_by TEXT, "
            "applied INTEGER NOT NULL DEFAULT 0, "
            "note TEXT NOT NULL DEFAULT '')"
        )
        self._conn.commit()
        self._lock = asyncio.Lock()

    async def add(self, patch: HealingPatch) -> HealingPatch:
        async with self._lock:
            await asyncio.to_thread(self._write_sync, patch)
        return patch

    async def update(self, patch: HealingPatch) -> HealingPatch:
        async with self._lock:
            await asyncio.to_thread(self._write_sync, patch)
        return patch

    def _write_sync(self, patch: HealingPatch) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO healing_patches (patch_id, event_id, run_id, system_code, "
            "broken_selector, healed_selector, file_path, occurrences, diff, warnings, status, "
            "created_at, decided_at, decided_by, applied, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                patch.patch_id,
                patch.event_id,
                patch.run_id,
                patch.system_code,
                patch.broken_selector,
                patch.healed_selector,
                patch.file_path,
                patch.occurrences,
                patch.diff,
                "\n".join(patch.warnings),
                str(patch.status.value),
                patch.created_at.isoformat(),
                _iso(patch.decided_at),
                patch.decided_by,
                int(patch.applied),
                patch.note,
            ),
        )
        self._conn.commit()

    async def get(self, patch_id: str) -> HealingPatch:
        async with self._lock:
            patch = await asyncio.to_thread(self._get_sync, patch_id)
        if patch is None:
            raise KeyError(patch_id)
        return patch

    def _get_sync(self, patch_id: str) -> HealingPatch | None:
        row = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM healing_patches WHERE patch_id = ?", (patch_id,)
        ).fetchone()
        return self._row_to_patch(row) if row else None

    async def list(self) -> list[HealingPatch]:
        async with self._lock:
            return await asyncio.to_thread(self._list_sync)

    def _list_sync(self) -> list[HealingPatch]:
        rows = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM healing_patches ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_patch(row) for row in rows]

    _COLUMNS = (
        "patch_id, event_id, run_id, system_code, broken_selector, healed_selector, file_path, "
        "occurrences, diff, warnings, status, created_at, decided_at, decided_by, applied, note"
    )

    @staticmethod
    def _row_to_patch(row: tuple) -> HealingPatch:
        return HealingPatch(
            patch_id=row[0],
            event_id=row[1],
            run_id=row[2] or "",
            system_code=row[3],
            broken_selector=row[4],
            healed_selector=row[5],
            file_path=row[6],
            occurrences=row[7] or 1,
            diff=row[8] or "",
            warnings=[w for w in (row[9] or "").split("\n") if w],
            status=PatchStatus(row[10]),
            created_at=datetime.fromisoformat(row[11]),
            decided_at=_parse(row[12]),
            decided_by=row[13],
            applied=bool(row[14]),
            note=row[15] or "",
        )
