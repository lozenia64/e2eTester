#!/usr/bin/env python3
"""Wait for the next worker_done/escalation and record the verdict in loop state."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loop_state import append_trace, read_loop, write_loop
from orca_cli import configure_stdout_utf8, run_orca

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG = ROOT / ".cursor" / "orchestration" / "plan-build-verify-loop.config.json"


def load_timeout(config_path: Path, override_ms: int | None) -> int:
    if override_ms is not None:
        return override_ms
    if config_path.is_file():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return int(data.get("wait_timeout_ms") or 1800000)
    return 1800000


def verdict_from_message(msg: dict[str, Any]) -> str:
    msg_type = str(msg.get("type") or "")
    subject = str(msg.get("subject") or "")
    body = str(msg.get("body") or "")
    combined = f"{subject} {body}".upper()
    if msg_type == "escalation":
        return "FAIL"
    if "PASS" in combined and "FAIL" not in subject.upper():
        return "PASS"
    if "FAIL" in combined:
        return "FAIL"
    return "UNKNOWN"


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="Wait for next worker_done/escalation")
    parser.add_argument("--loop-dir", required=True)
    parser.add_argument("--timeout-ms", type=int, default=None)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()

    loop_dir = Path(args.loop_dir).resolve()
    loop = read_loop(loop_dir)
    timeout_ms = load_timeout(Path(args.config), args.timeout_ms)

    data = run_orca(
        [
            "orchestration",
            "check",
            "--wait",
            "--types",
            "worker_done,escalation,decision_gate",
            f"--timeout-ms={timeout_ms}",
            "--json",
        ]
    )

    if not data.get("ok"):
        print(json.dumps({"ok": False, "error": data.get("error"), "timed_out": True}))
        return 2

    result = data.get("result") or {}
    count = int(result.get("count") or 0)
    if count == 0:
        loop["status"] = "wait_timeout"
        loop["updated_at"] = datetime.now(UTC).isoformat()
        write_loop(loop_dir, loop)
        print(json.dumps({"ok": False, "timed_out": True, "timeout_ms": timeout_ms}))
        return 2

    msg = result.get("message") or result.get("messages", [{}])[0]
    verdict = verdict_from_message(msg)

    now = datetime.now(UTC).isoformat()
    history_entry = {
        "phase": loop.get("phase"),
        "task_id": loop.get("last_task_id"),
        "verdict": verdict,
        "type": msg.get("type"),
        "subject": msg.get("subject"),
        "body": msg.get("body"),
        "at": now,
    }
    loop.setdefault("history", []).append(history_entry)
    loop["last_verdict"] = verdict
    loop["updated_at"] = now
    write_loop(loop_dir, loop)
    append_trace(loop_dir, f"{now} received type={msg.get('type')} verdict={verdict}")

    out = {
        "ok": True,
        "verdict": verdict,
        "message": {
            "type": msg.get("type"),
            "subject": msg.get("subject"),
            "body": msg.get("body"),
            "payload": msg.get("payload"),
        },
        "phase": loop.get("phase"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
