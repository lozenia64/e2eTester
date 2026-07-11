"""저장소 포트(Protocol) 정의.

오케스트레이터·스케줄러는 구체 저장소(InMemory/SQLite)가 아니라 이 포트에만 의존한다.
``ExecutionGateway`` 가 브라우저 실행을 포트로 분리한 것과 같은 방식으로, 저장소도
포트 뒤로 두어 인메모리 ↔ 영속(SQLite) 어댑터를 무수정으로 교체할 수 있게 한다.

구현체는 모두 ``get_*`` 류에서 없는 키에 ``KeyError`` 를 던져야 한다(API 계층이 404 로 변환).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.core.models import (
    AnomalyHandling,
    AuthPreset,
    PendingExecution,
    Run,
    Schedule,
    SuiteRun,
)
from app.domain.events import DomainEvent
from app.healing.models import HealingEvent, HealingPatch, HealingPolicy
from app.realtime.ports import RealtimeNotificationPort
from app.storage.query_rows import (
    AnomalyInboxRow,
    DailyRunSummaryRow,
    DailyStatusRow,
    ModuleHistoryRow,
    Page,
    RunSummaryFilter,
    RunSummaryRow,
    StatsRollupRow,
    SuiteSummaryRow,
)


class RunWriteRepositoryPort(Protocol):
    """Run 상태(state) 집합체의 **쓰기** 영속 경계.

    create/save/get/delete 만 담당한다. 이력 조회·WebSocket fan-out 은 각각
    ``RunHistoryQueryPort``·``RealtimeNotificationPort`` 가 소유한다.
    """

    async def create_run(self, run: Run, *, events: list[DomainEvent] | None = None) -> Run: ...
    async def save_run(self, run: Run, *, events: list[DomainEvent] | None = None) -> Run: ...
    async def get_run(self, run_id: str) -> Run: ...
    async def append_events(self, events: list[DomainEvent]) -> None: ...
    async def delete_run(self, run_id: str) -> None: ...


class RunHistoryQueryPort(Protocol):
    """Run 이력 조회 포트 (**deprecated** — WP-A4 에서 소비처 전환 후 삭제).

    ``list[Run]`` 을 반환하는 blob 재수화 경로다. 신규 코드는 ``RunSummaryQueryPort``/
    ``ModuleHistoryQueryPort`` 를 사용한다.
    """

    async def list_all_runs(self) -> list[Run]: ...
    async def get_run(self, run_id: str) -> Run: ...
    async def list_runs_by_user(self, user_id: str) -> list[Run]: ...
    async def list_runs_by_system(self, system_code: str) -> list[Run]: ...
    async def list_runs_by_schedule(self, schedule_id: str, limit: int = 30) -> list[Run]: ...
    async def list_schedule_tagged_runs(self) -> list[Run]: ...
    async def list_runs_since(self, since: datetime) -> list[Run]: ...
    async def list_runs_with_statuses(self, statuses: frozenset) -> list[Run]: ...
    async def list_waiting_input_runs(self) -> list[Run]: ...
    async def last_finished_at_by_system(self) -> dict[str, datetime]: ...
    async def find_previous_finished_run(self, run: Run) -> Run | None: ...


class RunSummaryQueryPort(Protocol):
    """Run 요약 목록 **읽기** 쿼리 경계 — ``run_history_index`` 프로젝션 전용.

    화면 모양(screen-shaped) 행만 반환한다. 도메인 엔티티(``Run``)는 반환하지 않는다 —
    필터·정렬·페이지는 전부 SQL 로 수행되고(단일 SELECT), blob 재수화는 타입 수준에서
    불가능하다. 단건 애그리거트 로드가 필요한 상세/쓰기 경로는 ``RunWriteRepositoryPort``
    를 쓴다.
    """

    async def list_summaries(self, query: RunSummaryFilter, page: Page) -> list[RunSummaryRow]: ...
    async def count(self, query: RunSummaryFilter) -> int: ...
    async def counts_by_status(self) -> dict[str, int]: ...
    async def list_run_ids(self, query: RunSummaryFilter) -> list[str]: ...
    async def last_finished_at_by_system(self) -> dict[str, datetime]: ...
    async def find_previous_finished_run_id(
        self, system_code: str, before: datetime, exclude_run_id: str
    ) -> str | None: ...


class ModuleHistoryQueryPort(Protocol):
    """모듈 실행 이력 **읽기** 쿼리 경계 — ``module_history_index`` 프로젝션 전용.

    인사이트(헬스/타임라인/딥다이브)·사용량 통계·일간 소요시간이 소비한다.
    """

    async def list_for_system(
        self, system_code: str, *, limit: int | None = None
    ) -> list[ModuleHistoryRow]: ...
    async def list_for_runs(self, run_ids: list[str]) -> list[ModuleHistoryRow]: ...
    async def list_between(
        self, since: datetime | None, until: datetime | None
    ) -> list[ModuleHistoryRow]: ...


class SuiteSummaryQueryPort(Protocol):
    """Suite 요약 목록 **읽기** 쿼리 경계 — ``suite_history_index`` 프로젝션 전용."""

    async def list_summaries(self, *, limit: int | None = None) -> list[SuiteSummaryRow]: ...
    async def counts_by_status(self) -> dict[str, int]: ...


class RunRepositoryPort(
    RunWriteRepositoryPort, RunHistoryQueryPort, RealtimeNotificationPort, Protocol
):
    """Run 저장소 **복합 포트**(하위 호환 · **deprecated**).

    쓰기(``RunWriteRepositoryPort``)·이력 조회(``RunHistoryQueryPort``)·실시간 알림
    (``RealtimeNotificationPort``)를 한 타입으로 묶는다.

    .. deprecated::
        프로덕션 코드는 ``RunWriteRepositoryPort`` + ``RunHistoryQueryPort`` +
        ``RealtimeNotificationPort`` 를 각각 주입받는다. 이 복합 포트는 기존 테스트·
        ``CompositeRunRepository`` 하위 호환용으로만 유지한다.
    """


class RunLogStorePort(Protocol):
    """모듈 실행 로그(append-only 스트림)의 저장 경계.

    Run 상태 집합체와 분리된 별도 집합체다. 로그는 한 줄씩 추가되는 고빈도 텔레메트리이므로,
    Run blob 을 통째로 다시 쓰지 않고 ``(run_id, module_id)`` 키의 append-only 스토어에
    한 줄당 한 번 INSERT 한다(핫패스 쓰기량을 O(N²)→O(N) 으로 낮춘다). 읽기 시
    ``RunService`` 가 이 스토어에서 로그를 읽어 Run 읽기 모델에 하이드레이션한다.
    """

    async def append(self, run_id: str, module_id: str, line: str) -> None: ...
    async def get(self, run_id: str, module_id: str) -> list[str]: ...
    async def get_all(self, run_id: str) -> dict[str, list[str]]: ...
    async def delete_by_run_id(self, run_id: str) -> None: ...


class RunControlStorePort(Protocol):
    """Run 의 **비공개 제어 상태**(클라이언트에 직렬화되지 않음) 저장 경계.

    Run blob 은 ``model_dump`` 로 모든 WebSocket 리스너에 그대로 방송되므로(``RunEventPublisher``),
    취소 의도·재개 컨텍스트(세션 토큰·resume index) 같은 내부 제어 상태는 Run blob 이 아니라 이
    형제 스토어가 소유한다 — 모듈 로그를 ``RunLogStorePort`` 로 분리한 것과 같은 이유다. 이로써
    ``RunService`` 의 서비스-인스턴스 메모리 dict(``_pending_otp``/``_cancel_requested``)가 사라지고
    제어 상태가 권위 있는 단일 출처로 영속된다.

    취소 플래그와 pending(재개) 컬럼은 **서로 다른 컬럼**이라, 실행 중 취소(컬럼 A 갱신)와
    OTP 일시정지 기록(컬럼 B 갱신)이 같은 행을 통째로 덮어써 lost-update 를 내지 않는다.
    구현체는 ``get_pending`` 에서 대기 중이 아니면 ``None`` 을 돌려준다.
    """

    async def set_cancel_requested(self, run_id: str) -> None: ...
    async def is_cancel_requested(self, run_id: str) -> bool: ...
    async def set_pending(
        self,
        run_id: str,
        session_id: str,
        execution_mode: str,
        resume_index: int,
        module_id: str,
    ) -> None: ...
    async def get_pending(self, run_id: str) -> PendingExecution | None: ...
    async def clear_pending(self, run_id: str) -> None: ...
    async def delete(self, run_id: str) -> None: ...


class RunInputStorePort(Protocol):
    """Run 의 해석된 입력값(이름·전화 등 **PII**) 저장 경계.

    PII 이므로 Run blob/이벤트 payload 에 절대 직렬화하지 않는다(``RunService`` 가 이 포트로만
    보관·조회). 기본 어댑터는 인메모리(오늘의 ``_run_inputs`` dict 와 동일한 휘발성)이며, 암호화
    SQLite 어댑터를 끼우면 재기동 후 rerun 까지 가능해진다(Phase 2). rerun 과 OTP 재개가 이
    입력값을 읽는다. 일시적인 OTP 코드는 담지 않는다(게이트웨이가 런타임에 직접 주입).
    """

    async def put(self, run_id: str, input_data: dict[str, str]) -> None: ...
    async def get(self, run_id: str) -> dict[str, str] | None: ...
    async def delete(self, run_id: str) -> None: ...


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


class ScheduleRepositoryPort(Protocol):
    async def save(self, schedule: Schedule) -> Schedule: ...
    async def get(self, schedule_id: str) -> Schedule: ...
    async def list(self) -> list[Schedule]: ...
    async def delete(self, schedule_id: str) -> None: ...


class AnomalyHandlingStorePort(Protocol):
    """이상징후 인박스 **처리 레코드**(``AnomalyHandling``)의 저장 경계.

    ANOMALY/ERROR 로 끝난 모듈(이상건)마다 처리상태·담당자·메모를 모듈-Run 단위로 보관한다.
    이상건 자체는 Run 스캔으로 매번 새로 도출하고, 이 스토어는 그 위에 얹히는 '조치' 메타데이터만
    소유한다(행이 없으면 기본 ``UNRESOLVED``). ``module_run_id`` = ``f"{run_id}::{module_id}"``.
    """

    async def get(self, module_run_id: str) -> AnomalyHandling | None: ...
    async def list(self) -> list[AnomalyHandling]: ...
    async def upsert(self, handling: AnomalyHandling) -> AnomalyHandling: ...


class AnomalyInboxQueryPort(Protocol):
    """이상징후 인박스 **읽기** 쿼리 — ``anomaly_inbox_index`` 프로젝션."""

    async def list_page(
        self,
        allowed_system_codes: list[str] | None,
        *,
        limit: int = 500,
        offset: int = 0,
    ) -> list[AnomalyInboxRow]: ...


class DailyStatusQueryPort(Protocol):
    """일간 점검 현황 **읽기** 쿼리 — ``daily_system_status`` + 당일 Run 요약."""

    async def list_for_date(
        self,
        date_label: str,
        allowed_system_codes: list[str] | None,
    ) -> list[DailyStatusRow]: ...

    async def list_run_summaries_for_date(
        self,
        date_label: str,
        since_utc: datetime,
        allowed_system_codes: list[str] | None,
    ) -> list[DailyRunSummaryRow]: ...


class StatsQueryPort(Protocol):
    """사용량 통계 **읽기** 쿼리 — ``stats_rollup`` + 이력 인덱스 기반 Run 조립."""

    async def rollup_between(
        self,
        from_day: str | None,
        to_day: str | None,
        *,
        system_codes: list[str] | None = None,
    ) -> list[StatsRollupRow]: ...

    async def list_usage_runs(
        self,
        from_dt: datetime | None,
        to_dt: datetime | None,
    ) -> list[Run]: ...


class HealingEventStorePort(Protocol):
    """자가 치유 이벤트(감사 로그)의 저장 경계 — append-only.

    무인 실행 중 셀렉터가 깨졌을 때의 치유 시도 1건(무엇이 깨졌나/어떻게 복구했나/신뢰도)을
    기록한다. 이벤트는 수정되지 않고 쌓이기만 하며, 만성(chronic) 판정·MTTR·복구율 집계의
    입력이 된다.
    """

    async def append(self, event: HealingEvent) -> HealingEvent: ...
    async def list(self, limit: int | None = None) -> list[HealingEvent]: ...


class HealingPolicyStorePort(Protocol):
    """자동 복구 정책(시스템별 auto-heal on/off + 신뢰도 임계치)의 저장 경계.

    ``system_code="*"`` 행이 전역 기본값이다. 실행 스레드는 이 포트가 아니라 같은 테이블을
    읽는 동기 리더(``SqliteHealingPolicyReader``)로 정책 스냅샷을 조회한다(스레드 경계 분리).
    """

    async def list(self) -> list[HealingPolicy]: ...
    async def upsert(self, policy: HealingPolicy) -> HealingPolicy: ...


class HealingPatchStorePort(Protocol):
    """셀렉터 오토픽스 패치(승인 대기 diff 제안)의 저장 경계.

    치유된 셀렉터를 실제 steps 소스에 반영하는 제안(PROPOSED)과 그 승인/거절 감사 이력
    (누가 언제 어떤 셀렉터를 바꿨나)을 보관한다. 소스 파일 적용 자체는 ``HealingService``
    가 승인 시점에 수행한다.
    """

    async def add(self, patch: HealingPatch) -> HealingPatch: ...
    async def get(self, patch_id: str) -> HealingPatch: ...
    async def list(self) -> list[HealingPatch]: ...
    async def update(self, patch: HealingPatch) -> HealingPatch: ...


class PresetRepositoryPort(Protocol):
    """사용자별 인증 프리셋(``AuthPreset``)의 저장 경계.

    프리셋은 인증 정보(PII 포함 가능)를 **의도적으로** 영속한다 — 그것이 기능의 목적이다.
    소유권 강제(사용자별 격리)는 상위 서비스/라우트가 책임지며, 저장소는 CRUD 만 담당한다.
    """

    async def save(self, preset: AuthPreset) -> AuthPreset: ...
    async def get(self, preset_id: str) -> AuthPreset: ...
    async def list_by_user(self, user_id: str) -> list[AuthPreset]: ...
    async def delete(self, preset_id: str) -> None: ...
