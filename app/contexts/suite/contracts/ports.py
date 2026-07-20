"""저장소 포트(Protocol) 정의 — Suite 컨텍스트."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.contexts.suite.contracts.query_rows import SuiteSummaryRow
from app.core.enums import SuiteStatus
from app.core.suite_models import SuiteRun
from app.domain.events import DomainEvent


class SuiteSummaryQueryPort(Protocol):
    """Suite 요약 목록 **읽기** 쿼리 경계 — ``suite_history_index`` 프로젝션 전용."""

    async def list_summaries(
        self,
        *,
        limit: int | None = None,
        requested_before: datetime | None = None,
        requested_since: datetime | None = None,
        statuses: frozenset[SuiteStatus] | None = None,
    ) -> list[SuiteSummaryRow]: ...
    async def counts_by_status(self) -> dict[str, int]: ...


class SuiteControlStorePort(Protocol):
    """Suite 의 **비공개 제어 상태**(취소 의도) 저장 경계.

    ``RunControlStorePort`` 와 같은 이유로, Suite 취소 의도를 더 이상 서비스-인스턴스 메모리
    set(``_cancel_requested``)에 두지 않고 권위 있는 단일 출처로 영속한다. Suite blob 은 WebSocket
    리스너로 그대로 방송되므로 제어 상태는 형제 스토어가 소유한다. 이벤트 기반 Saga 가 다음
    스텝으로 진행하기 전에 이 플래그를 (스토어에서 최신값으로) 읽어 협력적으로 중단한다.
    """

    async def set_cancel_requested(self, suite_id: str) -> None: ...
    async def is_cancel_requested(self, suite_id: str) -> bool: ...
    async def delete(self, suite_id: str) -> None: ...


class SuiteInputStorePort(Protocol):
    """Suite 의 시스템별 실행 입력값(``{system_code: {field: value}}``) 저장 경계.

    이벤트 기반 Saga 는 각 스텝의 Run 을 시작할 때 시스템별 입력값이 필요하다(과거에는
    ``_execute_suite`` 의 루프 클로저에만 들고 있었다). PII 가 섞일 수 있어 Suite blob/이벤트
    payload 로 직렬화하지 않고 이 전용 스토어에만 둔다(``RunInputStorePort`` 와 동일 패턴, 기본
    인메모리 휘발성).
    """

    async def put(self, suite_id: str, systems_input: dict[str, dict[str, str]]) -> None: ...
    async def get(self, suite_id: str) -> dict[str, dict[str, str]] | None: ...
    async def delete(self, suite_id: str) -> None: ...


class SuiteWriteRepositoryPort(Protocol):
    """Suite 상태 집합체의 **쓰기** 영속 경계."""

    async def create_suite(
        self, suite: SuiteRun, *, events: list[DomainEvent] | None = None
    ) -> SuiteRun: ...
    async def save_suite(
        self, suite: SuiteRun, *, events: list[DomainEvent] | None = None
    ) -> SuiteRun: ...
    async def get_suite(self, suite_id: str) -> SuiteRun: ...
    async def append_events(self, events: list[DomainEvent]) -> None: ...


class SuiteReadRepositoryPort(Protocol):
    """Suite **읽기** 경계(list/get)."""

    async def get_suite(self, suite_id: str) -> SuiteRun: ...
    async def list_suites(self) -> list[SuiteRun]: ...
    async def list_suites_by_user(self, user_id: str) -> list[SuiteRun]: ...


class SuiteRepositoryPort(SuiteReadRepositoryPort, Protocol):
    """Suite 저장소 **복합 포트**(하위 호환 · read-only)."""
