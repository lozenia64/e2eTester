from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_registry, get_suite_service
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.models import StartSuiteRequest, SubmitOtpRequest
from app.orchestrator.suite_view import filter_suite_for_user, resolve_suite_request_for_user

if TYPE_CHECKING:
    from app.orchestrator.suite_service import SuiteService
    from app.registry.loader import ModuleRegistry

router = APIRouter(prefix="/api/suites", tags=["suites"])


@router.get("")
async def list_suites(
    current_user: User = Depends(get_current_user),
    suite_service: SuiteService = Depends(get_suite_service),
):
    return await suite_service.list_suite_summaries()


@router.post("")
async def start_suite(
    payload: StartSuiteRequest,
    current_user: User = Depends(get_current_user),
    suite_service: SuiteService = Depends(get_suite_service),
    registry: ModuleRegistry = Depends(get_registry),
):
    if current_user.role != "admin":
        all_codes = [s.system_code for s in registry.list_systems()]
        try:
            payload = resolve_suite_request_for_user(
                payload,
                all_system_codes=all_codes,
                allowed_system_codes=current_user.allowed_system_codes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        suite = await suite_service.start_suite(
            payload,
            user_id=current_user.user_id,
            user_name=current_user.name,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="System not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    suite = filter_suite_for_user(suite, current_user)
    return suite.model_dump(mode="json")


@router.get("/{suite_id}")
async def get_suite(
    suite_id: str,
    current_user: User = Depends(get_current_user),
    suite_service: SuiteService = Depends(get_suite_service),
):
    try:
        suite = await suite_service.get_suite(suite_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Suite not found") from exc
    suite = filter_suite_for_user(suite, current_user)
    return suite.model_dump(mode="json")


@router.post("/{suite_id}/cancel")
async def cancel_suite(
    suite_id: str,
    current_user: User = Depends(get_current_user),
    suite_service: SuiteService = Depends(get_suite_service),
):
    try:
        suite = await suite_service.cancel_suite(suite_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Suite not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    suite = filter_suite_for_user(suite, current_user)
    return suite.model_dump(mode="json")


@router.post("/{suite_id}/otp")
async def submit_suite_otp(
    suite_id: str,
    payload: SubmitOtpRequest,
    current_user: User = Depends(get_current_user),
    suite_service: SuiteService = Depends(get_suite_service),
):
    try:
        suite = await suite_service.submit_otp(suite_id, payload.otp_code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Suite not waiting for OTP") from exc
    suite = filter_suite_for_user(suite, current_user)
    return suite.model_dump(mode="json")
