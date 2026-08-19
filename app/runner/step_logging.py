"""스텝 실행 로깅 능력 — 컨텍스트-로컬 싱크(전역 stdout 치환 대체).

과거 실행 엔진은 스텝 동안 ``contextlib.redirect_stdout`` 로 **프로세스 전역** ``sys.stdout``
을 교체해 PageObject 의 ``print()`` 를 가로챘다. 실행 큐는 최대 8개 모듈을 동시에 스레드에서
돌리므로, 각 스텝의 redirect 가 같은 전역 ``sys.stdout`` 을 서로 덮어써 로그가 다른 스텝의
파일/WS 스트림으로 새는 **경합**이 설계에 내장돼 있었다.

이 모듈은 그 전역 치환을 없앤다. 엔진은 스텝을 실행하기 직전(그 스텝이 도는 세션 스레드
위에서) ``push_sink`` 로 이 스텝의 로그 싱크를 ``ContextVar`` 에 설정하고, PageObject/스텝
핸들러는 ``print()`` 대신 ``log(...)`` 로 명시적으로 로그를 흘려보낸다. ``ContextVar`` 는
설정된 그 스레드/컨텍스트에서만 읽히므로, 동시 실행되는 다른 스텝 스레드가 서로의 싱크를
덮어쓸 수 없다(전역 상태 경합 제거). 싱크가 없으면 ``log`` 는 조용히 무시한다.
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable

LogSink = Callable[[str], None]

_sink: contextvars.ContextVar[LogSink | None] = contextvars.ContextVar(
    "e2e_step_log_sink", default=None
)


def push_sink(sink: LogSink) -> contextvars.Token:
    """현재 컨텍스트의 로그 싱크를 설정하고 복원용 토큰을 돌려준다(엔진 전용)."""
    return _sink.set(sink)


def pop_sink(token: contextvars.Token) -> None:
    """``push_sink`` 가 돌려준 토큰으로 이전 싱크를 복원한다(엔진 전용)."""
    _sink.reset(token)


def log(message: str = "") -> None:
    """현재 스텝의 로그 싱크로 한 줄을 흘려보낸다(싱크 미설정 시 무시).

    PageObject/스텝 핸들러가 ``print()`` 대신 호출한다 — 호출 형태가 동일해(단일 문자열
    인자) 기계적 치환이 안전하다. 빈 인자는 빈 줄이므로 싱크 단계에서 걸러진다.
    """
    sink = _sink.get()
    if sink is not None:
        sink(str(message))


def bind_log() -> LogSink:
    """현재 컨텍스트의 싱크에 **고정된** 로거를 돌려준다(이벤트 콜백 전용).

    Playwright sync API 의 이벤트 콜백(``page.on("dialog", ...)`` 등)은 dispatcher
    greenlet 에서 실행되고, greenlet 은 자체 contextvars 컨텍스트를 가지므로 그 안에서
    부른 ``log`` 은 싱크를 못 보고 **조용히 사라진다**. 실제로 대표홈페이지 방어 스크립트의
    alert 로그가 이렇게 유실돼, 운영자와 AI 분석이 원인을 오판했다.
    콜백을 등록하는 쪽(= 스텝 컨텍스트)에서 이 함수로 싱크를 미리 붙여 넘긴다.
    """
    sink = _sink.get()
    if sink is None:
        return lambda message="": None
    return lambda message="": sink(str(message))
