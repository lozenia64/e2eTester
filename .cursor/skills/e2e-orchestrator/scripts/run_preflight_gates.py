#!/usr/bin/env python3
"""Run T2 preflight gates (changed-file lint/format) and write preflight-report.json."""

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
    spec = importlib.util.spec_from_file_location("e2e_ci_gates", gates_path)
    if spec is None or spec.loader is None:
        msg = f"cannot load gates module: {gates_path}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Run e2e preflight gates (T2)")
    parser.add_argument("--run-dir", required=True, help="Absolute path to run directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    run_json_path = run_dir / "run.json"
    if not run_json_path.is_file():
        print(json.dumps({"error": "run.json not found"}))
        return 1

    run_data = json.loads(run_json_path.read_text(encoding="utf-8"))
    workspace = Path(run_data["workspace"])
    profile = run_data.get("pipeline_profile") or ""

    if profile == "spike":
        report = {
            "passed": True,
            "skipped": True,
            "profile": profile,
            "gates": {},
            "changed_files": [],
            "ran_at": datetime.now(UTC).isoformat(),
        }
        out_path = run_dir / "preflight-report.json"
        out_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps({"passed": True, "skipped": True, "path": str(out_path)}))
        return 0

    gates_mod = _load_gates_module(workspace)
    changed_files = gates_mod.resolve_changed_files(workspace)
    gate_names = list(gates_mod.PREFLIGHT_GATES)
    results = gates_mod.run_gates(
        gate_names,
        workspace,
        stop_on_first_failure=True,
        changed_files=changed_files,
    )
    passed = all(r["passed"] for r in results.values()) if results else True
    report = {
        "passed": passed,
        "profile": profile,
        "changed_files": changed_files,
        "gates": results,
        "ran_at": datetime.now(UTC).isoformat(),
    }
    out_path = run_dir / "preflight-report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "path": str(out_path)}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
