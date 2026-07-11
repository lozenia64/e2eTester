#!/usr/bin/env python3
"""Run e2eTester CI gates and write gates-report.json."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

GATE_COMMANDS: dict[str, list[str]] = {
    "docs_consistency": ["python3", "scripts/check_docs_consistency.py"],
    "ruff": ["python3", "-m", "ruff", "check", "."],
    "ruff_format": ["python3", "-m", "ruff", "format", "--check", "."],
    "pytest": ["python3", "-m", "pytest", "tests/", "-q"],
}

PROFILE_GATES: dict[str, list[str]] = {
    "step_fix": ["docs_consistency", "ruff", "ruff_format", "pytest"],
    "new_module": ["docs_consistency", "ruff", "ruff_format", "pytest"],
    "new_system": ["docs_consistency", "ruff", "ruff_format", "pytest"],
    "platform": ["docs_consistency", "ruff", "ruff_format", "pytest"],
    "healing_patch": ["docs_consistency", "ruff", "ruff_format", "pytest"],
    "docs_only": ["docs_consistency"],
    "spike": [],
}


def run_command(cmd: list[str], cwd: Path) -> dict:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        return {
            "command": " ".join(cmd),
            "passed": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-8000:] if proc.stdout else "",
            "stderr": proc.stderr[-8000:] if proc.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {
            "command": " ".join(cmd),
            "passed": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "timeout after 600s",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run e2e CI gates")
    parser.add_argument("--run-dir", required=True, help="Absolute path to run directory")
    parser.add_argument(
        "--profile",
        default=None,
        help="Pipeline profile (reads from run.json if omitted)",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    run_json_path = run_dir / "run.json"
    if not run_json_path.exists():
        print(json.dumps({"error": "run.json not found"}))
        return 1

    run_data = json.loads(run_json_path.read_text(encoding="utf-8"))
    workspace = Path(run_data["workspace"])
    profile = args.profile or run_data.get("pipeline_profile")
    if not profile:
        print(json.dumps({"error": "pipeline_profile missing; run intake first or pass --profile"}))
        return 1
    if profile not in PROFILE_GATES:
        print(json.dumps({"error": f"unknown pipeline_profile: {profile}"}))
        return 1
    gate_names = PROFILE_GATES[profile]

    results: dict[str, dict] = {}
    for name in gate_names:
        results[name] = run_command(GATE_COMMANDS[name], workspace)

    passed = all(r["passed"] for r in results.values()) if results else True
    report = {
        "passed": passed,
        "profile": profile,
        "gates": results,
        "ran_at": datetime.now(UTC).isoformat(),
    }

    out_path = run_dir / "gates-report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "path": str(out_path)}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
