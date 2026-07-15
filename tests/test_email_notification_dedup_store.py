import pytest

from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.storage.sqlite_email_notification_dedup import SqliteEmailNotificationDedupStore


@pytest.mark.asyncio
async def test_email_notification_dedup_store_claims_once(tmp_path):
    db = SqliteDatabase(tmp_path / "dedup.db")
    await ensure_schema(db)
    store = SqliteEmailNotificationDedupStore(db)
    assert await store.try_claim_run("run_1") is True
    assert await store.try_claim_run("run_1") is False
    await store.release_run("run_1")
    assert await store.try_claim_run("run_1") is True
