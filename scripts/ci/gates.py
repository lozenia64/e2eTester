"""CI gate SSOT — GitHub Actions and scripts/ci/run_all_gates.py."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _py(*parts: str) -> list[str]:
    """Build a gate command using the current interpreter (Windows/macOS parity)."""
    return [sys.executable, *parts]


# Gate name → shell command (run from workspace root)
GATE_COMMANDS: dict[str, list[str]] = {
    "docs_consistency": _py("scripts/check_docs_consistency.py"),
    "architecture_gates": _py("scripts/check_architecture_gates.py"),
    "projection_validate": _py(
        "scripts/rebuild_projections.py",
        "--validate",
        "--db",
        "data/.ci_projection_validate.db",
    ),
    "snapshot_validate": _py(
        "scripts/rebuild_snapshots.py",
        "--validate",
        "--db",
        "data/.ci_snapshot_validate.db",
    ),
    "import_contracts": _py("-m", "importlinter.cli", "lint"),
    "pyright_decider": _py(
        "-m",
        "pyright",
        "app/contexts/run/domain/decider.py",
        "app/contexts/suite/domain/decider.py",
    ),
    "ruff": _py("-m", "ruff", "check", "."),
    "ruff_format": _py("-m", "ruff", "format", "--check", "."),
    "pytest": _py("-m", "pytest", "tests/", "-q"),
    "pip_audit": _py("-m", "pip_audit", "-r", "requirements.txt"),
    "bandit_security": _py(
        "-m",
        "bandit",
        "-c",
        "pyproject.toml",
        "-r",
        "app/contexts/identity",
        "app/api/routes_trigger.py",
        "app/api/routes_otp.py",
    ),
}

PREFLIGHT_GATES: list[str] = ["ruff_changed", "ruff_format_changed"]

# Fail-fast tier (lower runs first in sequential local runner; CI jobs run in parallel per tier group)
GATE_TIERS: dict[str, int] = {
    "docs_consistency": 0,
    "ruff": 0,
    "ruff_format": 0,
    "ruff_changed": 0,
    "ruff_format_changed": 0,
    "architecture_gates": 1,
    "import_contracts": 1,
    "pyright_decider": 1,
    "projection_validate": 1,
    "snapshot_validate": 1,
    "pytest": 2,
    "pip_audit": 3,
    "bandit_security": 3,
}

STANDARD_GATES: list[str] = [
    "docs_consistency",
    "architecture_gates",
    "import_contracts",
    "pyright_decider",
    "projection_validate",
    "snapshot_validate",
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

_PATH_IN_BACKTICKS = re.compile(r"`([^`]+)`")
_PATH_LIKE = re.compile(r"(?:^|\s)((?:app|docs|scripts|tests)/[^\s`]+)")


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


def resolve_changed_files(workspace: Path) -> list[str]:
    """Return repo-relative paths changed vs HEAD (staged, unstaged, untracked)."""
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    paths: set[str] = set()
    for cmd in (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "diff", "--name-only", "--cached", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            proc = subprocess.run(
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except OSError:
            continue
        if proc.returncode == 0 and proc.stdout:
            for line in proc.stdout.splitlines():
                rel = line.strip().replace("\\", "/")
                if rel:
                    paths.add(rel)
    return sorted(paths)


def filter_python_files(paths: list[str]) -> list[str]:
    """Keep only .py files that exist on disk."""
    return [p for p in paths if p.endswith(".py")]


def parse_ruff_findings(stdout: str) -> list[dict[str, Any]]:
    """Parse ruff JSON output into structured findings."""
    if not stdout.strip():
        return []
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    findings: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        location = item.get("location") or {}
        findings.append(
            {
                "file": item.get("filename", ""),
                "line": location.get("row"),
                "rule": item.get("code", ""),
                "message": item.get("message", ""),
            }
        )
    return findings


def _run_subprocess(
    cmd: list[str],
    workspace: Path,
    *,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.run(
        cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )


def _gate_result(
    *,
    name: str,
    cmd: list[str],
    passed: bool,
    returncode: int,
    stdout: str,
    stderr: str,
    duration_ms: int,
    findings: list[dict[str, Any]] | None = None,
    changed_files: list[str] | None = None,
    skipped: bool = False,
    skip_reason: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "command": " ".join(cmd),
        "passed": passed,
        "returncode": returncode,
        "stdout": stdout[-8000:] if stdout else "",
        "stderr": stderr[-8000:] if stderr else "",
        "duration_ms": duration_ms,
        "tier": GATE_TIERS.get(name, 0),
    }
    if findings is not None:
        result["findings"] = findings
    if changed_files is not None:
        result["changed_files"] = changed_files
    if skipped:
        result["skipped"] = True
        result["skip_reason"] = skip_reason
    return result


def run_gate(
    name: str,
    workspace: Path,
    *,
    timeout: int = 600,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """Execute one gate; return result dict with duration_ms and tier."""
    started = time.perf_counter()

    if name == "ruff_changed":
        py_files = filter_python_files(changed_files or resolve_changed_files(workspace))
        if not py_files:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return _gate_result(
                name=name,
                cmd=[sys.executable, "-m", "ruff", "check", "(no changed .py files)"],
                passed=True,
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=elapsed_ms,
                findings=[],
                changed_files=py_files,
                skipped=True,
                skip_reason="no changed python files",
            )
        cmd = [sys.executable, "-m", "ruff", "check", "--output-format", "json", *py_files]
        try:
            proc = _run_subprocess(cmd, workspace, timeout=timeout)
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return _gate_result(
                name=name,
                cmd=cmd,
                passed=False,
                returncode=-1,
                stdout="",
                stderr=f"timeout after {timeout}s",
                duration_ms=elapsed_ms,
                findings=[],
                changed_files=py_files,
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        findings = parse_ruff_findings(proc.stdout)
        return _gate_result(
            name=name,
            cmd=cmd,
            passed=proc.returncode == 0,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_ms=elapsed_ms,
            findings=findings,
            changed_files=py_files,
        )

    if name == "ruff_format_changed":
        py_files = filter_python_files(changed_files or resolve_changed_files(workspace))
        if not py_files:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return _gate_result(
                name=name,
                cmd=[sys.executable, "-m", "ruff", "format", "--check", "(no changed .py files)"],
                passed=True,
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=elapsed_ms,
                findings=[],
                changed_files=py_files,
                skipped=True,
                skip_reason="no changed python files",
            )
        cmd = [sys.executable, "-m", "ruff", "format", "--check", *py_files]
        try:
            proc = _run_subprocess(cmd, workspace, timeout=timeout)
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return _gate_result(
                name=name,
                cmd=cmd,
                passed=False,
                returncode=-1,
                stdout="",
                stderr=f"timeout after {timeout}s",
                duration_ms=elapsed_ms,
                findings=[],
                changed_files=py_files,
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return _gate_result(
            name=name,
            cmd=cmd,
            passed=proc.returncode == 0,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_ms=elapsed_ms,
            findings=[],
            changed_files=py_files,
        )

    if name not in GATE_COMMANDS:
        msg = f"unknown gate: {name}"
        raise KeyError(msg)

    cmd = list(GATE_COMMANDS[name])
    if name == "ruff":
        cmd = [sys.executable, "-m", "ruff", "check", "--output-format", "json", "."]
    try:
        proc = _run_subprocess(cmd, workspace, timeout=timeout)
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return _gate_result(
            name=name,
            cmd=cmd,
            passed=False,
            returncode=-1,
            stdout="",
            stderr=f"timeout after {timeout}s",
            duration_ms=elapsed_ms,
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    findings: list[dict[str, Any]] | None = None
    if name == "ruff":
        findings = parse_ruff_findings(proc.stdout)
    changed = resolve_changed_files(workspace) if name in {"ruff", "ruff_format"} else None
    return _gate_result(
        name=name,
        cmd=cmd,
        passed=proc.returncode == 0,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_ms=elapsed_ms,
        findings=findings,
        changed_files=changed,
    )


def run_gates(
    gate_names: list[str],
    workspace: Path,
    *,
    stop_on_first_failure: bool = False,
    stop_on_tier_failure: bool = False,
    changed_files: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run gates in tier order (stable within same tier)."""
    ordered = sorted(gate_names, key=lambda n: (GATE_TIERS.get(n, 99), n))
    results: dict[str, dict[str, Any]] = {}
    failed_tiers: set[int] = set()
    for name in ordered:
        tier = GATE_TIERS.get(name, 0)
        if stop_on_tier_failure and tier in failed_tiers:
            results[name] = _gate_result(
                name=name,
                cmd=[],
                passed=False,
                returncode=-1,
                stdout="",
                stderr=f"skipped: tier {tier} already failed",
                duration_ms=0,
                skipped=True,
                skip_reason=f"tier {tier} failure",
            )
            continue
        result = run_gate(name, workspace, changed_files=changed_files)
        results[name] = result
        if not result["passed"]:
            if stop_on_first_failure:
                break
            if stop_on_tier_failure:
                failed_tiers.add(tier)
    return results


def extract_paths_from_markdown(text: str) -> list[str]:
    """Extract repo-relative paths from markdown backticks and path-like tokens."""
    paths: list[str] = []
    for match in _PATH_IN_BACKTICKS.finditer(text):
        candidate = match.group(1).strip().replace("\\", "/")
        if candidate.startswith(("app/", "docs/", "scripts/", "tests/")):
            paths.append(candidate)
    for match in _PATH_LIKE.finditer(text):
        candidate = match.group(1).strip().replace("\\", "/")
        paths.append(candidate)
    return paths
