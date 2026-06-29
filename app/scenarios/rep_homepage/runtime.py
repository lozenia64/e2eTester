"""대표홈페이지 시나리오 공용 런타임 (PC·모바일 단일 타입).

기존의 ``HomWorkflowRuntime`` / ``MhmWorkflowRuntime`` 은 클래스 이름만 다른 동일
dataclass 였다. 채널 차이는 데이터(`channel: ChannelProfile`)로 들고, 런타임 타입은
하나로 통합한다. `WorkflowRuntime` Protocol(공용 실행 엔진 계약)을 그대로 만족한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.scenarios.rep_homepage.channel import ChannelProfile


@dataclass
class RepHomepageRuntime:
    channel: ChannelProfile
    config: Any
    playwright_manager: object
    browser: object
    context: object
    page: object
    dialog_messages: list[str]
    # 실행 스레드 풀은 게이트웨이 세션이 소유한다(런타임은 자기 브라우저 상태만 안다).
    # 휴대폰인증은 SMS 요청 → (OTP 대기) → OTP 제출 두 단계로 나뉘므로, 이미 SMS 를
    # 요청했는지를 런타임에 들고 OTP 재개 시 같은 세션에서 이어서 진행한다.
    phone_login_sms_requested: bool = False
    closed: bool = False
