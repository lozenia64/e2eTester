from __future__ import annotations

import time

import jwt
from fastapi import HTTPException, status

from app.core.settings import get_settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7


def _secret_key() -> str:
    return get_settings().jwt_secret.get_secret_value()


def create_access_token(data: dict) -> str:
    payload = dict(data)
    payload["exp"] = int(time.time()) + ACCESS_TOKEN_EXPIRE_MINUTES * 60
    return jwt.encode(payload, _secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="유효하지 않거나 만료된 토큰입니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # algorithms 를 명시해 alg 혼동 공격(alg:none/비대칭키 우회)을 차단한다.
        return jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
    except jwt.InvalidTokenError as exc:  # 만료(ExpiredSignatureError) 포함 모든 검증 실패
        raise _invalid from exc
