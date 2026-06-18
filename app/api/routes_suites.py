from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.models import StartSuiteRequest, SubmitOtpRequest

router = APIRouter(prefix="/api/suites", tags=["suites"])


@router.get("")
async def list_suites(request: Request, current_user: User = Depends(get_current_user)):
    return await request.app.state.suite_service.list_suite_summaries()


@router.post("")
async def start_suite(
    request: Request,
    payload: StartSuiteRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        suite = await request.app.state.suite_service.start_suite(
            payload,
            user_id=current_user.user_id,
            user_name=current_user.name,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="System not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return suite.model_dump(mode="json")


@router.get("/{suite_id}")
async def get_suite(
    request: Request,
    suite_id: str,
    current_user: User = Depends(get_current_user),
):
    try:
        suite = await request.app.state.suite_service.get_suite(suite_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Suite not found") from exc
    return suite.model_dump(mode="json")


@router.post("/{suite_id}/cancel")
async def cancel_suite(
    request: Request,
    suite_id: str,
    current_user: User = Depends(get_current_user),
):
    try:
        suite = await request.app.state.suite_service.cancel_suite(suite_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Suite not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return suite.model_dump(mode="json")


@router.post("/{suite_id}/otp")
async def submit_suite_otp(
    request: Request,
    suite_id: str,
    payload: SubmitOtpRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        suite = await request.app.state.suite_service.submit_otp(suite_id, payload.otp_code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Suite not waiting for OTP") from exc
    return suite.model_dump(mode="json")
