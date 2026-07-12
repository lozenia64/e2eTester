from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_preset_service
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.requests import CreatePresetRequest, UpdatePresetRequest

if TYPE_CHECKING:
    from app.contexts.preset.application.service import PresetService

router = APIRouter(prefix="/api/presets", tags=["presets"])


def _ensure_system_access(user: User, system_code: str) -> None:
    if user.role != "admin" and system_code not in user.allowed_system_codes:
        raise HTTPException(status_code=403, detail="해당 시스템에 대한 접근 권한이 없습니다.")


@router.get("")
async def list_presets(
    system_code: str | None = None,
    current_user: User = Depends(get_current_user),
    preset_service: PresetService = Depends(get_preset_service),
):
    presets = await preset_service.list_presets(current_user.user_id, system_code)
    return [preset.to_public() for preset in presets]


@router.post("")
async def create_preset(
    payload: CreatePresetRequest,
    current_user: User = Depends(get_current_user),
    preset_service: PresetService = Depends(get_preset_service),
):
    _ensure_system_access(current_user, payload.system_code)
    try:
        preset = await preset_service.create_preset(current_user.user_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="System not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return preset.to_public()


@router.put("/{preset_id}")
async def update_preset(
    preset_id: str,
    payload: UpdatePresetRequest,
    current_user: User = Depends(get_current_user),
    preset_service: PresetService = Depends(get_preset_service),
):
    try:
        preset = await preset_service.update_preset(preset_id, current_user.user_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Preset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return preset.to_public()


@router.delete("/{preset_id}")
async def delete_preset(
    preset_id: str,
    current_user: User = Depends(get_current_user),
    preset_service: PresetService = Depends(get_preset_service),
):
    try:
        await preset_service.delete_preset(preset_id, current_user.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Preset not found") from exc
    return {"ok": True}
