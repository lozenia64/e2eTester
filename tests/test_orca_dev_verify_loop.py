"""Unit tests for Orca dev-verify loop helpers (no Orca runtime required)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".cursor" / "skills" / "orca-dev-verify-loop" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from loop_state import build_verifier_spec  # noqa: E402


def test_build_verifier_spec_substitutes_placeholders(tmp_path: Path):
    loop_dir = tmp_path / "loop"
    loop_dir.mkdir()
    loop = {
        "user_request": "README 정리",
        "loop_dir": str(loop_dir),
        "max_iterations": 3,
        "gates_command": "python3 scripts/ci/run_all_gates.py --profile full",
        "changed_files": ["README.md"],
    }
    spec = build_verifier_spec(loop, iteration=1)
    assert "README 정리" in spec
    assert str(loop_dir) in spec
    assert "README.md" in spec
    assert "run_all_gates.py" in spec


def test_init_loop_creates_loop_json(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".cursor" / "orchestration").mkdir(parents=True)
    script = SCRIPTS / "init_loop.py"
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(script), str(workspace), "test goal"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    loop_dir = Path(data["loop_dir"])
    loop = json.loads((loop_dir / "loop.json").read_text(encoding="utf-8"))
    assert loop["user_request"] == "test goal"
    assert loop["pattern"] == "orca_dev_verify_loop"
    assert loop["max_iterations"] == 3


def test_verdict_from_report(tmp_path: Path):
    from wait_worker import verdict_from_message

    loop_dir = tmp_path / "loop"
    loop_dir.mkdir()
    (loop_dir / "verify-report.json").write_text(
        json.dumps({"gate_decision": "FAIL", "summary_ko": "게이트 실패"}),
        encoding="utf-8",
    )
    msg = {"subject": "done", "body": "checked"}
    assert verdict_from_message(msg, loop_dir) == "FAIL"
