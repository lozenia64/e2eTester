"""실행 경계 결과 계약 — ``ExecutionGateway`` 가 돌려주는 스텝 실행 결과 DTO.

과거 이 타입은 ``app/runner/workflow_common.py`` 에 있어 실행 게이트웨이(``app/execution/``)가
실행 평면(runner)을 import 해야 했다. 실행 평면 분리(Phase C, WP-C4)를 위해 결과 계약을
게이트웨이 곁으로 옮겨, 오케스트레이션·게이트웨이가 runner 를 import 하지 않게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.enums import FailureSignal, ModuleStatus

if TYPE_CHECKING:
    from app.contexts.healing.models import HealingAttempt


@dataclass(frozen=True)
class StepExecutionResult:
    status: ModuleStatus
    message: str
    artifacts: list[str]
    current_url: str | None
    dialog_messages: list[str]
    last_error: str | None = None
    screenshot_path: Path | None = None
    # 복구 등급 결정의 유일한 입력(설계 §3.1). 기본값이 있으므로 기존 호출부는 무수정 동작한다.
    failure_signal: FailureSignal = FailureSignal.UNKNOWN
    # 자가 치유 시도 '사실' 보고(어댑터는 보고만, 영속·패치 제안은 오케스트레이터가 수행).
    healing_events: list[HealingAttempt] = field(default_factory=list)

    @classmethod
    def failure(
        cls,
        message: str,
        current_url: str | None,
        dialog_messages: list[str],
        last_error: str | None,
        screenshot_path: Path | None = None,
    ) -> StepExecutionResult:
        return cls(
            status=ModuleStatus.ANOMALY,
            message=message,
            artifacts=[],
            current_url=current_url,
            dialog_messages=dialog_messages,
            last_error=last_error,
            screenshot_path=screenshot_path,
            failure_signal=FailureSignal.SITE,
        )
