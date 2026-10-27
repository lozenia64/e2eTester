"""사용량 통계와 성과 보고가 공유하는 수동 점검 기준 초."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.enums import ModuleStatus

if TYPE_CHECKING:
    from app.contexts.insights.infrastructure.module_settings_repository import (
        ModuleSettingsRepositoryPort,
    )
    from app.contexts.run.contracts.query_rows import ModuleHistoryRow
    from app.core.system_models import SystemDefinition


async def load_savings_basis(
    systems: list[SystemDefinition], settings: ModuleSettingsRepositoryPort | None
) -> dict[str, dict[str, int]]:
    basis = {
        s.system_code: {m.module_id: m.estimated_manual_seconds for m in s.modules} for s in systems
    }
    if settings is not None:
        for override in await settings.list():
            code, separator, _ = override.module_id.partition(".")
            if separator and code in basis:
                basis[code][override.module_id] = override.estimated_manual_seconds
    return basis


def saved_module_seconds(modules: list[ModuleHistoryRow], basis: dict[str, int]) -> int:
    return sum(basis.get(m.module_id, 0) for m in modules if m.status == ModuleStatus.PASSED)
