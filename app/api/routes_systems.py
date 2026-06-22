from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from app.api.dependencies import get_run_service

if TYPE_CHECKING:
    from app.orchestrator.run_service import RunService


router = APIRouter(prefix="/api/systems", tags=["systems"])


@router.get("")
async def list_systems(run_service: "RunService" = Depends(get_run_service)):
    systems = run_service.list_systems()
    return [system.model_dump(mode="json") for system in systems]
