"""RunExecutionQueue(감독되는 작업 큐) 단위 테스트.

브라우저 없이 큐의 감독 동작(작업 실행·예외 격리·순서·정상 종료)을 검증한다.
pytest 비동기 플러그인 없이 동작하도록 각 테스트는 ``asyncio.run`` 으로 코루틴을 돌린다.
"""

from __future__ import annotations

import asyncio
import functools

import pytest

from app.execution.run_queue import RunExecutionQueue


def test_submit_before_start_raises():
    async def scenario():
        queue = RunExecutionQueue(worker_count=1)
        with pytest.raises(RuntimeError):
            await queue.submit(_noop, label="x")

    asyncio.run(scenario())


async def _noop() -> None:
    return None


def test_jobs_run_to_completion():
    async def scenario():
        queue = RunExecutionQueue(worker_count=2)
        queue.start()
        done: list[int] = []

        async def job(n: int) -> None:
            done.append(n)

        for i in range(5):
            await queue.submit(functools.partial(job, i), label=f"job-{i}")
        await queue._queue.join()  # 모든 작업 처리 대기
        await queue.stop()
        assert sorted(done) == [0, 1, 2, 3, 4]

    asyncio.run(scenario())


def test_job_exception_is_isolated():
    async def scenario():
        queue = RunExecutionQueue(worker_count=1)
        queue.start()
        ran: list[str] = []

        async def boom() -> None:
            raise RuntimeError("의도된 실패")

        async def ok() -> None:
            ran.append("ok")

        await queue.submit(boom, label="boom")
        await queue.submit(ok, label="ok")
        await queue._queue.join()
        await queue.stop()
        # 한 작업이 예외로 죽어도 워커는 살아 다음 작업을 처리해야 한다.
        assert ran == ["ok"]

    asyncio.run(scenario())


def test_single_worker_preserves_fifo_order():
    async def scenario():
        queue = RunExecutionQueue(worker_count=1)
        queue.start()
        order: list[int] = []

        async def job(n: int) -> None:
            await asyncio.sleep(0)
            order.append(n)

        for i in range(6):
            await queue.submit(functools.partial(job, i), label=f"job-{i}")
        await queue._queue.join()
        await queue.stop()
        assert order == [0, 1, 2, 3, 4, 5]

    asyncio.run(scenario())


def test_stop_cancels_workers():
    async def scenario():
        queue = RunExecutionQueue(worker_count=2)
        queue.start()
        assert all(not w.done() for w in queue._workers)
        await queue.stop()
        assert queue._workers == []
        # stop 후에는 다시 제출할 수 없다(시작되지 않은 상태).
        with pytest.raises(RuntimeError):
            await queue.submit(_noop, label="x")

    asyncio.run(scenario())
