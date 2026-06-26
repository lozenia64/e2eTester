"""단계 핸들러의 **타입드 결과**(sealed union).

과거에는 단계 함수가 평범한 ``str`` 을 돌려주고, OTP 등 사용자 입력 대기를
``return f"{WAITING_INPUT_PREFIX}{message}"`` 처럼 **매직 문자열**로 표현했다. 즉
"사람 입력이 필요하다"는 일급 제어 신호가 반환값(데이터 평면)에 밀입국해, 실행 엔진이
``str.startswith("WAITING_INPUT::")`` 로 그 문자열을 sniff 해야만 제어 전이를 만들 수
있었다(제어 평면을 데이터 평면으로 운전하는 결합).

이 모듈은 그 in-band 프로토콜을 **명시적 타입**으로 대체한다. 단계 핸들러는 문자열이
아니라 아래 sealed union 중 하나를 돌려주고, 실행 엔진은 문자열 파싱이 아니라 타입
매칭으로 결과를 해석한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StepCompleted:
    """단계가 정상적으로 끝났다. ``message`` 는 모듈 요약 문구."""

    message: str


@dataclass(frozen=True)
class StepNeedsInput:
    """단계가 사람 입력(OTP 등)을 기다리며 Run 일시정지를 요청한다.

    ``prompt`` 는 대시보드에 보여줄 안내 문구다. 모듈 종료가 아니라 *일시정지* 이므로
    실행 엔진은 이 결과에서 스크린샷을 찍지 않는다.
    """

    prompt: str


# 단계 핸들러가 돌려줄 수 있는 모든 결과. 새 결과 종류(예: StepFailed)가 필요하면
# 여기에 추가하고 실행 엔진의 매칭을 확장한다(컴파일 타임에 분기 누락을 드러내기 위함).
StepOutcome = StepCompleted | StepNeedsInput
