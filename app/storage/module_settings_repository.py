from __future__ import annotations

from typing import Protocol

from app.core.stats_models import ModuleSettings


class ModuleSettingsRepositoryPort(Protocol):
    async def save(self, settings: ModuleSettings) -> ModuleSettings: ...
    async def get(self, module_id: str) -> ModuleSettings | None: ...
    async def list(self) -> list[ModuleSettings]: ...
