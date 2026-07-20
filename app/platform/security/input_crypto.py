"""Run/Suite 입력값 at-rest 암호화 (AES-GCM + 레거시 XOR 복호화 호환)."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

GCM_PREFIX = "gcm:v1:"


def derive_key(secret: str, *, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        salt,
        100_000,
        dklen=32,
    )


def _legacy_xor_crypt(data: bytes, key: bytes) -> bytes:
    stream = bytearray()
    counter = 0
    while len(stream) < len(data):
        stream.extend(hashlib.sha256(key + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(a ^ b for a, b in zip(data, stream[: len(data)], strict=True))


def encrypt_bytes(plaintext: bytes, key: bytes) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    encoded = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return f"{GCM_PREFIX}{encoded}"


def decrypt_bytes(stored: str, key: bytes) -> bytes:
    if stored.startswith(GCM_PREFIX):
        blob = base64.urlsafe_b64decode(stored[len(GCM_PREFIX) :].encode("ascii"))
        nonce, ciphertext = blob[:12], blob[12:]
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    return _legacy_xor_crypt(base64.urlsafe_b64decode(stored.encode("ascii")), key)
