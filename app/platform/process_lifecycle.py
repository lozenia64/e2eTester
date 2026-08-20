"""Cross-platform subprocess lifecycle helpers."""

from __future__ import annotations

import signal
import subprocess
import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint64)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


def create_child_job() -> int | None:
    """자식 프로세스 생명주기를 이 프로세스에 묶는 Windows Job Object 를 만든다.

    ``KILL_ON_JOB_CLOSE`` 를 걸어두면, 부모가 ``finally`` 를 못 타고 죽어도(터미널 강제
    종료, 강제 kill 등) OS 가 잡 핸들을 회수하는 순간 잡에 묶인 자식 전체(및 그 자식이
    낳은 손자 프로세스)를 함께 종료한다. ``CREATE_NEW_PROCESS_GROUP``(``popen_managed``)
    은 CTRL_BREAK 전달용일 뿐이라 부모 사망 시 자식이 좀비로 남는 문제를 못 막는다.
    non-Windows 에서는 ``None`` 을 반환하고 ``assign_to_job`` 은 그냥 아무것도 하지 않는다.
    """
    if sys.platform != "win32":
        return None
    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = _kernel32.SetInformationJobObject(
        job,
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if not ok:
        _kernel32.CloseHandle(job)
        return None
    return job


def assign_to_job(job: int | None, pid: int) -> None:
    """자식 프로세스를 ``job`` 에 편입시킨다(플랫폼이 다르거나 job 이 없으면 무시)."""
    if job is None or sys.platform != "win32":
        return
    handle = _kernel32.OpenProcess(_PROCESS_TERMINATE | _PROCESS_SET_QUOTA, False, pid)
    if not handle:
        return
    try:
        _kernel32.AssignProcessToJobObject(job, handle)
    finally:
        _kernel32.CloseHandle(handle)


def close_job(job: int | None) -> None:
    """``job`` 핸들을 명시적으로 닫는다 — 닫히는 순간 KILL_ON_JOB_CLOSE 로 묶인 자식이 즉시
    정리된다. 정상 종료 시엔 프로세스 exit 이 자동으로 해주므로 보통 호출할 필요 없고, 테스트
    나 명시적 조기 정리용."""
    if job is None or sys.platform != "win32":
        return
    _kernel32.CloseHandle(job)


def popen_managed(cmd: list[str], *, cwd: str, env: dict[str, str]) -> subprocess.Popen:
    """Start a child process with platform-appropriate process-group semantics."""
    if sys.platform == "win32":
        return subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(cmd, cwd=cwd, env=env, start_new_session=True)


def graceful_shutdown(proc: subprocess.Popen, *, timeout: float = 10) -> None:
    """Terminate a managed child process; escalate to kill on timeout."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except (AttributeError, OSError, ValueError):
            proc.terminate()
    else:
        proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout)
