"""Healing BC composition — event/policy/patch stores + HealingService."""

from __future__ import annotations

from dataclasses import dataclass

from app.contexts.healing.infrastructure.sqlite_healing_stores import (
    SqliteHealingEventStore,
    SqliteHealingPatchStore,
    SqliteHealingPolicyStore,
)
from app.contexts.healing.service import HealingService
from app.registry.loader import ModuleRegistry


@dataclass(frozen=True)
class HealingComposition:
    healing_service: HealingService


def compose_healing(db_path: str, registry: ModuleRegistry) -> HealingComposition:
    healing_service = HealingService(
        event_store=SqliteHealingEventStore(db_path),
        policy_store=SqliteHealingPolicyStore(db_path),
        patch_store=SqliteHealingPatchStore(db_path),
        registry=registry,
    )
    return HealingComposition(healing_service=healing_service)
