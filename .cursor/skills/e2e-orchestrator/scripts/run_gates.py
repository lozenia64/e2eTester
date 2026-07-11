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

    intake_path = run_dir / "intake.json"
    risk_flags: list[str] = []
    if intake_path.is_file():
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
        risk_flags = list(intake.get("risk_flags") or [])

    try:
        gates_mod = _load_gates_module(workspace)
        gate_names = gates_mod.resolve_gates(profile, risk_flags or None)
    except (FileNotFoundError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    results: dict[str, dict] = {}
    for name in gate_names:
        results[name] = gates_mod.run_gate(name, workspace)

    passed = all(r["passed"] for r in results.values()) if results else True
    report = {
        "passed": passed,
        "profile": profile,
        "risk_flags": risk_flags,
        "gates": results,
        "ran_at": datetime.now(UTC).isoformat(),
    }

    out_path = run_dir / "gates-report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "path": str(out_path)}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
