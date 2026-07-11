#!/usr/bin/env python3
"""Validate e2e-orchestrator agent artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PIPELINE_PROFILES = [
    "step_fix",
    "new_module",
    "new_system",
    "platform",
    "healing_patch",
    "docs_only",
    "spike",
]

SYSTEM_CODES = ["hom", "mhm", "fp", "hrp", "hwtc", "chbot", None]

AGENT_ARTIFACTS: dict[str, dict] = {
    "e2e-intake": {
        "file": "intake.json",
        "required": [
            "pipeline_profile",
            "system_code",
            "layer",
            "touch_surfaces",
            "risk_flags",
            "conditional_agents",
            "agent_graph",
        ],
    },
    "e2e-domain-scout": {
        "file": "context-map.md",
        "sections": ["## 관련 파일", "## 계층", "## 패턴"],
    },
    "e2e-scenario-analyst": {
        "file": "scenario-impact.md",
        "sections": ["## 시스템", "## 모듈 영향", "## 시나리오 문서"],
    },
    "e2e-manifest-planner": {
        "file": "manifest-plan.yaml",
        "min_lines": 5,
    },
    "e2e-platform-architect": {
        "file": "architecture-delta.md",
        "sections": ["## 개요", "## 경계", "## 변경 범위"],
    },
    "e2e-selector-healer": {
        "file": "healing-plan.md",
        "sections": ["## 깨진 셀렉터", "## 치유 전략", "## 검증"],
    },
    "e2e-docs-guardian": {
        "file": "docs-checklist.md",
        "sections": ["## SSOT", "## 수정 대상", "## 가드 항목"],
    },
    "e2e-implementer": {
        "file": "implementation-notes.md",
        "sections": ["## 변경 요약"],
    },
    "e2e-docs-writer": {
        "file": "implementation-notes.md",
        "sections": ["## 문서 변경"],
    },
    "e2e-test-runner": {
        "file": "gates-report.json",
        "required": ["passed", "gates"],
    },
    "e2e-code-reviewer": {
        "file": "review-report.json",
        "required": ["issues", "passed"],
    },
    "e2e-security-auditor": {
        "file": "security-report.json",
        "required": ["issues", "passed"],
    },
    "e2e-release-judge": {
        "file": "release-verdict.json",
        "required": ["passed"],
        "if_false": ["failed_agent", "feedback"],
    },
}


def validate_markdown(path: Path, sections: list[str]) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing file: {path.name}"]
    text = path.read_text(encoding="utf-8")
    for section in sections:
        if section not in text:
            errors.append(f"missing section: {section}")
    return errors


def validate_json(path: Path, required: list[str], if_false: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing file: {path.name}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"]
    for key in required:
        if key not in data:
            errors.append(f"missing field: {key}")
    if if_false and data.get("passed") is False:
        for key in if_false:
            if key not in data:
                errors.append(f"missing field (passed=false): {key}")
    return errors


def validate_intake(data: dict) -> list[str]:
    errors: list[str] = []
    profile = data.get("pipeline_profile")
    if profile not in PIPELINE_PROFILES:
        errors.append(f"invalid pipeline_profile: {profile}")
    system_code = data.get("system_code")
    if system_code not in SYSTEM_CODES:
        errors.append(f"invalid system_code: {system_code}")
    graph = data.get("agent_graph")
    if not isinstance(graph, list) or len(graph) == 0:
        errors.append("agent_graph must be a non-empty list")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Absolute path to run directory")
    parser.add_argument("--agent", required=True, help="Agent skill name (e.g. e2e-intake)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    agent = args.agent
    if agent not in AGENT_ARTIFACTS:
        print(json.dumps({"valid": False, "errors": [f"unknown agent: {agent}"]}))
        return 1

    spec = AGENT_ARTIFACTS[agent]
    errors: list[str] = []
    filename = spec.get("file", "")

    if filename.endswith(".json"):
        path = run_dir / filename
        errors = validate_json(path, spec.get("required", []), spec.get("if_false"))
        if agent == "e2e-intake" and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                errors.extend(validate_intake(data))
            except json.JSONDecodeError:
                pass
    elif filename.endswith(".md"):
        path = run_dir / filename
        errors = validate_markdown(path, spec.get("sections", []))
    elif filename.endswith(".yaml"):
        path = run_dir / filename
        if not path.exists():
            errors = [f"missing file: {filename}"]
        elif len(path.read_text(encoding="utf-8").splitlines()) < spec.get("min_lines", 5):
            errors = [f"{filename} too short"]

    result = {"valid": len(errors) == 0, "agent": agent, "errors": errors}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
