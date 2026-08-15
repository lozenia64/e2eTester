"""SDD Spec ↔ pytest 추적성 (conftest)."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "spec(spec_id, ac_id): SDD Spec 수용 기준과 테스트 연결 (예: SPEC-RUN-001, AC-002)",
    )
