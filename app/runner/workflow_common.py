from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.core.enums import ModuleStatus


@dataclass(frozen=True)
class StepExecutionResult:
    status: ModuleStatus
    message: str
    artifacts: list[str]
    current_url: str | None
    dialog_messages: list[str]
    last_error: str | None = None
    screenshot_path: Path | None = None

    @classmethod
    def failure(
        cls,
        message: str,
        current_url: str | None,
        dialog_messages: list[str],
        last_error: str | None,
        screenshot_path: Path | None = None,
    ) -> "StepExecutionResult":
        return cls(
            status=ModuleStatus.FAILED,
            message=message,
            artifacts=[],
            current_url=current_url,
            dialog_messages=dialog_messages,
            last_error=last_error,
            screenshot_path=screenshot_path,
        )


class LineWriter(io.TextIOBase):
    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            stripped = line.rstrip()
            if stripped:
                self._emit(stripped)
        return len(text)

    def flush(self) -> None:
        if self._buffer.strip():
            self._emit(self._buffer.strip())
        self._buffer = ""


def write_log_line(line: str, emit_log: Callable[[str], None], log_file) -> None:
    stripped = line.rstrip()
    if not stripped:
        return
    log_file.write(stripped + "\n")
    log_file.flush()
    emit_log(stripped)
