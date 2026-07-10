"""예약 점검 관리 센터 — 순수 빌더.

관제 보드의 문제 분류(stuck/failing/missed/stale), 캘린더의 cron 전개·계획 vs 실적 매칭,
예약별 실행 이력 통계(성공률/평균 소요/연속 성공), cron 식의 한글 라벨 같은 **규칙**은 전부
여기 순수 함수가 가진다. ``SchedulerService`` 는 저장소/서비스에서 데이터를 모아 이 빌더에
넘기고 결과를 응답으로 조립하는 얇은 인터프리터다(``insights_*``/``stats_*`` 빌더와 같은
패턴 — 브라우저/DB 없이 단위 테스트한다: ``tests/test_schedule_center.py``).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.scheduling.cron import next_run_after

# 관제 보드 판정 기준(사람이 튜닝하는 정책 값).
FAILING_MIN_CONSECUTIVE = 2  # 최근 종료 실행이 연달아 이만큼 ERROR/ANOMALY 면 '연속 실패 중'
MISSED_WINDOW_HOURS = 24  # last_skipped_at 이 이 안이면 '실행 누락/건너뜀'
STALE_DISABLED_DAYS = 7  # 꺼진 상태로 이 일수를 넘기면 '꺼진 지 오래'
COVERAGE_WINDOW_HOURS = 24  # 시스템 커버리지: 최근 24h 내 점검됐는가
CLUSTER_WARN_THRESHOLD = 3  # 같은 (요일,시) 슬롯에 계획 블록이 이만큼 몰리면 경고

# 계획(occurrence) ↔ 실적(Run/Suite) 매칭 허용 오차. 스케줄러 tick(20s)·큐 대기를 감안해
# 계획 시각보다 조금 이르거나(시계 오차) 몇 분 늦게 시작한 실행을 같은 칸으로 본다.
MATCH_BEFORE = timedelta(minutes=2)
MATCH_AFTER = timedelta(minutes=20)

# 캘린더 전개 상한(폭주 방지 — 1분 주기 예약을 한 주로 펼치면 10,080개가 된다).
MAX_OCCURRENCES_PER_SCHEDULE = 400

_FAILURE_STATUSES = {"ERROR", "ANOMALY", "FAILED"}  # FAILED 는 레거시 → ANOMALY 취급
_ACTIVE_STATUSES = {"PENDING", "RUNNING", "WAITING_INPUT"}
_DOW_LABELS = ["일", "월", "화", "수", "목", "금", "토"]  # cron 0=일요일


@dataclass(frozen=True)
class ExecutionPoint:
    """예약이 트리거한 실행(Run 또는 Suite) 한 건의 최소 투영."""

    execution_id: str
    kind: str  # "run" | "suite"
    status: str  # RunStatus/SuiteStatus 의 value 문자열
    requested_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @property
    def link(self) -> str:
        return (
            f"/suites/{self.execution_id}" if self.kind == "suite" else f"/runs/{self.execution_id}"
        )

    @property
    def duration_ms(self) -> int | None:
        if self.started_at is None or self.ended_at is None:
            return None
        return max(0, int((self.ended_at - self.started_at).total_seconds() * 1000))


def normalize_status(status: str | None) -> str | None:
    """레거시 FAILED 를 ANOMALY 로 접는다(표시/집계 규칙과 동일)."""
    if status is None:
        return None
    return "ANOMALY" if status == "FAILED" else status


# --------------------------------------------------------------------------- #
# cron 한글 라벨
# --------------------------------------------------------------------------- #
def cron_to_label(cron: str) -> str:
    """자주 쓰는 cron 패턴을 사람이 읽는 한글 라벨로 옮긴다. 모르는 형태는 원문 그대로."""
    fields = (cron or "").split()
    if len(fields) != 5:
        return cron
    minute, hour, dom, month, dow = fields
    if month != "*":
        return cron

    # 주기 반복형: */n
    if minute.startswith("*/") and hour == "*" and dom == "*" and dow == "*":
        return f"{minute[2:]}분마다"
    if minute.isdigit() and hour.startswith("*/") and dom == "*" and dow == "*":
        return f"{hour[2:]}시간마다"

    if not (minute.isdigit() and hour.isdigit()):
        return cron
    time_label = f"{int(hour):02d}:{int(minute):02d}"

    if dom == "*" and dow == "*":
        return f"매일 {time_label}"
    if dom == "*" and dow == "1-5":
        return f"평일 {time_label}"
    if dom == "*" and _is_dow_list(dow):
        days = "·".join(_DOW_LABELS[int(d) % 7] for d in dow.split(","))
        return f"매주 {days} {time_label}"
    if dow == "*" and dom.isdigit():
        return f"매월 {int(dom)}일 {time_label}"
    return cron


def _is_dow_list(dow: str) -> bool:
    parts = dow.split(",")
    return all(part.isdigit() and 0 <= int(part) <= 7 for part in parts)


# --------------------------------------------------------------------------- #
# cron 전개 (캘린더 계획 블록)
# --------------------------------------------------------------------------- #
def expand_occurrences(
    cron: str,
    start: datetime,
    end: datetime,
    cap: int = MAX_OCCURRENCES_PER_SCHEDULE,
) -> list[datetime]:
    """반개구간 ``[start, end)`` 의 cron 일치 시각을 시간순으로 펼친다(상한 cap).

    ``next_run_after`` 는 엄격히 '이후'만 반환하므로 커서를 1초 물려 시작 경계를
    포함시킨다 — 자정(00:00) cron 이 그 날 캘린더/오늘 예정 카운트에서 빠지고
    다음 날 경계가 이중 계산되는 경계 버그를 막는다.
    """
    occurrences: list[datetime] = []
    cursor = start - timedelta(seconds=1)
    while len(occurrences) < cap:
        cursor = next_run_after(cron, cursor)
        if cursor >= end:
            break
        occurrences.append(cursor)
    return occurrences


def match_occurrences(
    occurrences: list[datetime],
    executions: list[ExecutionPoint],
    now: datetime,
) -> list[dict]:
    """계획 시각마다 실적(실행)을 짝지어 캘린더 블록을 만든다.

    - 미래 계획 → ``planned``
    - 과거 계획 + 매칭 실행 있음 → 실행 상태(active 면 ``active``)
    - 과거 계획 + 매칭 실행 없음 → ``missed`` (회색 빗금 — 침묵 실패 노출)
    남는(어느 계획에도 안 붙은) 실행은 ``unplanned`` 실적 블록으로 덧붙인다(지금 실행/모바일 트리거).
    """
    remaining = sorted(executions, key=lambda e: e.requested_at)
    blocks: list[dict] = []
    for occurrence in occurrences:
        if occurrence > now:
            blocks.append({"at": occurrence, "state": "planned"})
            continue
        matched: ExecutionPoint | None = None
        for execution in remaining:
            delta = execution.requested_at - occurrence
            if -MATCH_BEFORE <= delta <= MATCH_AFTER:
                matched = execution
                break
            if delta > MATCH_AFTER:
                break
        if matched is None:
            blocks.append({"at": occurrence, "state": "missed"})
            continue
        remaining.remove(matched)
        blocks.append(_execution_block(occurrence, matched))
    for execution in remaining:
        if execution.requested_at > now:
            continue
        block = _execution_block(execution.requested_at, execution)
        block["unplanned"] = True
        blocks.append(block)
    blocks.sort(key=lambda block: block["at"])
    return blocks


def _execution_block(at: datetime, execution: ExecutionPoint) -> dict:
    status = normalize_status(execution.status)
    return {
        "at": at,
        "state": "active" if status in _ACTIVE_STATUSES else status,
        "execution_id": execution.execution_id,
        "link": execution.link,
    }


def cluster_warnings(planned_blocks: list[tuple[str, datetime]]) -> list[dict]:
    """같은 (요일, 시) 슬롯에 계획이 과다하게 몰린 곳을 찾는다(리소스 몰림 경고).

    ``planned_blocks`` 는 (schedule_id, 계획 시각) 쌍 — 같은 예약이 그 슬롯에 여러 번
    걸려도 예약 수 기준으로 센다.
    """
    per_slot: dict[tuple[int, int], set[str]] = {}
    for schedule_id, at in planned_blocks:
        slot = (int(at.strftime("%w")), at.hour)
        per_slot.setdefault(slot, set()).add(schedule_id)
    warnings = [
        {
            "dow": slot[0],
            "hour": slot[1],
            "label": f"{_DOW_LABELS[slot[0]]} {slot[1]:02d}시",
            "schedule_count": len(ids),
        }
        for slot, ids in per_slot.items()
        if len(ids) >= CLUSTER_WARN_THRESHOLD
    ]
    warnings.sort(key=lambda w: (-w["schedule_count"], w["dow"], w["hour"]))
    return warnings


def build_coverage(
    systems: list[tuple[str, str]],
    last_checked_at: dict[str, datetime],
    now: datetime,
) -> list[dict]:
    """시스템별 '최근 24h 내 점검됨?' 체크리스트(점검 공백 진단)."""
    window_start = now - timedelta(hours=COVERAGE_WINDOW_HOURS)
    coverage = []
    for system_code, system_name in systems:
        checked_at = last_checked_at.get(system_code)
        coverage.append(
            {
                "system_code": system_code,
                "system_name": system_name,
                "covered": checked_at is not None and checked_at >= window_start,
                "last_checked_at": checked_at.isoformat() if checked_at else None,
            }
        )
    return coverage


# --------------------------------------------------------------------------- #
# 관제 보드 분류 (management by exception)
# --------------------------------------------------------------------------- #
def classify_issues(
    *,
    enabled: bool,
    paused_until: datetime | None,
    last_status: str | None,
    last_skipped_at: datetime | None,
    disabled_at: datetime | None,
    created_at: datetime,
    last_run_at: datetime | None,
    recent_executions: list[ExecutionPoint],
    now: datetime,
) -> list[dict]:
    """예약 하나의 '조치 필요' 이슈 목록. 정상 예약은 빈 리스트(스캔만 하고 지나간다)."""
    issues: list[dict] = []

    last = normalize_status(last_status)
    if last == "WAITING_INPUT":
        issues.append({"type": "stuck"})

    terminal = [
        normalize_status(e.status)
        for e in sorted(recent_executions, key=lambda e: e.requested_at, reverse=True)
        if normalize_status(e.status) not in _ACTIVE_STATUSES
    ]
    streak = 0
    for status in terminal:
        if status in _FAILURE_STATUSES:
            streak += 1
        else:
            break
    if streak >= FAILING_MIN_CONSECUTIVE:
        issues.append({"type": "failing", "consecutive_failures": streak})

    if last_skipped_at is not None and now - last_skipped_at <= timedelta(
        hours=MISSED_WINDOW_HOURS
    ):
        issues.append({"type": "missed", "skipped_at": last_skipped_at.isoformat()})

    if not enabled:
        since = disabled_at or last_run_at or created_at
        stale_days = (now - since).days
        if stale_days >= STALE_DISABLED_DAYS:
            issues.append({"type": "stale", "disabled_days": stale_days})

    return issues


def count_today_planned(cron: str, day_start: datetime, day_end: datetime) -> int:
    """스케줄 타임존 기준 '오늘' 하루에 계획된 실행 횟수."""
    return len(expand_occurrences(cron, day_start, day_end, cap=MAX_OCCURRENCES_PER_SCHEDULE))


# --------------------------------------------------------------------------- #
# 예약별 실행 이력 통계 (이 예약은 신뢰할 수 있는가)
# --------------------------------------------------------------------------- #
def build_history_stats(executions: list[ExecutionPoint]) -> dict:
    """최근 실행들(최신 우선 입력)을 점 스트립 + 신뢰도 지표로 요약한다.

    - success_rate: 종료 실행(취소 제외) 중 PASSED 비율
    - avg_duration_ms: 소요를 알 수 있는 종료 실행 평균
    - current_streak: 최신부터 연속 PASSED 개수
    - dots: 과거→최신 순(스트립 왼→오른쪽 렌더링용)
    """
    ordered = sorted(executions, key=lambda e: e.requested_at, reverse=True)
    counts: Counter[str] = Counter()
    durations: list[int] = []
    dots: list[dict] = []
    for execution in ordered:
        status = normalize_status(execution.status) or "ERROR"
        state = "active" if status in _ACTIVE_STATUSES else status
        counts[state] += 1
        duration = execution.duration_ms
        if duration is not None and state not in ("active", "CANCELLED"):
            durations.append(duration)
        dots.append(
            {
                "state": state,
                "at": execution.requested_at.isoformat(),
                "execution_id": execution.execution_id,
                "link": execution.link,
                "duration_ms": duration,
            }
        )

    countable = sum(
        count for state, count in counts.items() if state not in ("active", "CANCELLED")
    )
    passed = counts.get("PASSED", 0)
    streak = 0
    for dot in dots:
        if dot["state"] == "active":
            continue
        if dot["state"] == "PASSED":
            streak += 1
        else:
            break

    dots.reverse()
    return {
        "total": len(ordered),
        "passed": passed,
        "anomaly": counts.get("ANOMALY", 0),
        "error": counts.get("ERROR", 0),
        "cancelled": counts.get("CANCELLED", 0),
        "active": counts.get("active", 0),
        "success_rate": round(passed / countable * 100, 1) if countable else None,
        "avg_duration_ms": int(sum(durations) / len(durations)) if durations else None,
        "current_streak": streak,
        "dots": dots,
    }
