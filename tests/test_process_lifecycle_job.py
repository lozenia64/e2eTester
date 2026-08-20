"""Windows Job Object 기반 자식 프로세스 정리 검증.

부모(run_local.py)가 finally 를 못 타고 죽어도(터미널 강제종료 등) OS 가 잡 핸들 회수 시점에
잡에 묶인 자식을 함께 종료하는지 확인한다 — ``close_job`` 으로 그 상황을 흉내낸다.
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from app.platform.process_lifecycle import assign_to_job, close_job, create_child_job

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Job Object 는 Windows 전용")


def test_closing_job_kills_assigned_child() -> None:
    job = create_child_job()
    assert job is not None

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assign_to_job(job, proc.pid)
        close_job(job)  # 부모가 finally 없이 죽는 상황을 흉내낸다.

        for _ in range(50):
            if proc.poll() is not None:
                break
            time.sleep(0.1)

        assert proc.poll() is not None, "job 핸들을 닫으면 잡에 묶인 자식이 즉시 종료돼야 한다"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_no_job_is_a_noop() -> None:
    """job 이 None 이면(비-Windows 경로 포함) assign/close 는 조용히 아무것도 안 한다."""
    assign_to_job(None, 1)
    close_job(None)
