"""CI gate SSOT — GitHub Actions, run_all_gates.py, e2e-orchestrator run_gates.py."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

# Gate name → shell command (run from workspace root)
GATE_COMMANDS: dict[str, list[str]] = {
    "docs_consistency": ["python3", "scripts/check_docs_consistency.py"],
    "architecture_gates": ["python3", "scripts/check_architecture_gates.py"],
    "projection_validate": [
        "python3",
        "scripts/rebuild_projections.py",
        "--validate",
        "--db",
        "data/.ci_projection_validate.db",
    ],
    "ruff": ["python3", "-m", "ruff", "check", "."],
    "ruff_format": ["python3", "-m", "ruff", "format", "--check", "."],
    "pytest": ["python3", "-m", "pytest", "tests/", "-q"],
    "pip_audit": [
        "python3",
        "-m",
        "pip_audit",
        "-r",
        "requirements.txt",
    ],
    "bandit_security": [
        "python3",
        "-m",
        "bandit",
        "-c",
        "pyproject.toml",
        "-r",
        "app/auth",
        "app/api/routes_trigger.py",
        "app/api/routes_otp.py",
    ],
}

# Fail-fast tier (lower runs first in sequential local runner; CI jobs run in parallel per tier group)
GATE_TIERS: dict[str, int] = {
    "docs_consistency": 0,
    "ruff": 0,
    "ruff_format": 0,
    "architecture_gates": 1,
    "projection_validate": 1,
    "pytest": 2,
    "pip_audit": 3,
    "bandit_security": 3,
}

STANDARD_GATES: list[str] = [
    "docs_consistency",
    "architecture_gates",
    "projection_validate",
    "ruff",
    "ruff_format",
    "pytest",
]

SECURITY_GATES: list[str] = ["pip_audit", "bandit_security"]

PROFILE_GATES: dict[str, list[str]] = {
    "step_fix": STANDARD_GATES,
    "new_module": STANDARD_GATES,
    "new_system": STANDARD_GATES + SECURITY_GATES,
    "platform": STANDARD_GATES,
    "healing_patch": STANDARD_GATES,
    "docs_only": ["docs_consistency", "architecture_gates"],
    "spike": [],
    "full": STANDARD_GATES,
}

SECURITY_PROFILES: frozenset[str] = frozenset({"new_system"})
SECURITY_RISK_FLAGS: frozenset[str] = frozenset({"pii", "otp", "auth"})


def resolve_gates(profile: str, risk_flags: list[str] | None = None) -> list[str]:
    """Return ordered gate names for a pipeline profile (+ optional security gates)."""
    if profile not in PROFILE_GATES:
        msg = f"unknown pipeline_profile: {profile}"
        raise KeyError(msg)
    gates = list(PROFILE_GATES[profile])
    flags = set(risk_flags or [])
    if profile in SECURITY_PROFILES or flags & SECURITY_RISK_FLAGS:
        for name in SECURITY_GATES:
            if name not in gates:
                gates.append(name)
    return gates


def run_gate(name: str, workspace: Path, *, timeout: int = 600) -> dict[str, Any]:
    """Execute one gate; return result dict with duration_ms and tier."""
    if name not in GATE_COMMANDS:
        msg = f"unknown gate: {name}"
        raise KeyError(msg)
    cmd = GATE_COMMANDS[name]
    started = time.perf_counter()
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        proc = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "command": " ".join(cmd),
            "passed": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-8000:] if proc.stdout else "",
            "stderr": proc.stderr[-8000:] if proc.stderr else "",
            "duration_ms": elapsed_ms,
            "tier": GATE_TIERS.get(name, 0),
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "command": " ".join(cmd),
            "passed": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"timeout after {timeout}s",
            "duration_ms": elapsed_ms,
            "tier": GATE_TIERS.get(name, 0),
        }


def run_gates(
    gate_names: list[str],
    workspace: Path,
    *,
    stop_on_first_failure: bool = False,
) -> dict[str, dict[str, Any]]:
    """Run gates in tier order (stable within same tier)."""
    ordered = sorted(gate_names, key=lambda n: (GATE_TIERS.get(n, 99), n))
    results: dict[str, dict[str, Any]] = {}
    for name in ordered:
        result = run_gate(name, workspace)
        results[name] = result
        if stop_on_first_failure and not result["passed"]:
            break
    return results
