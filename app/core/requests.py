"""HTTP 요청 본문 DTO — API 라우트가 파싱하고 서비스 호출로 번역한다.

전 계층이 참조 가능하도록 공유 커널(``app.core``)에 둔다(서비스가 ``app.api`` 를 import 하는
역방향 계층 의존을 피한다). 순수 pydantic — 도메인 엔티티에 의존하지 않는다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreatePresetRequest(BaseModel):
    system_code: str
    name: str
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None


class UpdatePresetRequest(BaseModel):
    name: str | None = None
    input_data: dict[str, str] | None = None
    selected_module_ids: list[str] | None = None


class StartRunRequest(BaseModel):
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None


class SubmitOtpRequest(BaseModel):
    otp_code: str


class InboundOtpRequest(BaseModel):
    """SMS 중계기(안드로이드/문자 포워더)가 보내는 인바운드 OTP 요청.

    ``run_id`` 없이 코드만 보낸다(중계기는 어느 Run 이 대기 중인지 모른다). ``code`` 가 오면
    그대로 쓰고, 없으면 ``text``(SMS 원문)를 서버가 정규식으로 파싱한다.
    """

    code: str | None = None
    text: str | None = None


class CreateScheduleRequest(BaseModel):
    cron: str
    name: str = ""
    input_data: dict[str, str] = Field(default_factory=dict)
    selected_module_ids: list[str] | None = None
    enabled: bool = True


class CreateSuiteScheduleRequest(BaseModel):
    cron: str
    name: str = ""
    browser_mode: str = "headed"
    systems: dict[str, dict[str, str]] = Field(default_factory=dict)
    selected_system_codes: list[str] | None = None
    scope_system_codes: list[str] | None = None
    enabled: bool = True


class UpdateScheduleRequest(BaseModel):
    """예약 in-place 수정 요청 — None 인 필드는 기존 값을 유지한다.

    ``input_data`` 는 제공된 키만 덮어쓴다(빈 문자열 값은 무시). 저장된 인증값(PII)을
    화면에 되돌려주지 않고도 교체할 수 있게 하는 병합 규약이다.
    """

    name: str | None = None
    cron: str | None = None
    input_data: dict[str, str] | None = None
    selected_module_ids: list[str] | None = None
    # suite 예약 전용
    browser_mode: str | None = None
    selected_system_codes: list[str] | None = None


class PauseScheduleRequest(BaseModel):
    """일시 중지(~시각까지) 요청. ``paused_until=None`` 은 즉시 재개."""

    paused_until: datetime | None = None


class StartSuiteRequest(BaseModel):
    browser_mode: str = "headed"
    systems: dict[str, dict[str, str]] = Field(default_factory=dict)
    selected_system_codes: list[str] | None = None
    scope_system_codes: list[str] | None = None
