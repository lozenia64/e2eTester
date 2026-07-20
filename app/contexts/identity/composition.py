"""Identity BC composition — user repository + service."""

from __future__ import annotations

from dataclasses import dataclass

from app.contexts.identity.infrastructure.sqlite_user_repository import SqliteUserRepository
from app.contexts.identity.service import UserService


@dataclass(frozen=True)
class IdentityContainer:
    user_repository: SqliteUserRepository
    user_service: UserService


def compose_identity(db_path: str) -> IdentityContainer:
    user_repository = SqliteUserRepository(db_path)
    user_service = UserService(user_repository)
    return IdentityContainer(user_repository=user_repository, user_service=user_service)
