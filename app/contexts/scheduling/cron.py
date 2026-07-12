"""cron 식 파싱·평가 — croniter 백엔드.

표준 5필드 cron(`분 시 일 월 요일`)을 지원한다. 각 필드는 `*`, 숫자, 목록(`,`),
범위(`-`), 스텝(`*/n`, `a-b/n`)을 조합할 수 있다. 요일은 0~6(0=일요일)이며 7도
일요일로 받는다. 일(day-of-month)과 요일(day-of-week)이 모두 제한되어 있으면 둘 중
하나라도 맞으면 실행하는 표준 cron 규칙을 따른다.

과거에는 의존성을 피하려 직접 1분 단위로 전진 탐색하는 파서를 두었으나, DST/타임존
경계 처리와 다음 실행 시각 계산을 croniter 에 위임한다. 공개 API(``parse_cron`` /
``CronSchedule.matches`` / ``next_run_after``)와 5필드 검증 계약은 그대로 유지한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from croniter import CroniterError
from croniter import croniter as _Croniter

_FIELD_COUNT = 5


@dataclass(frozen=True)
class CronSchedule:
    """검증된 cron 식. ``matches`` 로 특정 시각의 일치 여부를 평가한다."""

    expression: str

    def matches(self, moment: datetime) -> bool:
        # day_or=True: 일·요일이 모두 제한되면 둘 중 하나만 맞아도 실행(표준 cron 규칙).
        return _Croniter.match(self.expression, moment)


def parse_cron(expression: str) -> CronSchedule:
    """cron 식을 파싱·검증한다. 형식이 틀리면 ValueError 를 던진다."""
    fields = (expression or "").split()
    if len(fields) != _FIELD_COUNT:
        raise ValueError("cron 식은 '분 시 일 월 요일' 5개 필드여야 합니다. 예: 0 9 * * *")
    expr = " ".join(fields)
    try:
        # 생성자가 필드 범위·문법을 검증한다(CroniterError 는 ValueError 의 하위 클래스).
        _Croniter(expr)
    except CroniterError as exc:
        raise ValueError(f"잘못된 cron 식입니다: '{expression}' ({exc})") from exc
    return CronSchedule(expression=expr)


def next_run_after(expression: str, after: datetime) -> datetime:
    """`after` 이후(초과)의 첫 일치 시각을 반환한다. `after` 와 같은 tzinfo 를 유지한다."""
    schedule = parse_cron(expression)
    iterator = _Croniter(schedule.expression, after)
    return iterator.get_next(datetime)
