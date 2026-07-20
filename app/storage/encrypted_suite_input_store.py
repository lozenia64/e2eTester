"""암호화 SQLite ``SuiteInputStorePort`` — 재기동 후에도 Suite 입력값 보존."""

from __future__ import annotations

import asyncio
import json

from app.platform.eventing.support import SqliteDatabase
from app.storage.input_crypto import decrypt_bytes, derive_key, encrypt_bytes

_SUITE_INPUT_SALT = b"e2e-suite-input-v1"


def _encrypt_json(payload: dict[str, dict[str, str]], key: bytes) -> str:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return encrypt_bytes(raw, key)


def _decrypt_json(ciphertext: str, key: bytes) -> dict[str, dict[str, str]]:
    raw = decrypt_bytes(ciphertext, key)
    data = json.loads(raw.decode("utf-8"))
    return {
        str(system_code): {str(k): str(v) for k, v in fields.items()}
        for system_code, fields in data.items()
    }


class EncryptedSqliteSuiteInputStore:
    """``SuiteInputStorePort`` 의 암호화 SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase, encryption_secret: str) -> None:
        self._db = db
        self._key = derive_key(encryption_secret, salt=_SUITE_INPUT_SALT)
        self._lock = asyncio.Lock()

    async def put(self, suite_id: str, systems_input: dict[str, dict[str, str]]) -> None:
        copied = {code: dict(fields) for code, fields in systems_input.items()}
        ciphertext = _encrypt_json(copied, self._key)
        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO suite_inputs (suite_id, ciphertext) VALUES (?, ?)
                ON CONFLICT(suite_id) DO UPDATE SET ciphertext = excluded.ciphertext
                """,
                (suite_id, ciphertext),
            )

    async def get(self, suite_id: str) -> dict[str, dict[str, str]] | None:
        async with self._lock:
            row = await self._db.fetchone(
                "SELECT ciphertext FROM suite_inputs WHERE suite_id = ?",
                (suite_id,),
            )
        if row is None:
            return None
        return _decrypt_json(row["ciphertext"], self._key)

    async def delete(self, suite_id: str) -> None:
        async with self._lock:
            await self._db.execute("DELETE FROM suite_inputs WHERE suite_id = ?", (suite_id,))
