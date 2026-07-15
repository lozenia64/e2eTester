#!/usr/bin/env python3
"""Run T1 planning gate and write planning-gate-report.json."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from orchestration_gates import e2e_profile, validate_planning_gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run e2e planning gate (T1)")
    parser.add_argument("--run-dir", required=True, help="Absolute path to run directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    run_json_path = run_dir / "run.json"
    if not run_json_path.is_file():
        print(json.dumps({"error": "run.json not found"}))
        return 1

    run_data = json.loads(run_json_path.read_text(encoding="utf-8"))
    workspace = Path(run_data["workspace"])
    profile = e2e_profile(run_data)
    if not profile:
        intake_path = run_dir / "intake.json"
        if intake_path.is_file():
            intake = json.loads(intake_path.read_text(encoding="utf-8"))
            profile = e2e_profile(intake)

    result = validate_planning_gate(run_dir, workspace, profile)
    report = {
        **result,
        "profile": profile,
        "ran_at": datetime.now(UTC).isoformat(),
    }
    out_path = run_dir / "planning-gate-report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "path": str(out_path)}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
