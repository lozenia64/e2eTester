from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import (
    get_module_settings_repo,
    get_ops_service,
    get_registry,
    get_run_queries,
    get_run_service,
    get_schedule_repository,
    get_stats_service,
    get_suite_summary_query,
)
from app.contexts.identity.dependencies import get_user_service, require_admin
from app.contexts.identity.models import CreateUserRequest, User, UserPublic
from app.contexts.run.views.actor import load_actor_context
from app.core.stats_models import ModuleSettings
from app.core.status_labels import ADMIN_VISIBLE_RUN_STATUSES

if TYPE_CHECKING:
    from app.contexts.identity.service import UserService
    from app.contexts.insights.application.ops_service import OpsService
    from app.contexts.insights.application.stats_service import StatsService
    from app.contexts.run.application.service import RunService
    from app.orchestrator.queries import RunQueries
    from app.registry.loader import ModuleRegistry
    from app.storage.ports import ScheduleRepositoryPort, SuiteSummaryQueryPort

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _fmt_saved_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}초"
    minutes = seconds // 60
    rem = seconds % 60
    return f"{minutes}분 {rem}초"


@router.get("/runs")
async def admin_list_runs(
    limit: int = Query(default=100, ge=1, le=1000),
    system_code: str | None = Query(default=None),
    user_name: str | None = Query(default=None),
    current_user: User = Depends(require_admin),
    run_queries: RunQueries = Depends(get_run_queries),
    user_service: UserService = Depends(get_user_service),
    suite_summary_query: SuiteSummaryQueryPort = Depends(get_suite_summary_query),
    schedule_repo: ScheduleRepositoryPort = Depends(get_schedule_repository),
) -> list[dict[str, Any]]:
    actor_context = await load_actor_context(
        user_service,
        suite_summary_query,
        schedule_repo,
    )
    summaries = await run_queries.list_run_summaries(
        limit=limit,
        system_code=system_code,
        user_name_query=user_name,
        actor_context=actor_context,
        run_statuses=ADMIN_VISIBLE_RUN_STATUSES,
    )
    return summaries


@router.delete("/runs/{run_id}")
async def admin_delete_run(
    run_id: str,
    current_user: User = Depends(require_admin),
    run_service: RunService = Depends(get_run_service),
) -> dict[str, bool]:
    try:
        await run_service.delete_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run을 찾을 수 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/ops/snapshot")
async def admin_ops_snapshot(
    current_user: User = Depends(require_admin),
    ops_service: OpsService = Depends(get_ops_service),
) -> dict[str, Any]:
    return await ops_service.build_snapshot()


@router.get("/stats/usage")
async def admin_usage_stats(
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    current_user: User = Depends(require_admin),
    stats_service: StatsService = Depends(get_stats_service),
):
    stats = await stats_service.get_usage_stats(from_dt=from_dt, to_dt=to_dt)
    return stats.model_dump(mode="json")


@router.get("/users")
async def admin_list_users(
    current_user: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
) -> list[UserPublic]:
    users = await user_service.list_users()
    return [UserPublic(**u.model_dump()) for u in users]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    payload: CreateUserRequest,
    current_user: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
) -> UserPublic:
    user = await user_service.create_user(payload)
    return UserPublic(**user.model_dump())


@router.patch("/users/{user_id}/active")
async def admin_toggle_user_active(
    user_id: str,
    payload: dict,
    current_user: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
) -> UserPublic:
    is_active = payload.get("is_active")
    if not isinstance(is_active, bool):
        raise HTTPException(status_code=400, detail="is_active 값이 필요합니다.")
    try:
        user = await user_service.update_user_active(user_id, is_active)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.") from exc
    return UserPublic(**user.model_dump())


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
) -> dict:
    try:
        await user_service.delete_user(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.") from exc
    except AttributeError:
        raise HTTPException(status_code=501, detail="사용자 삭제 기능이 지원되지 않습니다.")
    return {"ok": True}


@router.get("/stats/savings/csv")
async def admin_savings_csv(
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    current_user: User = Depends(require_admin),
    stats_service: StatsService = Depends(get_stats_service),
) -> StreamingResponse:
    stats = await stats_service.get_usage_stats(from_dt=from_dt, to_dt=to_dt)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "사용자ID",
            "이름",
            "이메일",
            "총Run수",
            "통과모듈수",
            "실패모듈수",
            "자동화실행시간(분)",
            "절감시간",
            "시스템코드",
            "시스템명",
            "시스템별Run수",
            "시스템별통과모듈",
            "시스템별절감시간",
        ]
    )

    for u in stats.by_user:
        automation_min = round((u.total_duration_ms or 0) / 60000, 1)
        for s in u.by_system:
            writer.writerow(
                [
                    u.user_id or "",
                    u.user_name or "(시스템)",
                    u.email or "",
                    u.total_runs,
                    u.total_modules_passed,
                    u.total_modules_failed,
                    automation_min,
                    _fmt_saved_seconds(u.manual_seconds_saved),
                    s.system_code,
                    s.system_name,
                    s.runs,
                    s.modules_passed,
                    _fmt_saved_seconds(s.manual_seconds_saved),
                ]
            )

    date_str = datetime.now().strftime("%Y%m%d")
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename=savings_{date_str}.csv"},
    )


