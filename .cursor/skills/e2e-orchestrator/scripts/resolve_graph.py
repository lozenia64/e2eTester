#!/usr/bin/env python3
"""Mechanically resolve agent graph from unified intake + profiles."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

E2E_PROFILES = frozenset(
    {
        "step_fix",
        "new_module",
        "new_system",
        "platform",
        "healing_patch",
        "docs_only",
        "spike",
    }
)

SHIP_ELIGIBLE = frozenset(
    {"step_fix", "new_module", "new_system", "platform", "healing_patch"}
)

SECURITY_FLAGS = frozenset({"pii", "otp", "auth"})
DEV_SECURITY_FLAGS = frozenset(
    {"auth", "pii", "input_validation", "dependencies", "network"}
)

PROFILE_SPECS: dict[str, dict[str, Any]] = {
    "step_fix": {
        "dev_profile": "hotfix",
        "dev_graph": ["dev-context-scout"],
        "e2e_graph": [
            "e2e-domain-scout",
            "e2e-scenario-analyst",
            "e2e-selector-healer",
        ],
        "guardian": True,
        "qc": ["e2e-test-runner", "e2e-code-reviewer", "dev-build-integrator"],
        "ship_eligible": True,
        "skip_research": False,
        "last_planner": "e2e-selector-healer",
        "implementer": "e2e-implementer",
    },
    "new_module": {
        "dev_profile": "feature",
        "dev_graph": [
            "dev-spec-writer",
            "dev-context-scout",
            "dev-architect",
            "dev-task-planner",
        ],
        "e2e_graph": [
            "e2e-scenario-analyst",
            "e2e-manifest-planner",
            "e2e-docs-guardian",
        ],
        "guardian": True,
        "qc": ["e2e-test-runner", "e2e-code-reviewer", "dev-build-integrator"],
        "ship_eligible": True,
        "skip_research": False,
        "last_planner": "e2e-docs-guardian",
        "implementer": "e2e-implementer",
    },
    "new_system": {
        "dev_profile": "feature",
        "dev_graph": [
            "dev-spec-writer",
            "dev-context-scout",
            "dev-architect",
            "dev-task-planner",
        ],
        "e2e_graph": [
            "e2e-domain-scout",
            "e2e-platform-architect",
            "e2e-manifest-planner",
            "e2e-docs-guardian",
        ],
        "guardian": True,
        "qc": [
            "e2e-test-runner",
            "e2e-code-reviewer",
            "e2e-security-auditor",
            "dev-build-integrator",
        ],
        "ship_eligible": True,
        "skip_research": False,
        "last_planner": "e2e-docs-guardian",
        "implementer": "e2e-implementer",
    },
    "platform": {
        "dev_profile": "feature",
        "dev_graph": [
            "dev-spec-writer",
            "dev-context-scout",
            "dev-architect",
            "dev-task-planner",
        ],
        "e2e_graph": ["e2e-domain-scout", "e2e-platform-architect"],
        "guardian": True,
        "qc": ["e2e-test-runner", "e2e-code-reviewer", "dev-build-integrator"],
        "ship_eligible": True,
        "skip_research": False,
        "last_planner": "e2e-platform-architect",
        "implementer": "e2e-implementer",
    },
    "healing_patch": {
        "dev_profile": "hotfix",
        "dev_graph": ["dev-context-scout"],
        "e2e_graph": ["e2e-selector-healer"],
        "guardian": True,
        "qc": ["e2e-test-runner", "e2e-code-reviewer", "dev-build-integrator"],
        "ship_eligible": True,
        "skip_research": False,
        "last_planner": "e2e-selector-healer",
        "implementer": "e2e-implementer",
    },
    "docs_only": {
        "dev_profile": "docs",
        "dev_graph": [],
        "e2e_graph": ["e2e-docs-guardian", "e2e-docs-writer"],
        "guardian": False,
        "qc": ["e2e-test-runner"],
        "ship_eligible": False,
        "skip_research": True,
        "last_planner": "e2e-docs-guardian",
        "implementer": "e2e-docs-writer",
    },
    "spike": {
        "dev_profile": "spike",
        "dev_graph": [],
        "e2e_graph": [],
        "guardian": False,
        "qc": [],
        "ship_eligible": False,
        "skip_research": False,
        "last_planner": None,
        "implementer": None,
        "stop_after_research": True,
    },
}


def _profile_key(intake: dict[str, Any]) -> str:
    profile = intake.get("e2e_pipeline_profile") or intake.get("pipeline_profile")
    if not profile or profile not in E2E_PROFILES:
        msg = f"invalid or missing e2e_pipeline_profile: {profile!r}"
        raise ValueError(msg)
    return str(profile)


def _has_flag(flags: list[str], candidates: frozenset[str]) -> bool:
    return bool(candidates.intersection(flags))


def _insert_after(graph: list[str], after: str, agent: str) -> None:
    if agent in graph:
        return
    if after not in graph:
        graph.append(agent)
        return
    idx = graph.index(after) + 1
    graph.insert(idx, agent)


def resolve_from_intake(intake: dict[str, Any]) -> dict[str, Any]:
    """Return resolved graph metadata from intake.json fields."""
    profile = _profile_key(intake)
    spec = PROFILE_SPECS[profile]

    risk_flags = list(intake.get("risk_flags") or [])
    conditional = set(intake.get("conditional_agents") or [])
    dev_path = intake.get("dev_path") or "standard"
    ship_requested = bool(intake.get("ship_requested"))

    graph: list[str] = []

    if dev_path == "minimal":
        graph.append("triage")

    graph.extend(spec["dev_graph"])

    if "unknown_tech" in risk_flags and "dev-researcher" not in graph:
        anchor = "dev-context-scout" if "dev-context-scout" in graph else graph[-1] if graph else ""
        if anchor:
            _insert_after(graph, anchor, "dev-researcher")
        else:
            graph.append("dev-researcher")

    if "dev-ux-designer" in conditional or "user_facing" in risk_flags:
        if "dev-task-planner" in graph:
            _insert_after(graph, "dev-task-planner", "dev-ux-designer")

    for agent in conditional:
        if agent.startswith("dev-") and agent not in graph:
            if agent == "dev-ux-designer" and "dev-task-planner" in graph:
                _insert_after(graph, "dev-task-planner", agent)
            elif agent == "dev-researcher" and graph:
                anchor = "dev-context-scout" if "dev-context-scout" in graph else graph[-1]
                _insert_after(graph, anchor, agent)

    graph.extend(spec["e2e_graph"])

    if spec.get("guardian"):
        graph.append("guardian")

    implementer = spec.get("implementer")
    if implementer:
        graph.append(implementer)

    qc = list(spec["qc"])

    if _has_flag(risk_flags, SECURITY_FLAGS) or profile == "new_system":
        if "e2e-security-auditor" not in qc:
            qc.append("e2e-security-auditor")

    if _has_flag(risk_flags, DEV_SECURITY_FLAGS):
        if "dev-security-auditor" not in qc and "e2e-security-auditor" not in qc:
            qc.append("dev-security-auditor")
        elif "dev-security-auditor" not in qc:
            qc.append("dev-security-auditor")

    ship_agents: list[str] = []
    ship_eligible = bool(spec.get("ship_eligible"))
    if ship_requested and ship_eligible:
        ship_agents = ["dev-pr-publisher", "dev-ci-watcher"]

    return {
        "e2e_pipeline_profile": profile,
        "dev_pipeline_profile": spec["dev_profile"],
        "pipeline_profile": profile,
        "agent_graph": graph,
        "qc_agents": qc,
        "ship_agents": ship_agents,
        "ship_eligible": ship_eligible,
        "ship_requested": ship_requested,
        "last_planner": spec.get("last_planner"),
        "skip_research": bool(spec.get("skip_research")),
        "stop_after_research": bool(spec.get("stop_after_research")),
        "implementer": implementer,
    }


def apply_to_run_dir(run_dir: Path) -> dict[str, Any]:
    intake_path = run_dir / "intake.json"
    if not intake_path.is_file():
        msg = f"intake.json not found in {run_dir}"
        raise FileNotFoundError(msg)

    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    resolved = resolve_from_intake(intake)

    run_path = run_dir / "run.json"
    run_data: dict[str, Any] = {}
    if run_path.is_file():
        run_data = json.loads(run_path.read_text(encoding="utf-8"))

    now = datetime.now(UTC).isoformat()
    run_data.update(
        {
            "orchestrator": "e2e-orchestrator",
            "orchestrator_version": "2.0",
            "e2e_pipeline_profile": resolved["e2e_pipeline_profile"],
            "dev_pipeline_profile": resolved["dev_pipeline_profile"],
            "pipeline_profile": resolved["pipeline_profile"],
            "ship_requested": resolved["ship_requested"],
            "ship_eligible": resolved["ship_eligible"],
            "agent_graph": resolved["agent_graph"],
            "qc_agents": resolved["qc_agents"],
            "ship_agents": resolved["ship_agents"],
            "last_planner": resolved["last_planner"],
            "skip_research": resolved["skip_research"],
            "stop_after_research": resolved.get("stop_after_research", False),
            "implementer": resolved["implementer"],
            "agent_graph_resolved_at": now,
            "updated_at": now,
        }
    )
    if "context_variables" not in run_data:
        run_data["context_variables"] = {}
    cv = run_data["context_variables"]
    for key in (
        "system_code",
        "layer",
        "touch_surfaces",
        "affected_modules",
        "risk_flags",
        "conditional_agents",
    ):
        if key in intake:
            cv[key] = intake[key]

    run_path.write_text(
        json.dumps(run_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    graph_path = run_dir / "agent_graph.json"
    graph_path.write_text(
        json.dumps(resolved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    intake["agent_graph"] = None
    intake_path.write_text(
        json.dumps(intake, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve agent graph from intake.json")
    parser.add_argument("--run-dir", required=True, help="Absolute path to run directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    try:
        resolved = apply_to_run_dir(run_dir)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc), "valid": False}))
        return 1

    print(json.dumps({"valid": True, **resolved}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
