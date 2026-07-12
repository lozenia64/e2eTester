"""SMS 중계 인바운드 OTP 엔드포인트.

안드로이드 SMS 중계기(또는 문자 포워더 앱)가 수신한 OTP 를 서버로 전달하면, 서버가 현재
``WAITING_INPUT`` 으로 멈춰 있는 Run 을 찾아 OTP 를 주입해 재개한다(``RunService.submit_otp_to_waiting``).
사용자 세션이 아니라 **기기 토큰**(``X-OTP-Relay-Token`` 헤더)으로 인증하며, ``E2E_OTP_RELAY_TOKEN``
미설정 시 기능은 비활성(503)이다 — AI/메일과 동일하게 off-by-default. OTP 는 응답/로그에 남기지 않는다.
"""

from __future__ import annotations

import hmac
import re
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.dependencies import get_otp_relay_regex, get_otp_relay_token, get_run_service
from app.core.requests import InboundOtpRequest

if TYPE_CHECKING:
    from app.contexts.run.application.service import RunService

# SMS 원문에서 OTP 를 뽑을 기본 정규식: 연속된 4~8 자리 숫자의 첫 매치.
# 회사 SMS 형식에 맞춰 E2E_OTP_RELAY_REGEX 로 재정의할 수 있다(첫 캡처 그룹 사용).
DEFAULT_OTP_RELAY_REGEX = r"(\d{4,8})"

# 최종 코드 형식 검증(기존 본인인증 단계의 resolve_otp_code 와 동일한 4~8 자리 규칙).
_OTP_CODE_RE = re.compile(r"\d{4,8}")

router = APIRouter(prefix="/api/otp", tags=["otp"])


def _extract_code(payload: InboundOtpRequest, pattern: str | None) -> str | None:
    """요청에서 OTP 코드를 추출·검증한다(없거나 형식 위반이면 None).

    ``code`` 가 오면 그대로 4~8 자리 검증, 없으면 ``text``(SMS 원문)를 정규식으로 파싱한다.
    잘못된 정규식이 설정돼 있어도 기본 정규식으로 폴백한다.
    """
    if payload.code:
        candidate = payload.code.strip()
        return candidate if _OTP_CODE_RE.fullmatch(candidate) else None
    if not payload.text:
        return None
    try:
        match = re.search(pattern or DEFAULT_OTP_RELAY_REGEX, payload.text)
    except re.error:
        match = re.search(DEFAULT_OTP_RELAY_REGEX, payload.text)
    if not match:
        return None
    candidate = (match.group(1) if match.groups() else match.group(0)).strip()
    return candidate if _OTP_CODE_RE.fullmatch(candidate) else None


@router.post("/inbound")
async def submit_inbound_otp(
    payload: InboundOtpRequest,
    x_otp_relay_token: str | None = Header(default=None, alias="X-OTP-Relay-Token"),
    configured_token: str | None = Depends(get_otp_relay_token),
    relay_regex: str | None = Depends(get_otp_relay_regex),
    run_service: RunService = Depends(get_run_service),
):
    """중계기가 보낸 OTP 를 현재 대기 중인 Run 에 주입해 재개한다.

    Run/Suite 공통: Run 을 재개하면 ``RunResumed`` 도메인 이벤트로 Suite Saga 가 자동 반영된다.
    대기 중 Run 이 없으면 404, 토큰 불일치는 401, 기능 비활성은 503 으로 응답한다.
    """
    if not configured_token:
        raise HTTPException(status_code=503, detail="OTP 중계 기능이 비활성화되어 있습니다.")
    if not x_otp_relay_token or not hmac.compare_digest(x_otp_relay_token, configured_token):
        raise HTTPException(status_code=401, detail="유효하지 않은 중계 토큰입니다.")

    code = _extract_code(payload, relay_regex)
    if code is None:
        raise HTTPException(status_code=400, detail="유효한 OTP 코드를 찾지 못했습니다.")

    try:
        run = await run_service.submit_otp_to_waiting(code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="OTP 입력을 기다리는 Run이 없습니다.") from exc
    return {"run_id": run.run_id, "status": run.status.value}
