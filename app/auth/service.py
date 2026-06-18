from __future__ import annotations

import secrets
from datetime import datetime, timezone

from passlib.context import CryptContext

from app.auth.models import CreateUserRequest, User
from app.storage.user_repository import UserRepositoryPort

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    def __init__(self, repo: UserRepositoryPort) -> None:
        self._repo = repo

    async def create_user(self, req: CreateUserRequest) -> User:
        existing = await self._repo.get_by_email(req.email)
        if existing is not None:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 사용 중인 이메일입니다.",
            )
        user = User(
            user_id=f"usr_{secrets.token_hex(4)}",
            email=req.email,
            name=req.name,
            role=req.role,
            hashed_password=_pwd_ctx.hash(req.password),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        return await self._repo.save(user)

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self._repo.get_by_email(email)
        if user is None:
            return None
        if not user.is_active:
            return None
        if not _pwd_ctx.verify(password, user.hashed_password):
            return None
        return user

    async def get_user(self, user_id: str) -> User:
        return await self._repo.get(user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        return await self._repo.get_by_email(email)

    async def list_users(self) -> list[User]:
        return await self._repo.list()

    async def update_user_active(self, user_id: str, is_active: bool) -> User:
        user = await self._repo.get(user_id)
        updated = user.model_copy(update={"is_active": is_active})
        return await self._repo.save(updated)

    async def seed_admin(self, email: str, password: str, name: str = "관리자") -> None:
        existing = await self._repo.get_by_email(email)
        if existing is not None:
            return
        req = CreateUserRequest(email=email, name=name, password=password, role="admin")
        await self.create_user(req)
        print(f"[auth] 관리자 계정 생성: {email}")
