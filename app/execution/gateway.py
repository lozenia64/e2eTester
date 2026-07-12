from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.system_models import ModuleDefinition
from app.runner.workflow_common import StepExecutionResult

# 단계 실행 도중 흘러나오는 로그 한 줄을 오케스트레이터로 되돌려 주는 비동기 콜백.
# 실행 스레드 ↔ 이벤트 루프 사이의 브리지는 게이트웨이 어댑터가 책임지므로,
# 오케스트레이터는 평범한 async 콜백만 넘기면 된다.
LogSink = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class ExecutionHandle:
    """오케스트레이터가 들고 다니는 **직렬화 가능한** 실행 세션 토큰.

    두 필드 모두 평범한 문자열이므로 메모리 참조(라이브 브라우저 런타임·스레드 풀 등)를
    전혀 담지 않는다. 실제 런타임은 게이트웨이가 ``session_id`` 로 자기 안에서만 보관하며,
    오케스트레이터는 이 토큰을 재개(start_index)·취소·종료 시 게이트웨이에 그대로 되돌려
    줄 뿐 내부를 들여다보지 않는다. 핸들이 값(value)이므로 OTP 일시정지 컨텍스트(영속 제어
    스토어)에 라이브 객체가 새지 않고, 장차 별도 프로세스/원격 워커 구현으로 토큰을 그대로 넘길 수 있다.
    """

    execution_mode: str
    # 게이트웨이 내부 세션 레지스트리의 키. 라이브 객체가 아니라 식별자(문자열)다.
    session_id: str


class ExecutionGateway(ABC):
    """오케스트레이션(상태머신)과 브라우저 실행(부작용) 사이의 포트.

    상태머신은 "무엇을, 어떤 순서로 실행할지"만 결정하고, 실제 브라우저 구동·스레드
    모델·런타임 수명·로그 브리지는 전적으로 이 포트 뒤로 숨긴다.

    수명 주기:
        ``open_session`` → (``run_step`` | ``submit_input``)* → ``close_session``

    한 Run 의 모든 단계는 같은 핸들(같은 브라우저 세션)을 공유하며, OTP 대기로 일시정지한
    뒤에도 같은 핸들로 재개한다. 현재 구현은 in-process(``LocalExecutionGateway``)지만,
    동일 포트로 별도 워커 프로세스/Playwright MCP 구현체로 교체할 수 있다.
    """

    @abstractmethod
    def supports(self, execution_mode: str) -> bool:
        """이 게이트웨이가 해당 실행 모드를 구동할 수 있는지."""

    @abstractmethod
    async def open_session(
        self,
        execution_mode: str,
        input_data: dict[str, str],
        run_id: str,
        module_id: str,
    ) -> ExecutionHandle:
        """브라우저 세션을 열고 핸들을 돌려준다. (실패 시 예외 전파)"""

    @abstractmethod
    async def run_step(
        self,
        handle: ExecutionHandle,
        run_id: str,
        module: ModuleDefinition,
        on_log: LogSink,
    ) -> StepExecutionResult:
        """단일 워크플로 단계를 실행하고 결과를 돌려준다."""

    @abstractmethod
    async def submit_input(self, handle: ExecutionHandle, value: str) -> None:
        """OTP 등 사용자 입력을 세션에 반영한다(체크포인트). 입력이 없는 시스템은 no-op."""

    @abstractmethod
    async def close_session(self, handle: ExecutionHandle) -> None:
        """세션을 정리한다. 이미 닫혔거나 비어 있으면 조용히 무시한다."""

    @abstractmethod
    async def resume_from_step(
        self,
        handle: ExecutionHandle,
        module_index: int,
        workflow_step: str,
    ) -> None:
        """부분 재실행 시 세션의 재개 지점을 기록한다(브라우저 상태는 세션에 유지)."""

    async def capture_storage_state(self, handle: ExecutionHandle) -> str | None:
        """세션의 Playwright ``storage_state``(쿠키+localStorage)를 직렬화해 돌려준다(Phase C).

        모듈 경계·OTP 일시정지 시 호출해 내구 체크포인트에 저장하면, 재기동/워커 교체 후 임의
        워커가 세션을 복원할 수 있다. 체크포인트를 지원하지 않는 어댑터는 기본 ``None`` 을
        돌려준다(추상 아님 — 기존 어댑터 무변경). 실제 캡처는 세션 스레드에서 수행해야 한다.
        """
        return None
