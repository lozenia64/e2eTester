from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import require_admin
from app.auth.models import CreateUserRequest, User, UserPublic

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
