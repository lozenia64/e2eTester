from __future__ import annotations

from app.core.models import ModuleSettings
from app.storage.sqlite_support import JsonTableStore


class SqliteModuleSettingsRepository:
    def __init__(self, db_path: str) -> None:
        self._store = JsonTableStore(db_path, "module_settings")

    async def save(self, settings: ModuleSettings) -> ModuleSettings:
        await self._store.upsert(settings.module_id, settings.model_dump_json())
        return settings

    async def get(self, module_id: str) -> ModuleSettings | None:
        data = await self._store.get(module_id)
        if data is None:
            return None
        return ModuleSettings.model_validate_json(data)

    async def list(self) -> list[ModuleSettings]:
        return [ModuleSettings.model_validate_json(data) for data in await self._store.list_all()]
