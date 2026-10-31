from __future__ import annotations

from app.contexts.suite.contracts.records import SuiteRecord
from app.core.suite_models import SuiteRun
from app.platform.eventing.support import SqliteDatabase


class SqliteSuiteRepository:
    """``SuiteReadRepositoryPort`` 어댑터 — 스냅샷(이벤트 폴드 파생 캐시)에서 읽는다.

    WP-B6 로 ``suites`` blob 테이블이 폐기됐으므로, Suite 상태의 유일한 저장소인
    ``aggregate_snapshots``(``stream_id = 'Suite:{id}'``)에서 SuiteRun 을 재구성한다.
    """

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db

    async def get_suite(self, suite_id: str) -> SuiteRun:
        row = await self._db.fetchone(
            "SELECT state_json FROM aggregate_snapshots WHERE stream_id = ?",
            (f"Suite:{suite_id}",),
        )
        if row is None:
            raise KeyError(suite_id)
        return SuiteRecord.deserialize(row["state_json"])

    async def list_suites(self) -> list[SuiteRun]:
        rows = await self._db.fetchall(
            "SELECT state_json FROM aggregate_snapshots WHERE aggregate_type = 'Suite'"
        )
        return [SuiteRecord.deserialize(row["state_json"]) for row in rows]
