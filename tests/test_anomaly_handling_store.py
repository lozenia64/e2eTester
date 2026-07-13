"""이상징후 처리 스토어(SqliteAnomalyHandlingStore) 단위 테스트."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import AnomalyState
from app.core.run_models import AnomalyHandling
from app.storage.sqlite_anomaly_handling_store import SqliteAnomalyHandlingStore


async def test_upsert_get_list_and_default_missing(tmp_path):
    store = SqliteAnomalyHandlingStore(tmp_path / "anomaly.db")

    # 없는 키는 None (기본 UNRESOLVED 로 간주하는 정책은 상위 빌더가 담당)
    assert await store.get("r0::login") is None
    assert await store.list() == []

    await store.upsert(
        AnomalyHandling(
            module_run_id="r0::login",
            state=AnomalyState.ACKNOWLEDGED,
            assignee_user_id="u1",
            assignee_name="김담당",
            memo="조사중",
            updated_at=datetime(2026, 7, 9, tzinfo=UTC),
            updated_by_user_id="u9",
        )
    )
    got = await store.get("r0::login")
    assert got is not None
    assert got.state == AnomalyState.ACKNOWLEDGED
    assert got.assignee_name == "김담당"
    assert got.memo == "조사중"
    assert got.updated_by_user_id == "u9"

    # 같은 키 upsert 는 갱신(중복 행 없음)
    await store.upsert(
        AnomalyHandling(module_run_id="r0::login", state=AnomalyState.RESOLVED, memo="완료")
    )
    updated = await store.get("r0::login")
    assert updated.state == AnomalyState.RESOLVED
    assert updated.memo == "완료"
    assert updated.assignee_user_id is None  # 새 레코드로 대체됨
    assert len(await store.list()) == 1
