from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.core.models import ModuleDefinition
from app.runner.workflow_common import StepExecutionResult

# 단계 실행 도중 흘러나오는 로그 한 줄을 오케스트레이터로 되돌려 주는 비동기 콜백.
# 실행 스레드 ↔ 이벤트 루프 사이의 브리지는 게이트웨이 어댑터가 책임지므로,
# 오케스트레이터는 평범한 async 콜백만 넘기면 된다.
LogSink = Callable[[str], Awaitable[None]]


@dataclass
class ExecutionHandle:
    """오케스트레이터가 들고 다니는 불투명한 실행 세션 핸들.

    내부 구현(브라우저 런타임, 스레드 풀, 원격 워커 식별자 등)은 게이트웨이만 안다.
    오케스트레이터는 이 핸들을 재개(start_index)·취소·종료 시 게이트웨이에 그대로
    되돌려 줄 뿐, ``execution_mode`` 외의 내부 필드에 접근하지 않는다.
    """

    execution_mode: str
    # 어댑터 전용 내부 상태. 오케스트레이터는 절대 들여다보지 않는다.
    runtime: Any = None
    internal: dict[str, Any] = field(default_factory=dict)


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
