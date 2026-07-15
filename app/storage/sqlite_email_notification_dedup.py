"""Run/Suite 종료 메일 중복 발송 방지 — 프로세스 간 공유 SQLite claim."""

from __future__ import annotations

from datetime import UTC, datetime

from app.eventsourcing.support import SqliteDatabase


class SqliteEmailNotificationDedupStore:
    """``INSERT OR IGNORE`` 로 메일 발송 권한을 원자적으로 선점한다."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def try_claim_run(self, run_id: str) -> bool:
        return await self._try_claim("run", run_id)

    async def try_claim_suite(self, suite_id: str) -> bool:
        return await self._try_claim("suite", suite_id)

    async def release_run(self, run_id: str) -> None:
        await self._release("run", run_id)

    async def release_suite(self, suite_id: str) -> None:
        await self._release("suite", suite_id)

    def try_claim_run_sync(self, run_id: str) -> bool:
        return self._try_claim_sync("run", run_id)

    def try_claim_suite_sync(self, suite_id: str) -> bool:
        return self._try_claim_sync("suite", suite_id)

    def try_claim_sync(self, scope: str, entity_id: str) -> bool:
        return self._try_claim_sync(scope, entity_id)

    def release_run_sync(self, run_id: str) -> None:
        self._release_sync("run", run_id)

    def release_suite_sync(self, suite_id: str) -> None:
        self._release_sync("suite", suite_id)

    def release_sync(self, scope: str, entity_id: str) -> None:
        self._release_sync(scope, entity_id)

    async def _try_claim(self, scope: str, entity_id: str) -> bool:
        claimed_at = datetime.now(UTC).isoformat()
        inserted = await self._db.execute_changes(
            """
            INSERT OR IGNORE INTO email_notification_claims
                (scope, entity_id, claimed_at)
            VALUES (?, ?, ?)
            """,
            (scope, entity_id, claimed_at),
        )
        return inserted == 1

    async def _release(self, scope: str, entity_id: str) -> None:
        await self._db.execute(
            "DELETE FROM email_notification_claims WHERE scope = ? AND entity_id = ?",
            (scope, entity_id),
        )

    def _try_claim_sync(self, scope: str, entity_id: str) -> bool:
        claimed_at = datetime.now(UTC).isoformat()
        inserted = self._db.execute_changes_sync(
            """
            INSERT OR IGNORE INTO email_notification_claims
                (scope, entity_id, claimed_at)
            VALUES (?, ?, ?)
            """,
            (scope, entity_id, claimed_at),
        )
        return inserted == 1

    def _release_sync(self, scope: str, entity_id: str) -> None:
        self._db.execute_changes_sync(
            "DELETE FROM email_notification_claims WHERE scope = ? AND entity_id = ?",
            (scope, entity_id),
        )
