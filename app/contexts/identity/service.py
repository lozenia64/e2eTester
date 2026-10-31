from __future__ import annotations

import secrets
from datetime import UTC, datetime

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.contexts.identity.infrastructure.user_repository import UserRepositoryPort
from app.contexts.identity.models import CreateUserRequest, User

# 첫 해셔(Argon2id)가 신규 비밀번호 해싱에 쓰이고, 모든 해셔가 검증에 쓰인다.
# 기존에 저장된 bcrypt 해시도 그대로 검증되며, 로그인 시 Argon2id 로 자동 재해싱된다.
_password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))


def _hash_password(password: str) -> str:
    return _password_hash.hash(password)


def _verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)


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
            created_at=datetime.now(UTC),
        )
        return await self._repo.save(user)

    async def authenticate(self, email: str, password: str) -> User | None:
        user = await self._repo.get_by_email(email)
        if user is None:
            return None
        if not user.is_active:
            return None
        valid, upgraded_hash = _password_hash.verify_and_update(password, user.hashed_password)
        if not valid:
            return None
        # 레거시 bcrypt 해시는 로그인 성공 시 Argon2id 로 1회 재해싱해 영속화한다.
        if upgraded_hash is not None:
            user = await self._repo.save(user.model_copy(update={"hashed_password": upgraded_hash}))
        return user

    async def get_user(self, user_id: str) -> User:
        return await self._repo.get(user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        return await self._repo.get_by_email(email)

    async def get_user_by_telegram_id(self, telegram_user_id: int) -> User | None:
        for user in await self._repo.list():
            if user.telegram_user_id == telegram_user_id:
                return user
        return None

    async def link_telegram(self, user_id: str, telegram_user_id: int) -> User:
        """텔레그램 계정 하나는 사용자 한 명에게만 연결한다(기존 연결은 옮겨 온다)."""
        user = await self._repo.get(user_id)
        previous = await self.get_user_by_telegram_id(telegram_user_id)
        if previous is not None and previous.user_id != user_id:
            await self._repo.save(previous.model_copy(update={"telegram_user_id": None}))
        return await self._repo.save(user.model_copy(update={"telegram_user_id": telegram_user_id}))

    async def unlink_telegram(self, user_id: str) -> None:
        user = await self._repo.get(user_id)
        await self._repo.save(user.model_copy(update={"telegram_user_id": None}))

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

    async def seed_admin(self, email: str, password: str, name: str = "관리자") -> None:
        existing = await self._repo.get_by_email(email)
        if existing is not None:
            return
        req = CreateUserRequest(email=email, name=name, password=password, role="admin")
        await self.create_user(req)
        print(f"[auth] 관리자 계정 생성: {email}")
