"""입력값 at-rest 암호화(AES-GCM + 레거시 XOR 복호화 호환)."""

from __future__ import annotations

import base64
import json

from app.platform.security.input_crypto import GCM_PREFIX, decrypt_bytes, derive_key, encrypt_bytes

_RUN_SALT = b"e2e-run-input-v1"


def test_aes_gcm_roundtrip():
    key = derive_key("test-secret", salt=_RUN_SALT)
    payload = {"phone": "01012345678", "password": "secret"}
    raw = json.dumps(payload).encode("utf-8")
    stored = encrypt_bytes(raw, key)
    assert stored.startswith(GCM_PREFIX)
    assert decrypt_bytes(stored, key) == raw


def test_legacy_xor_ciphertext_still_decrypts():
    key = derive_key("test-secret", salt=_RUN_SALT)
    payload = b'{"phone":"010"}'
    # 레거시 XOR 형식(접두사 없는 base64)
    from app.platform.security.input_crypto import _legacy_xor_crypt

    legacy = base64.urlsafe_b64encode(_legacy_xor_crypt(payload, key)).decode("ascii")
    assert not legacy.startswith(GCM_PREFIX)
    assert decrypt_bytes(legacy, key) == payload
