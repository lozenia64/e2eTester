from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter(prefix="/api/systems", tags=["systems"])


@router.get("")
async def list_systems(request: Request):
    systems = request.app.state.run_service.list_systems()
    return [system.model_dump(mode="json") for system in systems]
