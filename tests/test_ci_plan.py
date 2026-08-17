"""CI 게이트 러너·플래너 계약."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_gates_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/ci/run_all_gates.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def test_single_gate_mode_runs_one_gate():
    proc = _run_gates_cli("--gate", "ci_config_valid")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert '"gate_count": 1' in proc.stdout


def test_unknown_gate_name_is_rejected():
    proc = _run_gates_cli("--gate", "no_such_gate")
    assert proc.returncode == 1
    assert "no_such_gate" in proc.stdout


from scripts.ci.gates import SECURITY_PATHS  # noqa: E402
from scripts.ci.plan import matches_any, resolve_ci_gates  # noqa: E402


def test_docs_only_change_runs_minimal_gates():
    gates = resolve_ci_gates(["docs/CI.md", "README.md"], event_name="pull_request")
    assert gates == ["ci_config_valid", "docs_consistency", "architecture_gates"]


def test_code_change_runs_full_gates():
    gates = resolve_ci_gates(["app/api/routes_runs.py"], event_name="pull_request")
    assert "coverage" in gates
    assert "import_contracts" in gates
    assert "pyright_decider" in gates
    assert "pytest" not in gates  # coverage 가 흡수한다


def test_security_path_adds_security_gates():
    gates = resolve_ci_gates(["app/platform/security/input_crypto.py"], event_name="pull_request")
    assert "pip_audit" in gates
    assert "bandit_security" in gates


def test_encrypted_input_store_is_a_security_path():
    """2026-08-17 회귀: 이 경로가 security 필터에서 빠져 있었다."""
    assert matches_any(
        "app/contexts/run/infrastructure/encrypted_run_input_store.py",
        SECURITY_PATHS,
    )


def test_non_security_code_change_skips_security_gates():
    gates = resolve_ci_gates(["app/web/static/dashboard.js"], event_name="pull_request")
    assert "pip_audit" not in gates


def test_schedule_event_runs_everything():
    gates = resolve_ci_gates([], event_name="schedule")
    assert "pip_audit" in gates
    assert "coverage" in gates


def test_never_returns_empty_list():
    """빈 matrix 는 GitHub Actions 가 오류로 처리한다."""
    assert resolve_ci_gates([], event_name="pull_request") != []


def test_gate_list_has_no_duplicates():
    gates = resolve_ci_gates(
        ["app/contexts/identity/service.py", "requirements.txt"],
        event_name="pull_request",
    )
    assert len(gates) == len(set(gates))
