"""예외 객체 → FailureSignal 분류(순수 함수) 단위 테스트."""

from __future__ import annotations

import pytest

from app.core.enums import FailureSignal
from app.runner.failure_signal import classify_failure


def test_runtime_error_is_site_signal():
    """RuntimeError 는 page object 가 의도적으로 던지는 사이트 이상 신호다."""
    assert classify_failure(RuntimeError("계약목록을 찾지 못했습니다.")) is FailureSignal.SITE


def test_timeout_error_is_timeout_signal():
    class TimeoutError_(Exception):
        pass

    TimeoutError_.__name__ = "TimeoutError"
    assert classify_failure(TimeoutError_("Timeout 30000ms exceeded")) is FailureSignal.TIMEOUT


def test_target_closed_is_session_lost():
    class TargetClosedError(Exception):
        pass

    assert classify_failure(TargetClosedError("Target page closed")) is FailureSignal.SESSION_LOST


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ('waiting for selector "#btn" failed', FailureSignal.SELECTOR_MISS),
        ("net::ERR_CONNECTION_RESET at https://example.com", FailureSignal.NAVIGATION),
        ('navigation to "https://x" is interrupted', FailureSignal.NAVIGATION),
        ("Browser has been closed", FailureSignal.SESSION_LOST),
    ],
)
def test_message_based_classification(message: str, expected: FailureSignal):
    assert classify_failure(Exception(message)) is expected


def test_unrecognised_exception_is_unknown():
    assert classify_failure(ValueError("무언가 잘못됨")) is FailureSignal.UNKNOWN


def test_classification_never_raises():
    """분류 실패가 점검 자체를 망가뜨려서는 안 된다."""

    class Nasty(Exception):
        def __str__(self) -> str:
            raise ValueError("str() 폭발")

    assert classify_failure(Nasty()) is FailureSignal.UNKNOWN


# --- 결과 DTO 운반 -----------------------------------------------------------


def test_step_execution_result_defaults_to_unknown_signal():
    """기존 생성자 호출부가 무수정으로 동작해야 한다(하위호환)."""
    from app.execution.results import StepExecutionResult

    result = StepExecutionResult(
        status="ERROR",
        message="x",
        artifacts=[],
        current_url=None,
        dialog_messages=[],
    )
    assert result.failure_signal is FailureSignal.UNKNOWN


def test_step_execution_result_failure_helper_marks_site_signal():
    """StepExecutionResult.failure() 는 ANOMALY 를 만드는 헬퍼이므로 SITE 다."""
    from app.execution.results import StepExecutionResult

    result = StepExecutionResult.failure(
        message="사이트 이상",
        current_url=None,
        dialog_messages=[],
        last_error="boom",
    )
    assert result.failure_signal is FailureSignal.SITE
