"""암호화 SQLite ``RunInputStorePort`` — 재기동 후에도 rerun 입력값 보존."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json

from app.eventsourcing.support import SqliteDatabase


def _derive_key(secret: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        b"e2e-run-input-v1",
        100_000,
        dklen=32,
    )


def _xor_crypt(data: bytes, key: bytes) -> bytes:
    stream = bytearray()
    counter = 0
    while len(stream) < len(data):
        stream.extend(hashlib.sha256(key + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(a ^ b for a, b in zip(data, stream[: len(data)], strict=True))


def _encrypt_json(payload: dict[str, str], key: bytes) -> str:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(_xor_crypt(raw, key)).decode("ascii")


def _decrypt_json(ciphertext: str, key: bytes) -> dict[str, str]:
    raw = _xor_crypt(base64.urlsafe_b64decode(ciphertext.encode("ascii")), key)
    data = json.loads(raw.decode("utf-8"))
    return {str(key): str(value) for key, value in data.items()}


class EncryptedSqliteRunInputStore:
    """``RunInputStorePort`` 의 암호화 SQLite 어댑터."""

    def __init__(self, db: SqliteDatabase, encryption_secret: str) -> None:
        self._db = db
        self._key = _derive_key(encryption_secret)
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
