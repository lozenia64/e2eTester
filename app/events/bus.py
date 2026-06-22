from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.core.models import Run, SuiteRun

EventHandler = Callable[[Any], Awaitable[None]]


@dataclass(frozen=True)
class RunFinished:
    """Run 이 최종 상태(PASSED/FAILED/CANCELLED)로 종료되었음을 알리는 도메인 이벤트."""

    run: Run


@dataclass(frozen=True)
class RunWaitingInput:
    """Run 이 사용자 입력(OTP) 대기로 일시정지했음을 알리는 도메인 이벤트.

    Suite Saga 가 하위 Run 의 일시정지를 프레젠테이션(WebSocket) 큐 폴링이 아니라 이
    도메인 이벤트로 감지해 Suite 상태에 반영하도록 한다.
    """

    run: Run


@dataclass(frozen=True)
class RunResumed:
    """일시정지된 Run 이 입력(OTP) 접수 후 재개되었음을 알리는 도메인 이벤트."""

    run: Run


@dataclass(frozen=True)
class SuiteFinished:
    """Suite 가 최종 상태(PASSED/FAILED/CANCELLED)로 종료되었음을 알리는 도메인 이벤트."""

    suite: SuiteRun
    runs: list[Run]


class EventBus:
    """프로세스 내 비동기 이벤트 버스.

    설계 원칙:
    - **비블로킹**: 핸들러는 백그라운드 태스크로 디스패치되어, ``publish`` 호출자(오케스트
      레이터의 종료 처리 등)를 절대 기다리게 하지 않는다.
    - **격리**: 한 구독자에서 난 예외가 다른 구독자나 발행자에 전파되지 않는다.
    - **무지(無知)**: 발행자는 누가 구독하는지 모른다(메일/AI 분석을 몰라도 된다).
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Any) -> None:
        for handler in list(self._handlers.get(type(event), [])):
            asyncio.create_task(self._safe_invoke(handler, event))

    @staticmethod
    async def _safe_invoke(handler: EventHandler, event: Any) -> None:
        try:
            await handler(event)
        except Exception as exc:  # 구독자 오류는 발행 흐름과 격리한다
            print(f"[event-bus] 구독자 처리 오류 ({type(event).__name__}): {exc}")
