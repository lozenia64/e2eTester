#!/usr/bin/env python3
"""Run e2eTester CI gates and write gates-report.json (orchestrator QC)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _load_gates_module(workspace: Path) -> Any:
    gates_path = workspace / "scripts" / "ci" / "gates.py"
    if not gates_path.is_file():
        msg = f"gates SSOT not found: {gates_path}"
        raise FileNotFoundError(msg)
    spec = importlib.util.spec_from_file_location("e2e_ci_gates", gates_path)
    if spec is None or spec.loader is None:
        msg = f"cannot load gates module: {gates_path}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Run e2e CI gates")
    parser.add_argument("--run-dir", required=True, help="Absolute path to run directory")
    parser.add_argument(
        "--profile",
        default=None,
        help="Pipeline profile (reads from run.json if omitted)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        default=True,
        help="Stop after first failing tier (default: true)",
    )
    parser.add_argument(
        "--no-fail-fast",
        action="store_false",
        dest="fail_fast",
        help="Run all gates even after tier failure",
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
        intake_path = run_dir / "intake.json"
        if intake_path.is_file():
            intake = json.loads(intake_path.read_text(encoding="utf-8"))
            profile = intake.get("pipeline_profile")
    if not profile:
        print(json.dumps({"error": "pipeline_profile missing; run intake first or pass --profile"}))
        return 1

    intake_path = run_dir / "intake.json"
    risk_flags: list[str] = []
    if intake_path.is_file():
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
        risk_flags = list(intake.get("risk_flags") or [])

    try:
        gates_mod = _load_gates_module(workspace)
        gate_names = gates_mod.resolve_gates(profile, risk_flags or None)
    except (FileNotFoundError, KeyError) as exc:
        msg = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
        print(json.dumps({"error": msg}))
        return 1

    changed_files = gates_mod.resolve_changed_files(workspace)
    results = gates_mod.run_gates(
        gate_names,
        workspace,
        stop_on_tier_failure=args.fail_fast,
        changed_files=changed_files,
    )
    passed = all(r["passed"] for r in results.values()) if results else True
    report = {
        "passed": passed,
        "profile": profile,
        "risk_flags": risk_flags,
        "changed_files": changed_files,
        "fail_fast": args.fail_fast,
        "gates": results,
        "ran_at": datetime.now(UTC).isoformat(),
    }

    out_path = run_dir / "gates-report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "path": str(out_path)}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
