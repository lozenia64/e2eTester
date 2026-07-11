"""RunExecutionQueue(감독되는 작업 큐) 단위 테스트.

브라우저 없이 큐의 감독 동작(작업 실행·예외 격리·순서·정상 종료)을 검증한다.
async def 테스트는 pytest-asyncio(asyncio_mode="auto")가 코루틴으로 실행한다.
"""

from __future__ import annotations

import asyncio
import functools

import pytest

from app.execution.run_queue import RunExecutionQueue


async def _noop() -> None:
    return None


async def test_submit_before_start_raises():
    queue = RunExecutionQueue(worker_count=1)
    with pytest.raises(RuntimeError):
        await queue.submit(_noop, label="x")


async def test_jobs_run_to_completion():
    queue = RunExecutionQueue(worker_count=2)
    queue.start()
    done: list[int] = []

    async def job(n: int) -> None:
        done.append(n)

    for i in range(5):
        await queue.submit(functools.partial(job, i), label=f"job-{i}")
    await queue.join()
    await queue.stop()
    assert sorted(done) == [0, 1, 2, 3, 4]


async def test_job_exception_is_isolated():
    queue = RunExecutionQueue(worker_count=1)
    queue.start()
    ran: list[str] = []

    async def boom() -> None:
        raise RuntimeError("의도된 실패")

    async def ok() -> None:
        ran.append("ok")

    await queue.submit(boom, label="boom")
    await queue.submit(ok, label="ok")
    await queue.join()
    await queue.stop()
    # 한 작업이 예외로 죽어도 워커는 살아 다음 작업을 처리해야 한다.
    assert ran == ["ok"]


async def test_single_worker_preserves_fifo_order():
    queue = RunExecutionQueue(worker_count=1)
    queue.start()
    order: list[int] = []

    async def job(n: int) -> None:
        await asyncio.sleep(0)
        order.append(n)

    for i in range(6):
        await queue.submit(functools.partial(job, i), label=f"job-{i}")
    await queue.join()
    await queue.stop()
    assert order == [0, 1, 2, 3, 4, 5]


async def test_stop_cancels_workers():
    queue = RunExecutionQueue(worker_count=2)
    queue.start()
    assert all(not w.done() for w in queue._workers)
    await queue.stop()
    assert queue._workers == []
    # stop 후에는 다시 제출할 수 없다(시작되지 않은 상태).
    with pytest.raises(RuntimeError):
        await queue.submit(_noop, label="x")
