from __future__ import annotations

import secrets

import bcrypt
from datetime import datetime, timezone

from app.auth.models import CreateUserRequest, User
from app.storage.user_repository import UserRepositoryPort


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


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
            hashed_password=_hash_password(req.password),
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
        if not _verify_password(password, user.hashed_password):
            return None
        return user

    async def get_user(self, user_id: str) -> User:
        return await self._repo.get(user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        return await self._repo.get_by_email(email)

    async def list_users(self) -> list[User]:
        return await self._repo.list()

    async def update_user_systems(self, user_id: str, allowed_system_codes: list[str]) -> User:
        user = await self._repo.get(user_id)
        updated = user.model_copy(update={"allowed_system_codes": allowed_system_codes})
        return await self._repo.save(updated)

    async def update_user_active(self, user_id: str, is_active: bool) -> User:
        user = await self._repo.get(user_id)
        updated = user.model_copy(update={"is_active": is_active})
        return await self._repo.save(updated)

    async def delete_user(self, user_id: str) -> None:
        await self._repo.get(user_id)
        await self._repo.delete(user_id)

    async def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        from fastapi import HTTPException, status

        if len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="새 비밀번호는 8자 이상이어야 합니다.",
            )
        user = await self._repo.get(user_id)
        if not _verify_password(current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="현재 비밀번호가 올바르지 않습니다.",
            )
        updated = user.model_copy(update={"hashed_password": _hash_password(new_password)})
        await self._repo.save(updated)

    async def seed_admin(self, email: str, name: str = "관리자") -> None:
        existing = await self._repo.get_by_email(email)
        if existing is not None:
            return
        initial_password = secrets.token_urlsafe(12)
        req = CreateUserRequest(email=email, name=name, password=initial_password, role="admin")
        await self.create_user(req)
        print(
            f"[auth] 관리자 계정 최초 생성: {email} — "
            f"초기 비밀번호: {initial_password} (로그인 후 반드시 변경하세요)"
        )
