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
