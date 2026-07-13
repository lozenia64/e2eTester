"""Tests for WorkerExecutionGateway remote error formatting."""

from __future__ import annotations

from app.execution.worker_gateway import _format_remote_error


def test_format_remote_error_detects_redis_connection_refused_on_custom_port() -> None:
    detail = '{"detail":"Error 111 connecting to 127.0.0.1:6380. Connection refused."}'
    message = _format_remote_error(500, detail)
    assert "Redis" in message
    assert "인프라 오류" in message


def test_format_remote_error_leaves_unrelated_errors_unchanged() -> None:
    detail = '{"detail":"module step timeout"}'
    assert _format_remote_error(500, detail) == f"원격 실행 오류 500: {detail}"
