from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

# 큐에 적재되는 작업: 인자 없이 코루틴을 돌려주는 팩토리(보통 ``functools.partial``).
Job = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class RunJobDescriptor:
    """Run 실행 작업의 직렬화 가능한 설명자(원격 워커·Redis 브로커용).

    코루틴 팩토리는 프로세스 경계를 넘길 수 없으므로, ``run_id`` 와 작업 종류만
    브로커에 실어 보내고 소비 측(워커)이 공유 DB·제어 스토어에서 나머지를 복원한다.
    """

    run_id: str
    kind: Literal["execute", "resume"]
    start_index: int = 0
    label: str = ""


class JobQueuePort(Protocol):
    """Run 실행 작업을 제출하는 포트. 오케스트레이터는 구체 큐 구현을 모른다."""

    async def submit(self, job: Job, *, label: str) -> None: ...

    async def enqueue_run_job(self, descriptor: RunJobDescriptor) -> None: ...
