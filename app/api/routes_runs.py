from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.models import StartRunRequest, SubmitOtpRequest


router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("/systems/{system_code}")
async def start_system_run(request: Request, system_code: str, payload: StartRunRequest):
    try:
        run = await request.app.state.run_service.start_run(system_code, payload.input_data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="System not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return run.model_dump(mode="json")


@router.post("/{run_id}/otp")
async def submit_run_otp(request: Request, run_id: str, payload: SubmitOtpRequest):
    try:
        run = await request.app.state.run_service.submit_otp(run_id, payload.otp_code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not waiting for OTP") from exc
    return run.model_dump(mode="json")


@router.get("/{run_id}")
async def get_run(request: Request, run_id: str):
    try:
        run = await request.app.state.run_service.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return run.model_dump(mode="json")


@router.get("/{run_id}/nodes")
async def get_run_nodes(request: Request, run_id: str):
    try:
        run = await request.app.state.run_service.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    return [module.model_dump(mode="json") for module in run.modules]
