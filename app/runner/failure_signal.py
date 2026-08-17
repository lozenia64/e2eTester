"""예외 객체 → ``FailureSignal`` 분류(실행 평면 전용).

Playwright 예외의 세부 판별에는 타입명·메시지 검사가 일부 불가피하다. 그 검사를 **이 모듈
안에만 가두는 것**이 이 파일의 존재 이유다. 도메인(``app/contexts/run/domain/``)은 결과
enum 만 보고, 문자열을 절대 보지 않는다.
"""

from __future__ import annotations

from app.core.enums import FailureSignal

# 예외 클래스 이름 → 신호. Playwright 를 import 하지 않고 이름으로 판별해,
# 이 모듈이 Playwright 설치 여부와 무관하게 동작하게 한다(API 프로세스에는 Playwright 가 없다).
_TYPE_NAME_SIGNALS: dict[str, FailureSignal] = {
    "TimeoutError": FailureSignal.TIMEOUT,
    "TargetClosedError": FailureSignal.SESSION_LOST,
}

# 메시지 부분 문자열 → 신호. 위에서부터 먼저 일치하는 것을 쓴다(순서가 의미를 가진다).
_MESSAGE_SIGNALS: tuple[tuple[str, FailureSignal], ...] = (
    ("net::", FailureSignal.NAVIGATION),
    ("navigation", FailureSignal.NAVIGATION),
    ("err_", FailureSignal.NAVIGATION),
    ("target page, context or browser has been closed", FailureSignal.SESSION_LOST),
    ("browser has been closed", FailureSignal.SESSION_LOST),
    ("execution context was destroyed", FailureSignal.SESSION_LOST),
    ("waiting for selector", FailureSignal.SELECTOR_MISS),
    ("waiting for locator", FailureSignal.SELECTOR_MISS),
    ("resolved to 0 elements", FailureSignal.SELECTOR_MISS),
    ("no node found for selector", FailureSignal.SELECTOR_MISS),
    ("timeout", FailureSignal.TIMEOUT),
    ("dialog", FailureSignal.DIALOG),
)


def classify_failure(exc: BaseException) -> FailureSignal:
    """예외를 복구 등급 결정에 쓸 신호로 분류한다. **절대 예외를 던지지 않는다.**"""
    # RuntimeError 는 page object 가 "사이트가 이상하다"를 알리려고 던지는 신호다
    # (workflow_engine 이 이미 ANOMALY 로 가르는 기준과 동일하게 유지한다).
    if type(exc) is RuntimeError:
        return FailureSignal.SITE

    signal = _TYPE_NAME_SIGNALS.get(type(exc).__name__)
    if signal is not None:
        return signal

    try:
        message = str(exc).lower()
    except Exception:  # 분류 실패가 점검 결과를 더 망치지 않게 격리한다.
        return FailureSignal.UNKNOWN

    for needle, mapped in _MESSAGE_SIGNALS:
        if needle in message:
            return mapped
    return FailureSignal.UNKNOWN
