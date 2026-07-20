"""스케줄 타임존 기준 날짜 라벨 — 컨텍스트 무관 순수 유틸."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.logging import get_logger
from app.core.settings import get_settings

logger = get_logger(__name__)

DEFAULT_SCHEDULE_TIMEZONE = "Asia/Seoul"


def resolve_schedule_timezone() -> tuple[ZoneInfo, str]:
    settings = get_settings()
    name = (settings.schedule_tz or "").strip() or DEFAULT_SCHEDULE_TIMEZONE
    try:
        return ZoneInfo(name), name
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(
            "알 수 없는 타임존, UTC 로 대체",
            log_event="schedule.timezone_fallback",
            timezone=name,
        )
        return ZoneInfo("UTC"), "UTC"


def schedule_day_label(moment: datetime) -> str:
    """스케줄 타임존 기준 **해당 시각**의 날짜 라벨(YYYY-MM-DD).

    프로젝션은 벽시계(오늘)가 아니라 이벤트 발생 시각으로 날짜를 귀속시켜야 리빌드
    (과거 이벤트 재생) 시에도 같은 행이 재현된다 — 결정적 프로젝션의 전제.
    """
    tz, _ = resolve_schedule_timezone()
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return aware.astimezone(tz).strftime("%Y-%m-%d")
