"""의존성 없이 동작하는 최소 cron 구현.

표준 5필드 cron(`분 시 일 월 요일`)을 지원한다. 각 필드는 `*`, 숫자, 목록(`,`),
범위(`-`), 스텝(`*/n`, `a-b/n`)을 조합할 수 있다. 요일은 0~6(0=일요일)이며 7도
일요일로 받는다. 일(day-of-month)과 요일(day-of-week)이 모두 제한되어 있으면 둘 중
하나라도 맞으면 실행하는 표준 cron 규칙을 따른다.

croniter 같은 외부 패키지를 추가하지 않으려고 직접 구현했다. 매 분 단위로 전진하며
다음 일치 시각을 찾으므로(최대 ~366일 탐색) 초 단위 정밀도는 다루지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

_FIELD_BOUNDS: tuple[tuple[int, int], ...] = (
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 6),    # day of week (0 = Sunday)
)
_FIELD_NAMES = ("분", "시", "일", "월", "요일")
_SEARCH_LIMIT_MINUTES = 366 * 24 * 60


@dataclass(frozen=True)
class CronSchedule:
    minutes: frozenset[int]
    hours: frozenset[int]
    days_of_month: frozenset[int]
    months: frozenset[int]
    days_of_week: frozenset[int]
    dom_restricted: bool
    dow_restricted: bool

    def matches(self, moment: datetime) -> bool:
        if moment.minute not in self.minutes:
            return False
        if moment.hour not in self.hours:
            return False
        if moment.month not in self.months:
            return False
        # cron 요일: Monday=0(파이썬) -> Sunday=0 으로 변환
        dow = (moment.weekday() + 1) % 7
        dom_ok = moment.day in self.days_of_month
        dow_ok = dow in self.days_of_week
        if self.dom_restricted and self.dow_restricted:
            return dom_ok or dow_ok
        if self.dom_restricted:
            return dom_ok
        if self.dow_restricted:
            return dow_ok
        return True


def _parse_field(raw: str, index: int) -> tuple[frozenset[int], bool]:
    low, high = _FIELD_BOUNDS[index]
    name = _FIELD_NAMES[index]
    values: set[int] = set()
    restricted = True

    for part in raw.split(","):
        token = part.strip()
        if not token:
            raise ValueError(f"{name} 필드가 비어 있습니다.")

        step = 1
        if "/" in token:
            base, _, step_raw = token.partition("/")
            if not step_raw.isdigit() or int(step_raw) <= 0:
                raise ValueError(f"{name} 필드의 스텝 값이 올바르지 않습니다: '{token}'")
            step = int(step_raw)
            token = base.strip()

        if token == "*":
            start, end = low, high
            if step == 1:
                restricted = False
        elif "-" in token:
            start_raw, _, end_raw = token.partition("-")
            start, end = _to_int(start_raw, index), _to_int(end_raw, index)
            if start > end:
                raise ValueError(f"{name} 필드의 범위가 거꾸로입니다: '{part}'")
        else:
            start = end = _to_int(token, index)

        for value in range(start, end + 1, step):
            values.add(value)

    if not values:
        raise ValueError(f"{name} 필드에서 유효한 값을 찾지 못했습니다: '{raw}'")
    return frozenset(values), restricted


def _to_int(raw: str, index: int) -> int:
    token = raw.strip()
    if not token.lstrip("-").isdigit():
        raise ValueError(f"{_FIELD_NAMES[index]} 필드에 숫자가 아닌 값이 있습니다: '{raw}'")
    value = int(token)
    # 요일 필드의 7 은 일요일(0)로 정규화
    if index == 4 and value == 7:
        value = 0
    low, high = _FIELD_BOUNDS[index]
    if value < low or value > high:
        raise ValueError(f"{_FIELD_NAMES[index]} 필드 값이 범위({low}-{high})를 벗어났습니다: {value}")
    return value


def parse_cron(expression: str) -> CronSchedule:
    """cron 식을 파싱한다. 형식이 틀리면 ValueError 를 던진다."""
    fields = (expression or "").split()
    if len(fields) != 5:
        raise ValueError("cron 식은 '분 시 일 월 요일' 5개 필드여야 합니다. 예: 0 9 * * *")
    minutes, _ = _parse_field(fields[0], 0)
    hours, _ = _parse_field(fields[1], 1)
    days_of_month, dom_restricted = _parse_field(fields[2], 2)
    months, _ = _parse_field(fields[3], 3)
    days_of_week, dow_restricted = _parse_field(fields[4], 4)
    return CronSchedule(
        minutes=minutes,
        hours=hours,
        days_of_month=days_of_month,
        months=months,
        days_of_week=days_of_week,
        dom_restricted=dom_restricted,
        dow_restricted=dow_restricted,
    )


def next_run_after(expression: str, after: datetime) -> datetime:
    """`after` 이후(초과)의 첫 일치 시각을 반환한다. `after` 와 같은 tzinfo 를 유지한다."""
    schedule = parse_cron(expression)
    # 다음 분 경계부터 탐색 (초/마이크로초 버림)
    candidate = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
    for _ in range(_SEARCH_LIMIT_MINUTES):
        if schedule.matches(candidate):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError(f"cron 식 '{expression}' 의 다음 실행 시각을 찾지 못했습니다.")
