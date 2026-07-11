from __future__ import annotations

import asyncio

from app.execution.job_queue_port import Job, RunJobDescriptor

# E2E 도구는 헤디드 브라우저를 띄우므로 동시 실행을 무한정 허용하면 자원이 폭증한다.
DEFAULT_RUN_CONCURRENCY = 4


class InMemoryJobQueue:
    """프로세스-로컬 asyncio 큐 백엔드(테스트·로컬 개발용).

    ``RunExecutionQueue`` 가 워커 풀과 함께 이 백엔드를 소비한다.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[Job, str] | RunJobDescriptor] = asyncio.Queue()
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def pending_jobs(self) -> int:
        return self._queue.qsize()

    def mark_started(self) -> None:
        self._started = True

    async def submit(self, job: Job, *, label: str) -> None:
        if not self._started:
            raise RuntimeError("InMemoryJobQueue 가 시작되지 않았습니다.")
        await self._queue.put((job, label))

    async def enqueue_run_job(self, descriptor: RunJobDescriptor) -> None:
        if not self._started:
            raise RuntimeError("InMemoryJobQueue 가 시작되지 않았습니다.")
        await self._queue.put(descriptor)

    async def get(self) -> tuple[Job, str] | RunJobDescriptor:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()
