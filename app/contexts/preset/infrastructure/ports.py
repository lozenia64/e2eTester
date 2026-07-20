"""Preset BC storage ports."""

from __future__ import annotations

from typing import Protocol

from app.core.preset_models import AuthPreset


class PresetRepositoryPort(Protocol):
    """사용자별 인증 프리셋(``AuthPreset``)의 저장 경계.

    프리셋은 인증 정보(PII 포함 가능)를 **의도적으로** 영속한다 — 그것이 기능의 목적이다.
    소유권 강제(사용자별 격리)는 상위 서비스/라우트가 책임지며, 저장소는 CRUD 만 담당한다.
    """

    async def save(self, preset: AuthPreset) -> AuthPreset: ...
    async def get(self, preset_id: str) -> AuthPreset: ...
    async def list_by_user(self, user_id: str) -> list[AuthPreset]: ...
    async def delete(self, preset_id: str) -> None: ...
