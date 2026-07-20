from __future__ import annotations

from app.core.preset_models import AuthPreset
from app.platform.db import JsonTableStore


class SqlitePresetRepository:
    """``AuthPreset`` 의 SQLite 영속 어댑터(``PresetRepositoryPort`` 구현).

    단일 JSON blob 테이블(``auth_presets``)에 ``preset_id`` 키로 저장한다. 사용자별 조회는
    전량을 읽어 Python 에서 필터링한다 — 내부 저부하 도구라 프리셋 수가 적어 충분하다.
    """

    def __init__(self, db_path: str) -> None:
        self._store = JsonTableStore(db_path, "auth_presets")

    async def save(self, preset: AuthPreset) -> AuthPreset:
        await self._store.upsert(preset.preset_id, preset.model_dump_json())
        return preset

    async def get(self, preset_id: str) -> AuthPreset:
        data = await self._store.get(preset_id)
        if data is None:
            raise KeyError(preset_id)
        return AuthPreset.model_validate_json(data)

    async def list_by_user(self, user_id: str) -> list[AuthPreset]:
        presets = [AuthPreset.model_validate_json(data) for data in await self._store.list_all()]
        owned = [preset for preset in presets if preset.user_id == user_id]
        owned.sort(key=lambda preset: (preset.system_code, preset.created_at))
        return owned

    async def delete(self, preset_id: str) -> None:
        await self._store.delete(preset_id)
