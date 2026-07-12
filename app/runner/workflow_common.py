from __future__ import annotations

from collections.abc import Callable

# 결과 계약은 실행 경계(app/execution/results.py)로 이관됐다(WP-C4). 기존 임포터 호환을 위해
# 재노출한다 — runner 내부 코드는 계속 여기서 가져올 수 있다(단, execution/오케스트레이션은
# 직접 app.execution.results 를 쓴다).
from app.execution.results import StepExecutionResult

__all__ = ["StepExecutionResult", "write_log_line"]


def write_log_line(line: str, emit_log: Callable[[str], None], log_file) -> None:
    stripped = line.rstrip()
    if not stripped:
        return
    log_file.write(stripped + "\n")
    log_file.flush()
    emit_log(stripped)
