"""Healing BC composition — event/policy/patch stores + HealingService."""

from __future__ import annotations

from dataclasses import dataclass

from app.contexts.healing.engine import SelfHealingEngine
from app.contexts.healing.infrastructure.sqlite_healing_stores import (
    SqliteHealingEventStore,
    SqliteHealingPatchStore,
    SqliteHealingPolicyStore,
)
from app.contexts.healing.service import HealingService
from app.registry.loader import ModuleRegistry


@dataclass(frozen=True)
class HealingContainer:
    healing_engine: SelfHealingEngine | None
    healing_service: HealingService


def compose_healing(db_path: str, registry: ModuleRegistry) -> HealingContainer:
    healing_service = HealingService(
        event_store=SqliteHealingEventStore(db_path),
        policy_store=SqliteHealingPolicyStore(db_path),
        patch_store=SqliteHealingPatchStore(db_path),
        registry=registry,
    )
    return HealingContainer(healing_engine=None, healing_service=healing_service)
