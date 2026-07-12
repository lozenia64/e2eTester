from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from starlette.requests import HTTPConnection

from app.contexts.identity.jwt import decode_token
from app.contexts.identity.models import User

if TYPE_CHECKING:
    from app.contexts.identity.service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_user_service(connection: HTTPConnection) -> UserService:
    """인증/사용자 도메인 서비스 제공자(HTTP·WebSocket 공통)."""
    return connection.app.state.user_service


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    user_service: UserService = Depends(get_user_service),
) -> User:
    if token is None:
        token = request.cookies.get("access_token")

    if not token:
        if request.url.path.startswith("/api/"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다."
            )
        return RedirectResponse(url="/login")  # type: ignore[return-value]

    payload = decode_token(token)
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다."
        )

    try:
        user = await user_service.get_user(user_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="존재하지 않는 사용자입니다."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="비활성화된 계정입니다."
        )

    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한이 필요합니다."
        )
    return current_user
