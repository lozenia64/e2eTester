"""Unit tests for unified e2e-orchestrator graph resolution and validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".cursor" / "skills" / "e2e-orchestrator" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from resolve_graph import PROFILE_SPECS, resolve_from_intake  # noqa: E402

VALID_SUBAGENT_TYPES = frozenset(
    {
        "generalPurpose",
        "explore",
        "architect",
        "implementer",
        "documenter",
        "test-runner",
        "bugbot",
        "security-review",
        "verifier",
        "guardian",
        "triage",
        "shell",
        "ci-investigator",
        "docs-researcher",
        "debugger",
    }
)

REGISTRY_PATH = ROOT / ".cursor" / "skills" / "e2e-orchestrator" / "unified-registry.md"


def _base_intake(profile: str, **overrides: object) -> dict:
    data = {
        "e2e_pipeline_profile": profile,
        "pipeline_profile": profile,
        "system_code": None,
        "layer": "web",
        "touch_surfaces": ["api"],
        "affected_modules": [],
        "risk_flags": [],
        "conditional_agents": [],
        "dev_path": "standard",
        "ship_requested": False,
        "agent_graph": None,
        "summary": "test",
    }
    data.update(overrides)
    return data


def test_platform_graph_includes_dev_and_e2e_and_guardian():
    resolved = resolve_from_intake(_base_intake("platform", risk_flags=["user_facing"]))
    graph = resolved["agent_graph"]
    assert "dev-spec-writer" in graph
    assert "e2e-platform-architect" in graph
    assert "guardian" in graph
    assert graph.index("guardian") < graph.index("e2e-implementer")
    assert "dev-ux-designer" in graph
    assert "e2e-code-reviewer" in resolved["qc_agents"]


def test_ship_only_when_requested_and_eligible():
    no_ship = resolve_from_intake(_base_intake("platform", ship_requested=False))
    assert no_ship["ship_agents"] == []

    with_ship = resolve_from_intake(_base_intake("platform", ship_requested=True))
    assert with_ship["ship_agents"] == ["dev-pr-publisher", "dev-ci-watcher"]

    docs = resolve_from_intake(_base_intake("docs_only", ship_requested=True))
    assert docs["ship_agents"] == []


def test_spike_stops_after_research():
    resolved = resolve_from_intake(_base_intake("spike"))
    assert resolved["stop_after_research"] is True
    assert resolved["agent_graph"] == []


def test_security_qc_inserted_for_auth_flags():
    resolved = resolve_from_intake(_base_intake("step_fix", risk_flags=["auth", "otp"]))
    assert "e2e-security-auditor" in resolved["qc_agents"]


def test_resolve_graph_writes_run_json(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    intake = _base_intake("platform")
    (run_dir / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
    (run_dir / "run.json").write_text(
        json.dumps({"workspace": str(ROOT), "context_variables": {}}), encoding="utf-8"
    )

    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "resolve_graph.py"), "--run-dir", str(run_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    run_data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert run_data["orchestrator_version"] == "2.0"
    assert len(run_data["agent_graph"]) > 5
    assert (run_dir / "agent_graph.json").is_file()


def test_intake_rejects_hand_built_graph(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    bad_intake = _base_intake("platform")
    bad_intake["agent_graph"] = ["e2e-implementer"]
    (run_dir / "bad-intake.json").write_text(json.dumps(bad_intake), encoding="utf-8")
    (run_dir / "intake.json").write_text(json.dumps(bad_intake), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "validate_artifacts.py"),
            "--run-dir",
            str(run_dir),
            "--agent",
            "e2e-intake",
        ],
        capture_output=True,
        text=True,
    )
    result = json.loads(proc.stdout or proc.stderr or "{}")
    assert result.get("valid") is False


def test_registry_subagent_types_are_valid():
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    invalid = []
    for line in text.splitlines():
        if "|" not in line or "subagent_type" in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        subagent_type = parts[4]
        if subagent_type in ("planner", "docs-writer"):
            invalid.append(line)
    assert invalid == []


@pytest.mark.parametrize("profile", sorted(PROFILE_SPECS.keys()))
def test_all_profiles_resolve(profile: str):
    resolved = resolve_from_intake(_base_intake(profile))
    assert resolved["e2e_pipeline_profile"] == profile
