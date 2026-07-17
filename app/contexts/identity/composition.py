"""Identity BC composition — user repository + service."""

from __future__ import annotations

from dataclasses import dataclass

from app.contexts.identity.service import UserService
from app.storage.sqlite_user_repository import SqliteUserRepository


@dataclass(frozen=True)
class IdentityComposition:
    user_repository: SqliteUserRepository
    user_service: UserService


def compose_identity(db_path: str) -> IdentityComposition:
    user_repository = SqliteUserRepository(db_path)
    user_service = UserService(user_repository)
    return IdentityComposition(user_repository=user_repository, user_service=user_service)
