from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import require_admin
from app.auth.models import CreateUserRequest, User, UserPublic
from app.core.models import ModuleSettings

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/runs")
async def admin_list_runs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    summaries = await request.app.state.run_service.list_run_summaries()
    return summaries[:limit]


@router.get("/stats/usage")
async def admin_usage_stats(
    request: Request,
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    current_user: User = Depends(require_admin),
):
    stats = await request.app.state.stats_service.get_usage_stats(from_dt=from_dt, to_dt=to_dt)
    return stats.model_dump(mode="json")


@router.get("/users")
async def admin_list_users(
    request: Request,
    current_user: User = Depends(require_admin),
) -> list[UserPublic]:
    users = await request.app.state.user_service.list_users()
    return [UserPublic(**u.model_dump()) for u in users]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    request: Request,
    payload: CreateUserRequest,
    current_user: User = Depends(require_admin),
) -> UserPublic:
    user = await request.app.state.user_service.create_user(payload)
    return UserPublic(**user.model_dump())


@router.patch("/users/{user_id}/active")
async def admin_toggle_user_active(
    request: Request,
    user_id: str,
    payload: dict,
    current_user: User = Depends(require_admin),
) -> UserPublic:
    is_active = payload.get("is_active")
    if not isinstance(is_active, bool):
        raise HTTPException(status_code=400, detail="is_active 값이 필요합니다.")
    try:
        user = await request.app.state.user_service.update_user_active(user_id, is_active)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.") from exc
    return UserPublic(**user.model_dump())


@router.delete("/users/{user_id}")
async def admin_delete_user(
    request: Request,
    user_id: str,
    current_user: User = Depends(require_admin),
) -> dict:
    try:
        await request.app.state.user_service.delete_user(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.") from exc
    except AttributeError:
        raise HTTPException(status_code=501, detail="사용자 삭제 기능이 지원되지 않습니다.")
    return {"ok": True}


@router.get("/stats/savings/csv")
async def admin_savings_csv(
    request: Request,
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    current_user: User = Depends(require_admin),
) -> StreamingResponse:
    stats = await request.app.state.stats_service.get_usage_stats(from_dt=from_dt, to_dt=to_dt)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "사용자ID", "이름", "이메일", "총Run수", "통과모듈수", "실패모듈수",
        "자동화실행시간(분)", "절감시간(분)",
        "시스템코드", "시스템명", "시스템별Run수", "시스템별통과모듈", "시스템별절감시간(분)",
    ])

    for u in stats.by_user:
        automation_min = round((u.total_duration_ms or 0) / 60000, 1)
        for s in u.by_system:
            sys_automation_min = round((s.total_duration_ms or 0) / 60000, 1)
            writer.writerow([
                u.user_id or "",
                u.user_name or "(시스템)",
                u.email or "",
                u.total_runs,
                u.total_modules_passed,
                u.total_modules_failed,
                automation_min,
                u.manual_minutes_saved,
                s.system_code,
                s.system_name,
                s.runs,
                s.modules_passed,
                s.manual_minutes_saved,
            ])

    date_str = datetime.now().strftime("%Y%m%d")
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename=savings_{date_str}.csv"},
    )


@router.get("/systems")
async def admin_list_systems(
    request: Request,
    current_user: User = Depends(require_admin),
) -> list[dict]:
    registry = request.app.state.stats_service._registry
    return [
        {"system_code": s.system_code, "system_name": s.name}
        for s in registry.list_systems()
    ]


@router.put("/users/{user_id}/systems")
async def admin_update_user_systems(
    request: Request,
    user_id: str,
    payload: dict,
    current_user: User = Depends(require_admin),
) -> UserPublic:
    codes = payload.get("allowed_system_codes")
    if not isinstance(codes, list):
        raise HTTPException(status_code=400, detail="allowed_system_codes 목록이 필요합니다.")
    try:
        user = await request.app.state.user_service.update_user_systems(user_id, codes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.") from exc
    return UserPublic(**user.model_dump())


@router.get("/module-settings")
async def admin_list_module_settings(
    request: Request,
    current_user: User = Depends(require_admin),
) -> list[dict]:
    registry = request.app.state.stats_service._registry
    repo = request.app.state.module_settings_repo

    overrides: dict[str, int] = {}
    if repo is not None:
        for s in await repo.list():
            overrides[s.module_id] = s.estimated_manual_seconds

    result = []
    for system in registry.list_systems():
        modules = []
        for m in system.modules:
            is_overridden = m.module_id in overrides
            seconds = overrides[m.module_id] if is_overridden else m.estimated_manual_seconds
            modules.append({
                "module_id": m.module_id,
                "name": m.name,
                "estimated_manual_seconds": seconds,
                "manifest_default": m.estimated_manual_seconds,
                "is_overridden": is_overridden,
            })
        result.append({
            "system_code": system.system_code,
            "system_name": system.name,
            "modules": modules,
        })
    return result


@router.put("/module-settings/{module_id:path}")
async def admin_update_module_settings(
    request: Request,
    module_id: str,
    payload: dict,
    current_user: User = Depends(require_admin),
) -> dict:
    seconds = payload.get("estimated_manual_seconds")
    if not isinstance(seconds, int) or seconds < 0:
        raise HTTPException(status_code=400, detail="estimated_manual_seconds 값이 필요합니다.")

    repo = request.app.state.module_settings_repo
    if repo is None:
        raise HTTPException(status_code=503, detail="모듈 설정 저장소가 초기화되지 않았습니다.")

    from datetime import datetime, timezone
    settings = ModuleSettings(
        module_id=module_id,
        estimated_manual_seconds=seconds,
        updated_at=datetime.now(timezone.utc),
    )
    await repo.save(settings)
    return {"ok": True, "module_id": module_id, "estimated_manual_seconds": seconds}
