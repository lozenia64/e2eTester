"""CI 설정 자체의 정합성 검사 (유령 경로 재발 차단)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import gates
from scripts.ci.gates import validate_ci_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_current_ci_config_has_no_problems():
    assert validate_ci_config(REPO_ROOT) == []


def test_ghost_security_path_is_detected(monkeypatch: pytest.MonkeyPatch):
    """2026-08-17 회귀: app/storage/ 는 이사 갔는데 CI 가 계속 참조하고 있었다."""
    monkeypatch.setattr(gates, "SECURITY_PATHS", ["app/storage/input_crypto.py"])
    problems = validate_ci_config(REPO_ROOT)
    assert any("app/storage/input_crypto.py" in p for p in problems)


def test_ghost_gate_command_path_is_detected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        gates,
        "GATE_COMMANDS",
        {"bogus": ["python3", "scripts/does_not_exist.py"]},
    )
    problems = validate_ci_config(REPO_ROOT)
    assert any("scripts/does_not_exist.py" in p for p in problems)


def test_profile_referencing_unknown_gate_is_detected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gates, "PROFILE_GATES", {"full": ["no_such_gate"]})
    problems = validate_ci_config(REPO_ROOT)
    assert any("no_such_gate" in p for p in problems)


def test_gate_without_tier_is_detected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gates, "GATE_COMMANDS", {"tierless": ["python3", "--version"]})
    monkeypatch.setattr(gates, "GATE_TIERS", {})
    problems = validate_ci_config(REPO_ROOT)
    assert any("tierless" in p for p in problems)
