from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.contexts.identity.service import UserService
    from app.contexts.scheduling.infrastructure.ports import ScheduleRepositoryPort
    from app.contexts.suite.contracts.ports import SuiteSummaryQueryPort
    from app.contexts.suite.contracts.query_rows import SuiteSummaryRow
    from app.core.schedule_models import Schedule


class RunActorSource(Protocol):
    """실행자 해석에 필요한 최소 속성 계약 — ``Run`` 엔티티든 요약 행이든 만족한다."""

    created_by_user_id: str | None
    created_by_user_name: str | None
    suite_id: str | None
    schedule_id: str | None


def _lookup_user(
    user_id: str | None,
    users_by_id: dict[str, tuple[str, str | None]] | None,
) -> tuple[str | None, str | None]:
    if not user_id:
        return None, None
    if users_by_id and user_id in users_by_id:
        name, _email = users_by_id[user_id]
        return user_id, name
    return user_id, None


def resolve_run_actor(
    run: RunActorSource,
    *,
    users_by_id: dict[str, tuple[str, str | None]] | None = None,
    suites_by_id: dict[str, Any] | None = None,
    schedules_by_id: dict[str, Schedule] | None = None,
) -> tuple[str | None, str | None]:
    """Run 의 실행자(user_id, user_name) 를 표시·집계용으로 해석한다.

    저장 시점에 이름이 빠진 과거 Run(Suite·예약 하위 Run 등)은 상위 엔티티·user 조회로 보완한다.
    상위 Suite 는 요약 행(``SuiteSummaryRow``)이면 충분하다(created_by_* 만 읽는다).
    """
    user_id = run.created_by_user_id
    user_name = run.created_by_user_name

    if user_name:
        return user_id, user_name

    resolved = _lookup_user(user_id, users_by_id)
    if resolved[1]:
        return resolved

    if run.suite_id and suites_by_id and run.suite_id in suites_by_id:
        suite = suites_by_id[run.suite_id]
        if suite.created_by_user_name:
            return suite.created_by_user_id, suite.created_by_user_name
        resolved = _lookup_user(suite.created_by_user_id, users_by_id)
        if resolved[1]:
            return resolved

    if run.schedule_id and schedules_by_id and run.schedule_id in schedules_by_id:
        schedule = schedules_by_id[run.schedule_id]
        if schedule.created_by_user_name:
            return schedule.created_by_user_id, schedule.created_by_user_name
        resolved = _lookup_user(schedule.created_by_user_id, users_by_id)
        if resolved[1]:
            return resolved

    return user_id, user_name


@dataclass(frozen=True)
class ActorContext:
    users_by_id: dict[str, tuple[str, str | None]]
    suites_by_id: dict[str, SuiteSummaryRow]
    schedules_by_id: dict[str, Schedule]

    def resolve(self, run: RunActorSource) -> tuple[str | None, str | None]:
        return resolve_run_actor(
            run,
            users_by_id=self.users_by_id,
            suites_by_id=self.suites_by_id,
            schedules_by_id=self.schedules_by_id,
        )


async def load_actor_context(
    user_service: UserService,
    suite_summary_query: SuiteSummaryQueryPort,
    schedule_repo: ScheduleRepositoryPort,
) -> ActorContext:
    users_by_id = {
        user.user_id: (user.name, user.email) for user in await user_service.list_users()
    }
    suites_by_id = {row.suite_id: row for row in await suite_summary_query.list_summaries()}
    schedules_by_id = {schedule.schedule_id: schedule for schedule in await schedule_repo.list()}
    return ActorContext(
        users_by_id=users_by_id,
        suites_by_id=suites_by_id,
        schedules_by_id=schedules_by_id,
    )
