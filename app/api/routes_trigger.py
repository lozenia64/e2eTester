"""모바일 즉시 점검 트리거 (예약 기반 · 토큰 인증).

예약(Schedule)마다 발급되는 비밀 트리거 토큰으로, 대시보드 로그인(JWT 쿠키) 없이 모바일
브라우저에서 URL 접속만으로 해당 예약의 "지금 실행"과 동일한 점검을 수행한다.

설계 원칙: ``GET /m/{token}`` 은 **부수효과가 없는** 모바일 페이지만 돌려주고, 실제 실행은
페이지 스크립트가 호출하는 ``POST /api/trigger/{token}`` 이 수행한다 — 메신저 링크
미리보기(카카오톡 등)·브라우저 프리페치·북마크 동기화 같은 단순 GET 조회가 실 사이트
점검(실제 청구 접수 포함)을 오발사하지 않게 하기 위함이다. 토큰 불일치는 존재 여부를
구분하지 않고 일괄 404 로 응답하며, 예약 삭제가 곧 URL 폐기다. OTP 대기(WAITING_INPUT)
시에는 같은 페이지에서 ``POST /api/trigger/{token}/otp`` 로 인증번호를 제출할 수 있다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.dependencies import get_schedule_service
from app.core.models import Schedule, SubmitOtpRequest

if TYPE_CHECKING:
    from app.scheduling.scheduler import SchedulerService

router = APIRouter(tags=["trigger"])
templates = Jinja2Templates(directory="app/web/templates")


async def _get_schedule_by_token_or_404(
    schedule_service: SchedulerService, trigger_token: str
) -> Schedule:
    schedule = await schedule_service.find_by_trigger_token(trigger_token)
    if schedule is None:
        raise HTTPException(status_code=404, detail="유효하지 않은 점검 URL입니다.")
    return schedule


@router.get("/m/{trigger_token}", response_class=HTMLResponse)
async def mobile_trigger_page(
    request: Request,
    trigger_token: str,
    schedule_service: SchedulerService = Depends(get_schedule_service),
):
    """모바일 즉시 점검 페이지(부수효과 없음 — 실행은 페이지의 POST 가 담당)."""
    schedule = await _get_schedule_by_token_or_404(schedule_service, trigger_token)
    return templates.TemplateResponse(
        request,
        "mobile_trigger.html",
        {
            "schedule": schedule,
            "trigger_token": trigger_token,
        },
    )


@router.post("/api/trigger/{trigger_token}")
async def fire_trigger(
    trigger_token: str,
    schedule_service: SchedulerService = Depends(get_schedule_service),
):
    """예약의 "지금 실행"과 동일한 즉시 실행. 직전 실행이 진행 중이면 새로 만들지 않고
    그 실행 상태를 돌려준다(``already_running: true``)."""
    schedule = await _get_schedule_by_token_or_404(schedule_service, trigger_token)
    try:
        return await schedule_service.trigger_now(schedule.schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/trigger/{trigger_token}/status")
async def trigger_status(
    trigger_token: str,
    schedule_service: SchedulerService = Depends(get_schedule_service),
):
    """최근 실행 상태 요약(모바일 페이지 폴링용; 입력값 등 PII 미포함)."""
    schedule = await _get_schedule_by_token_or_404(schedule_service, trigger_token)
    try:
        return await schedule_service.trigger_status(schedule.schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.") from exc


@router.post("/api/trigger/{trigger_token}/otp")
async def submit_trigger_otp(
    trigger_token: str,
    payload: SubmitOtpRequest,
    schedule_service: SchedulerService = Depends(get_schedule_service),
):
    """대기 중(WAITING_INPUT) 실행에 OTP 를 제출해 재개한다."""
    schedule = await _get_schedule_by_token_or_404(schedule_service, trigger_token)
    try:
        return await schedule_service.submit_trigger_otp(schedule.schedule_id, payload.otp_code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="OTP 입력을 기다리는 실행이 없습니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
