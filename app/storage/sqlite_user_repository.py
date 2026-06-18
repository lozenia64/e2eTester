from __future__ import annotations

from app.auth.models import User
from app.storage.sqlite_support import JsonTableStore


class SqliteUserRepository:
    def __init__(self, db_path: str) -> None:
        self._store = JsonTableStore(db_path, "users")

    async def save(self, user: User) -> User:
        await self._store.upsert(user.user_id, user.model_dump_json())
        return user

    async def get(self, user_id: str) -> User:
        data = await self._store.get(user_id)
        if data is None:
            raise KeyError(user_id)
        return User.model_validate_json(data)

    async def get_by_email(self, email: str) -> User | None:
        all_data = await self._store.list_all()
        for data in all_data:
            user = User.model_validate_json(data)
            if user.email == email:
                return user
        return None

    async def list(self) -> list[User]:
        return [User.model_validate_json(data) for data in await self._store.list_all()]

    async def delete(self, user_id: str) -> None:
        await self._store.delete(user_id)
