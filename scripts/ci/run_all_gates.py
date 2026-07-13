#!/usr/bin/env python3
"""Run all e2eTester CI gates (SSOT entry point for local pre-PR and CI parity)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.platform.stdio_utf8 import configure_stdio_utf8  # noqa: E402
from scripts.ci.gates import (  # noqa: E402
    resolve_gates,
    run_gates,
)


def main() -> int:
    configure_stdio_utf8()
    parser = argparse.ArgumentParser(description="Run e2eTester CI gates (SSOT)")
    parser.add_argument(
        "--workspace",
        default=str(ROOT),
        help="Repository root (default: auto-detect)",
    )
    parser.add_argument(
        "--profile",
        default="full",
        help="Pipeline profile (full = standard CI gates)",
    )
    parser.add_argument(
        "--risk-flags",
        default="",
        help="Comma-separated risk flags (pii,otp,auth) for conditional security gates",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional path to write gates-report.json",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after first failing gate",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    risk_flags = [f.strip() for f in args.risk_flags.split(",") if f.strip()]

    try:
        gate_names = resolve_gates(args.profile, risk_flags or None)
    except KeyError as exc:
        print(json.dumps({"error": exc.args[0] if exc.args else str(exc)}))
        return 1

    if not gate_names:
        print(json.dumps({"passed": True, "profile": args.profile, "gates": {}}))
        return 0

    results = run_gates(gate_names, workspace, stop_on_first_failure=args.fail_fast)
    passed = all(r["passed"] for r in results.values())
    report = {
        "passed": passed,
        "profile": args.profile,
        "risk_flags": risk_flags,
        "gates": results,
        "ran_at": datetime.now(UTC).isoformat(),
    }

    if args.report:
        out = Path(args.report)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({"passed": passed, "profile": args.profile, "gate_count": len(results)}))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
