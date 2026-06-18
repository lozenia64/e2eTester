from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class User(BaseModel):
    user_id: str
    email: str
    name: str
    role: Literal["admin", "user"]
    hashed_password: str
    is_active: bool = True
    created_at: datetime
    allowed_system_codes: list[str] = []


class UserPublic(BaseModel):
    user_id: str
    email: str
    name: str
    role: Literal["admin", "user"]
    is_active: bool
    created_at: datetime
    allowed_system_codes: list[str] = []


class CreateUserRequest(BaseModel):
    email: str
    name: str
    password: str
    role: Literal["admin", "user"] = "user"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic
