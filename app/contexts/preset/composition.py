"""Preset BC composition — repository + PresetService."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.contexts.preset.application.service import PresetService
from app.contexts.preset.infrastructure.sqlite_preset_repository import SqlitePresetRepository
from app.contexts.run.application.service import RunService


@dataclass
class PresetContainer:
    preset_repository: SqlitePresetRepository = field(init=False)
    preset_service: PresetService = field(init=False)


def compose_preset_repository(db_path: str) -> SqlitePresetRepository:
    return SqlitePresetRepository(db_path)


def compose_preset_service(
    repository: SqlitePresetRepository,
    run_service: RunService,
) -> PresetService:
    return PresetService(repository=repository, run_service=run_service)
