from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.api.dependencies import get_healing_service
from app.auth.dependencies import get_current_user, require_admin
from app.auth.models import User

if TYPE_CHECKING:
    from app.orchestrator.healing_service import HealingService

router = APIRouter(prefix="/api/healing", tags=["healing"])


class PolicyItem(BaseModel):
    system_code: str
    auto_heal_enabled: bool = True
    confidence_threshold: float = 0.75


class PolicyUpdate(BaseModel):
    policies: list[PolicyItem] = Field(default_factory=list)


class PatchDecision(BaseModel):
    apply_to_source: bool = True
    note: str = ""


def _allowed(current_user: User) -> list[str] | None:
    return None if current_user.role == "admin" else current_user.allowed_system_codes


@router.get("/events")
async def list_healing_events(
    system: str | None = None,
    current_user: User = Depends(get_current_user),
    healing: HealingService = Depends(get_healing_service),
):
    """치유 이벤트 목록(폐루프 5단계 파이프라인 카드의 데이터 소스, 최신순)."""
    return await healing.list_events(
        allowed_system_codes=_allowed(current_user), system_code=system
    )


@router.get("/metrics")
async def healing_metrics(
    current_user: User = Depends(get_current_user),
    healing: HealingService = Depends(get_healing_service),
):
    """복구 콘솔 KPI(이번 달 자동 복구·무인 통과율·MTTR) + 추이 + 만성 지점 표."""
    return await healing.metrics(allowed_system_codes=_allowed(current_user))


@router.get("/durability")
async def healing_durability(
    current_user: User = Depends(get_current_user),
    healing: HealingService = Depends(get_healing_service),
):
    """셀렉터 내구성 맵 — steps 소스 정적 스캔 + 치유 이력 결합(사전 예방 관측)."""
    return await healing.durability(allowed_system_codes=_allowed(current_user))


@router.get("/policy")
async def get_healing_policy(
    current_user: User = Depends(get_current_user),
    healing: HealingService = Depends(get_healing_service),
):
    """자동 복구 정책(전역 기본값 + 시스템별 auto-heal on/off·신뢰도 임계치)."""
    return await healing.get_policies(allowed_system_codes=_allowed(current_user))


@router.put("/policy")
async def put_healing_policy(
    payload: PolicyUpdate,
    current_user: User = Depends(get_current_user),
    healing: HealingService = Depends(get_healing_service),
):
    """정책 upsert — 전역(``*``)은 관리자만, 시스템 행은 접근 범위 안에서만."""
    try:
        return await healing.put_policies(
            [item.model_dump() for item in payload.policies],
            actor_name=current_user.name,
            allowed_system_codes=_allowed(current_user),
            is_admin=current_user.role == "admin",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/patches")
async def list_healing_patches(
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    healing: HealingService = Depends(get_healing_service),
):
    """셀렉터 오토픽스 패치 목록(승인 대기 diff + 승인/거절 감사 이력)."""
    try:
        return await healing.list_patches(
            allowed_system_codes=_allowed(current_user), status=status
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/patches/{patch_id}/approve")
async def approve_healing_patch(
    patch_id: str,
    payload: PatchDecision | None = None,
    current_user: User = Depends(require_admin),
    healing: HealingService = Depends(get_healing_service),
):
    """패치 승인(사람 승인 게이트) — 승인 시점에 steps 소스 파일에 반영한다."""
    decision = payload or PatchDecision()
    try:
        patch = await healing.approve_patch(
            patch_id,
            actor_name=current_user.name,
            apply_to_source=decision.apply_to_source,
            allowed_system_codes=_allowed(current_user),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="패치를 찾을 수 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return patch.model_dump(mode="json")


@router.post("/patches/{patch_id}/reject")
async def reject_healing_patch(
    patch_id: str,
    payload: PatchDecision | None = None,
    current_user: User = Depends(require_admin),
    healing: HealingService = Depends(get_healing_service),
):
    """패치 거절 — 사유(note)와 함께 감사 이력에 남긴다."""
    decision = payload or PatchDecision()
    try:
        patch = await healing.reject_patch(
            patch_id,
            actor_name=current_user.name,
            note=decision.note,
            allowed_system_codes=_allowed(current_user),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="패치를 찾을 수 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return patch.model_dump(mode="json")


@router.get("/patches/{patch_id}/download")
async def download_healing_patch(
    patch_id: str,
    current_user: User = Depends(get_current_user),
    healing: HealingService = Depends(get_healing_service),
):
    """패치 diff 다운로드(.patch) — 소스 반영 대신 리뷰 도구로 가져갈 때."""
    try:
        filename, diff = await healing.patch_diff(
            patch_id, allowed_system_codes=_allowed(current_user)
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="패치를 찾을 수 없습니다.") from exc
    return PlainTextResponse(
        diff,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
