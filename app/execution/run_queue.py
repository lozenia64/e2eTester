from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Protocol

# 큐에 적재되는 작업: 인자 없이 코루틴을 돌려주는 팩토리(보통 ``functools.partial``).
Job = Callable[[], Awaitable[None]]

# E2E 도구는 헤디드 브라우저를 띄우므로 동시 실행을 무한정 허용하면 자원이 폭증한다.
# 기본 동시성은 보수적으로 두고 컴포지션 루트에서 env(E2E_RUN_CONCURRENCY)로 조정한다.
DEFAULT_RUN_CONCURRENCY = 4


class JobQueue(Protocol):
    """Run 실행 작업을 제출하는 포트. 오케스트레이터는 구체 큐 구현을 모른다."""

    async def submit(self, job: Job, *, label: str) -> None: ...


class RunExecutionQueue:
    """Run 실행을 위한 **감독되는(in-process) 작업 큐**.

    기존에는 ``RunService.start_run`` 이 ``asyncio.create_task`` 로 실행 코루틴을 발사 후
    망각(fire-and-forget)해, 추적·동시성 제한·예외 가시화·정상 종료가 전혀 없었다. 이 큐는
    그 자리를 대신한다:

    - **감독**: 워커 태스크가 큐에서 작업을 꺼내 실행하고, 작업에서 난 예외를 격리·로깅한다
      (고아 태스크/조용히 사라지는 예외 제거).
    - **동시성 제한**: 워커 수만큼만 동시에 실행한다(자원 폭증 방지). OTP 대기로 일시정지한
      Run 은 실행 코루틴이 반환되어 워커를 즉시 반납하고, 재개는 새 작업으로 다시 제출된다
      (대기 중에 워커를 점유하지 않음).
    - **수명 관리**: 컴포지션 루트(lifespan)가 ``start``/``stop`` 으로 워커를 띄우고 거둔다.

    큐 자체는 프로세스-로컬(in-process)이다. 같은 포트(``JobQueue``)로 외부 브로커 기반
    워커 구현을 끼워 out-of-process 실행으로 확장할 수 있다(워커 경계).
    """

    def __init__(self, worker_count: int = DEFAULT_RUN_CONCURRENCY) -> None:
        self._worker_count = max(1, worker_count)
        self._queue: asyncio.Queue[tuple[Job, str]] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._started = False

    @property
    def worker_count(self) -> int:
        return self._worker_count

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"run-queue-worker-{index}")
            for index in range(self._worker_count)
        ]

    async def submit(self, job: Job, *, label: str) -> None:
        if not self._started:
            raise RuntimeError("RunExecutionQueue 가 시작되지 않았습니다.")
        await self._queue.put((job, label))

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._started = False

    async def _worker(self, index: int) -> None:
        while True:
            job, label = await self._queue.get()
            try:
                await job()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # 작업 예외는 다른 작업/워커로 전파되지 않게 격리
                print(f"[run-queue] worker={index} job={label} 실행 오류: {exc}")
            finally:
                self._queue.task_done()
