"""암호화 SQLite ``RunInputStorePort`` — 재기동 후에도 rerun 입력값 보존."""

from __future__ import annotations

import asyncio
import json

from app.eventsourcing.support import SqliteDatabase
from app.storage.input_crypto import decrypt_bytes, derive_key, encrypt_bytes

_RUN_INPUT_SALT = b"e2e-run-input-v1"


def _encrypt_json(payload: dict[str, str], key: bytes) -> str:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return encrypt_bytes(raw, key)


def _decrypt_json(ciphertext: str, key: bytes) -> dict[str, str]:
    raw = decrypt_bytes(ciphertext, key)
    data = json.loads(raw.decode("utf-8"))
    return {str(field_key): str(value) for field_key, value in data.items()}


class EncryptedSqliteRunInputStore:
    """``RunInputStorePort`` 의 암호화 SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase, encryption_secret: str) -> None:
        self._db = db
        self._key = derive_key(encryption_secret, salt=_RUN_INPUT_SALT)
        self._lock = asyncio.Lock()

    async def put(self, run_id: str, input_data: dict[str, str]) -> None:
        ciphertext = _encrypt_json(dict(input_data), self._key)
        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO run_inputs (run_id, ciphertext) VALUES (?, ?)
                ON CONFLICT(run_id) DO UPDATE SET ciphertext = excluded.ciphertext
                """,
                (run_id, ciphertext),
            )

    async def get(self, run_id: str) -> dict[str, str] | None:
        async with self._lock:
            row = await self._db.fetchone(
                "SELECT ciphertext FROM run_inputs WHERE run_id = ?",
                (run_id,),
            )
        if row is None:
            return None
        return _decrypt_json(row["ciphertext"], self._key)

    async def delete(self, run_id: str) -> None:
        async with self._lock:
            await self._db.execute("DELETE FROM run_inputs WHERE run_id = ?", (run_id,))
