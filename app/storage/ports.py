"""저장소 포트(Protocol) 정의.

오케스트레이터·스케줄러는 구체 저장소(InMemory/SQLite)가 아니라 이 포트에만 의존한다.
``ExecutionGateway`` 가 브라우저 실행을 포트로 분리한 것과 같은 방식으로, 저장소도
포트 뒤로 두어 인메모리 ↔ 영속(SQLite) 어댑터를 무수정으로 교체할 수 있게 한다.

구현체는 모두 ``get_*`` 류에서 없는 키에 ``KeyError`` 를 던져야 한다(API 계층이 404 로 변환).
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from app.core.models import DashboardEvent, PendingExecution, Run, Schedule, SuiteEvent, SuiteRun


class RunRepositoryPort(Protocol):
    """Run 상태(state) 집합체의 영속 경계.

    이 포트는 Run 의 권위 있는 상태(status·모듈 전이·comparison 등)만 책임진다.
    **모듈 로그는 이 집합체에 속하지 않는다** — 고빈도 append-only 텔레메트리라
    별도 ``RunLogStorePort`` 가 소유하며, 영속 Run blob 에는 로그가 담기지 않는다(구현체의
    ``save_run`` 이 방어적으로 strip 한다). 로그를 붙인 읽기 모델 조립은 ``RunService.get_run``
    의 책임이다.
    """

    async def create_run(self, run: Run) -> Run: ...
    async def save_run(self, run: Run) -> Run: ...
    async def get_run(self, run_id: str) -> Run: ...
    async def list_runs(self) -> list[Run]: ...
    async def list_runs_by_user(self, user_id: str) -> list[Run]: ...
    async def delete_run(self, run_id: str) -> None: ...
    async def publish(self, event: DashboardEvent) -> None: ...
    async def subscribe(self, run_id: str) -> asyncio.Queue[DashboardEvent]: ...
    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[DashboardEvent]) -> None: ...


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


class SuiteRepositoryPort(Protocol):
    async def create_suite(self, suite: SuiteRun) -> SuiteRun: ...
    async def save_suite(self, suite: SuiteRun) -> SuiteRun: ...
    async def get_suite(self, suite_id: str) -> SuiteRun: ...
    async def list_suites(self) -> list[SuiteRun]: ...
    async def list_suites_by_user(self, user_id: str) -> list[SuiteRun]: ...
    async def publish(self, event: SuiteEvent) -> None: ...
    async def subscribe(self, suite_id: str) -> asyncio.Queue[SuiteEvent]: ...
    async def unsubscribe(self, suite_id: str, queue: asyncio.Queue[SuiteEvent]) -> None: ...


class ScheduleRepositoryPort(Protocol):
    async def save(self, schedule: Schedule) -> Schedule: ...
    async def get(self, schedule_id: str) -> Schedule: ...
    async def list(self) -> list[Schedule]: ...
    async def delete(self, schedule_id: str) -> None: ...
