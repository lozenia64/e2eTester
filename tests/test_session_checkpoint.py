"""Phase C 세션 체크포인트 — 재수화 결정 규칙(순수) + 저장소 왕복."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contexts.run.domain.state_machine import (
    ReplayFromLogin,
    ResumeFromCheckpoint,
    RunStateMachine,
)
from app.eventsourcing.support import SqliteDatabase, ensure_schema
from app.execution.session_checkpoint import (
    InMemorySessionCheckpointStore,
    SessionCheckpoint,
)
from app.storage.sqlite_session_checkpoint_store import SqliteSessionCheckpointStore


def test_rehydration_resumes_from_next_module_when_session_valid():
    decision = RunStateMachine.decide_rehydration(
        checkpoint_module_index=1, storage_state_valid=True, login_module_index=0
    )
    assert decision == ResumeFromCheckpoint(from_index=2)


def test_rehydration_replays_login_when_session_invalid():
    decision = RunStateMachine.decide_rehydration(
        checkpoint_module_index=3, storage_state_valid=False, login_module_index=1
    )
    assert decision == ReplayFromLogin(from_index=1)


def test_rehydration_replays_from_zero_when_no_login_module():
    decision = RunStateMachine.decide_rehydration(
        checkpoint_module_index=2, storage_state_valid=False, login_module_index=None
    )
    assert decision == ReplayFromLogin(from_index=0)


@pytest.mark.asyncio
async def test_in_memory_store_roundtrip():
    store = InMemorySessionCheckpointStore()
    cp = SessionCheckpoint(
        run_id="run_c",
        system_code="hom",
        execution_mode="remote",
        module_index=1,
        session_id="sess",
        storage_state='{"cookies": []}',
        runtime_config={"browser_mode": "headless"},
    )
    await store.save(cp)
    assert await store.get("run_c") == cp
    await store.delete("run_c")
    assert await store.get("run_c") is None


class _ReversingCipher:
    """테스트용 대칭 암호(문자열 뒤집기) — 저장 시 암호화·조회 시 복호화 왕복 검증용."""

    def encrypt(self, plaintext: str) -> str:
        return plaintext[::-1]

    def decrypt(self, ciphertext: str) -> str:
        return ciphertext[::-1]


@pytest.mark.asyncio
async def test_sqlite_store_encrypts_storage_state(tmp_path: Path):
    db = SqliteDatabase(tmp_path / "cp.db")
    await ensure_schema(db)
    store = SqliteSessionCheckpointStore(db, cipher=_ReversingCipher())
    cp = SessionCheckpoint(
        run_id="run_s",
        system_code="hom",
        execution_mode="remote",
        module_index=2,
        session_id="sess",
        storage_state='{"cookies": ["auth"]}',
        runtime_config={"browser_mode": "headed"},
    )
    await store.save(cp)

    # 디스크에는 암호문(원문 아님)으로 저장된다.
    row = await db.fetchone(
        "SELECT storage_state_cipher FROM session_checkpoints WHERE run_id = ?", ("run_s",)
    )
    assert row["storage_state_cipher"] == '{"cookies": ["auth"]}'[::-1]

    # 조회 시 복호화되어 원문으로 돌아온다.
    loaded = await store.get("run_s")
    assert loaded is not None
    assert loaded.storage_state == '{"cookies": ["auth"]}'
    assert loaded.module_index == 2
    assert loaded.runtime_config == {"browser_mode": "headed"}

    await store.delete("run_s")
    assert await store.get("run_s") is None
