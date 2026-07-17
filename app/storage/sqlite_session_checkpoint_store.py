"""``SessionCheckpointStorePort`` SQLite 어댑터(Phase C).

``session_checkpoints`` 테이블(스키마는 ``eventsourcing/support.ensure_schema``)에 모듈 경계
체크포인트를 upsert 한다. ``storage_state`` 는 인증 쿠키를 포함하므로 주입된 암호화 협력자로
암호화해 ``storage_state_cipher`` 컬럼에 저장한다(미주입 시 평문 — 개발/테스트 전용).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.execution.session_checkpoint import SessionCheckpoint
from app.platform.eventing.support import SqliteDatabase
from app.storage.input_crypto import decrypt_bytes, derive_key, encrypt_bytes

_CHECKPOINT_SALT = b"e2e-session-checkpoint-v1"


class StorageStateCipher:
    """입력 스토어와 동일한 AES-GCM 원시로 storage_state 문자열을 암복호화한다(인증 쿠키 보호)."""

    def __init__(self, encryption_secret: str) -> None:
        self._key = derive_key(encryption_secret, salt=_CHECKPOINT_SALT)

    def encrypt(self, plaintext: str) -> str:
        return encrypt_bytes(plaintext.encode("utf-8"), self._key)

    def decrypt(self, ciphertext: str) -> str:
        return decrypt_bytes(ciphertext, self._key).decode("utf-8")


class SqliteSessionCheckpointStore:
    def __init__(self, db: SqliteDatabase, *, cipher=None) -> None:
        self._db = db
        self._cipher = cipher

    def _encrypt(self, plaintext: str | None) -> str | None:
        if plaintext is None:
            return None
        return self._cipher.encrypt(plaintext) if self._cipher is not None else plaintext

    def _decrypt(self, ciphertext: str | None) -> str | None:
        if ciphertext is None:
            return None
        return self._cipher.decrypt(ciphertext) if self._cipher is not None else ciphertext

    async def save(self, checkpoint: SessionCheckpoint) -> None:
        await self._db.execute(
            """
            INSERT INTO session_checkpoints
                (run_id, session_id, worker_id, system_code, execution_mode, module_index,
                 workflow_step, storage_state_cipher, runtime_config_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                session_id = excluded.session_id,
                worker_id = excluded.worker_id,
                system_code = excluded.system_code,
                execution_mode = excluded.execution_mode,
                module_index = excluded.module_index,
                workflow_step = excluded.workflow_step,
                storage_state_cipher = excluded.storage_state_cipher,
                runtime_config_json = excluded.runtime_config_json,
                updated_at = excluded.updated_at
            """,
            (
                checkpoint.run_id,
                checkpoint.session_id,
                checkpoint.worker_id,
                checkpoint.system_code,
                checkpoint.execution_mode,
                checkpoint.module_index,
                checkpoint.workflow_step,
                self._encrypt(checkpoint.storage_state),
                json.dumps(checkpoint.runtime_config) if checkpoint.runtime_config else None,
                (checkpoint.updated_at or datetime.now(UTC)).isoformat(),
            ),
        )

    async def get(self, run_id: str) -> SessionCheckpoint | None:
        row = await self._db.fetchone(
            "SELECT * FROM session_checkpoints WHERE run_id = ?", (run_id,)
        )
        if row is None:
            return None
        config = row["runtime_config_json"]
        return SessionCheckpoint(
            run_id=row["run_id"],
            system_code=row["system_code"],
            execution_mode=row["execution_mode"],
            module_index=row["module_index"],
            session_id=row["session_id"],
            worker_id=row["worker_id"],
            workflow_step=row["workflow_step"],
            storage_state=self._decrypt(row["storage_state_cipher"]),
            runtime_config=json.loads(config) if config else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    async def delete(self, run_id: str) -> None:
        await self._db.execute("DELETE FROM session_checkpoints WHERE run_id = ?", (run_id,))
