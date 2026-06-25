from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException, status

from app.core.settings import get_settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7


def _secret_key() -> str:
    return get_settings().jwt_secret.get_secret_value()


def _b64url_encode(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _b64url_decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    return base64.urlsafe_b64decode(data + "=" * (padding % 4))


def create_access_token(data: dict) -> str:
    payload = dict(data)
    payload["exp"] = int(time.time()) + ACCESS_TOKEN_EXPIRE_MINUTES * 60
    secret_key = _secret_key()
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig_input = header + b"." + body
    sig = hmac.new(secret_key.encode(), sig_input, hashlib.sha256).digest()
    return (sig_input + b"." + _b64url_encode(sig)).decode()


def decode_token(token: str) -> dict:
    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="유효하지 않거나 만료된 토큰입니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise _invalid
        header_b, body_b, sig_b = parts
        sig_input = (header_b + "." + body_b).encode()
        secret_key = _secret_key()
        expected_sig = hmac.new(secret_key.encode(), sig_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise _invalid
        payload = json.loads(_b64url_decode(body_b))
        if payload.get("exp", 0) < int(time.time()):
            raise _invalid
        return payload
    except HTTPException:
        raise
    except Exception:
        raise _invalid