@router.get("/systems")
async def admin_list_systems(
    current_user: User = Depends(require_admin),
    registry: ModuleRegistry = Depends(get_registry),
) -> list[dict]:
    return [{"system_code": s.system_code, "system_name": s.name} for s in registry.list_systems()]


@router.put("/users/{user_id}/systems")
async def admin_update_user_systems(
    user_id: str,
    payload: dict,
    current_user: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
) -> UserPublic:
    codes = payload.get("allowed_system_codes")
    if not isinstance(codes, list):
        raise HTTPException(status_code=400, detail="allowed_system_codes 목록이 필요합니다.")
    try:
        user = await user_service.update_user_systems(user_id, codes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.") from exc
    return UserPublic(**user.model_dump())


@router.get("/module-settings")
async def admin_list_module_settings(
    current_user: User = Depends(require_admin),
    registry: ModuleRegistry = Depends(get_registry),
    repo=Depends(get_module_settings_repo),
) -> list[dict]:
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
            modules.append(
                {
                    "module_id": m.module_id,
                    "name": m.name,
                    "estimated_manual_seconds": seconds,
                    "manifest_default": m.estimated_manual_seconds,
                    "is_overridden": is_overridden,
                }
            )
        result.append(
            {
                "system_code": system.system_code,
                "system_name": system.name,
                "modules": modules,
            }
        )
    return result


@router.put("/module-settings/systems/{system_code}")
async def admin_bulk_update_module_settings(
    system_code: str,
    payload: dict,
    current_user: User = Depends(require_admin),
    registry: ModuleRegistry = Depends(get_registry),
    repo=Depends(get_module_settings_repo),
) -> dict:
    modules = payload.get("modules")
    if not isinstance(modules, list) or not modules:
        raise HTTPException(status_code=400, detail="modules 목록이 필요합니다.")

    try:
        system = registry.get_system(system_code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="시스템을 찾을 수 없습니다.") from exc

    allowed_ids = {m.module_id for m in system.modules}

    for item in modules:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="modules 항목 형식이 올바르지 않습니다.")
        module_id = item.get("module_id")
        if not isinstance(module_id, str) or module_id not in allowed_ids:
            raise HTTPException(
                status_code=400,
                detail=f"{module_id}는 이 시스템에 속하지 않습니다.",
            )
        seconds = item.get("estimated_manual_seconds")
        if not isinstance(seconds, int) or seconds < 0:
            raise HTTPException(status_code=400, detail="estimated_manual_seconds 값이 필요합니다.")

    if repo is None:
        raise HTTPException(status_code=503, detail="모듈 설정 저장소가 초기화되지 않았습니다.")

    from datetime import datetime

    now = datetime.now(UTC)
    saved: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []

    for item in modules:
        module_id = item["module_id"]
        seconds = item["estimated_manual_seconds"]
        try:
            settings = ModuleSettings(
                module_id=module_id,
                estimated_manual_seconds=seconds,
                updated_at=now,
            )
            await repo.save(settings)
            saved.append({"module_id": module_id, "estimated_manual_seconds": seconds})
        except Exception as exc:
            failed.append({"module_id": module_id, "detail": str(exc)})

    if failed:
        return {
            "ok": False,
            "system_code": system_code,
            "saved": saved,
            "failed": failed,
        }

    return {"ok": True, "system_code": system_code, "saved": saved}


@router.put("/module-settings/{module_id:path}")
async def admin_update_module_settings(
    module_id: str,
    payload: dict,
    current_user: User = Depends(require_admin),
    repo=Depends(get_module_settings_repo),
) -> dict:
    seconds = payload.get("estimated_manual_seconds")
    if not isinstance(seconds, int) or seconds < 0:
        raise HTTPException(status_code=400, detail="estimated_manual_seconds 값이 필요합니다.")

    if repo is None:
        raise HTTPException(status_code=503, detail="모듈 설정 저장소가 초기화되지 않았습니다.")

    from datetime import datetime

    settings = ModuleSettings(
        module_id=module_id,
        estimated_manual_seconds=seconds,
        updated_at=datetime.now(UTC),
    )
    await repo.save(settings)
    return {"ok": True, "module_id": module_id, "estimated_manual_seconds": seconds}
