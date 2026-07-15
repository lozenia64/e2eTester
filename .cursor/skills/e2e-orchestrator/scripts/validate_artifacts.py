#!/usr/bin/env python3
"""Validate e2e-orchestrator agent artifacts (unified router)."""

from __future__ import annotations

import argparse
import json
import subprocess
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

SYSTEM_CODES = {"hom", "mhm", "fp", "hrp", "hwtc", "chbot"}

RESEARCH_SECTIONS = [
    "## 요약",
    "## 조사 질문",
    "## 핵심 발견",
    "## e2eTester 적용 권장",
    "## 불확실성 / 추가 확인 필요",
    "## 참고 URL",
]

GLOBAL_AGENTS = frozenset({"guardian", "triage", "debugger"})

DEV_VALIDATE_SCRIPT = (
    Path.home() / ".cursor" / "skills" / "dev-orchestrator" / "scripts" / "validate_artifacts.py"
)

AGENT_ARTIFACTS: dict[str, dict] = {
    "e2e-intake": {
        "file": "intake.json",
        "required": [
            "e2e_pipeline_profile",
            "system_code",
            "layer",
            "touch_surfaces",
            "risk_flags",
            "conditional_agents",
        ],
    },
    "e2e-researcher": {
        "file": "research-brief.md",
        "sections": RESEARCH_SECTIONS,
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
        "also_requires": ["preflight-report.json"],
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
        "requires_mechanical": True,
    },
    "guardian": {
        "files": ["review.md", "context.md"],
    },
    "triage": {
        "skip_artifacts": True,
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
    if not isinstance(data, dict):
        return [f"JSON root must be an object, got {type(data).__name__}"]
    for key in required:
        if key not in data:
            errors.append(f"missing field: {key}")
    if if_false and data.get("passed") is False:
        for key in if_false:
            if key not in data:
                errors.append(f"missing field (passed=false): {key}")
    return errors


def normalize_system_code(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value in SYSTEM_CODES:
            return value
        if value.lower() == "null":
            return None
    return "__invalid__"


def validate_intake(data: dict) -> list[str]:
    errors: list[str] = []
    profile = data.get("e2e_pipeline_profile") or data.get("pipeline_profile")
    if profile not in PIPELINE_PROFILES:
        errors.append(f"invalid e2e_pipeline_profile: {profile}")
    system_code = normalize_system_code(data.get("system_code"))
    if system_code == "__invalid__":
        errors.append(f"invalid system_code: {data.get('system_code')}")
    graph = data.get("agent_graph")
    if graph is not None:
        if not isinstance(graph, list):
            errors.append(
                "agent_graph must be null or a list (prefer null; resolve_graph builds it)"
            )
        elif len(graph) > 0:
            errors.append("agent_graph must be null — use resolve_graph.py")
    if "dev_path" in data and data["dev_path"] not in ("full", "standard", "minimal"):
        errors.append(f"invalid dev_path: {data.get('dev_path')}")
    return errors


def validate_guardian(run_dir: Path) -> list[str]:
    errors: list[str] = []
    review = run_dir / "review.md"
    context = run_dir / "context.md"
    if not review.is_file():
        errors.append("missing file: review.md")
    if not context.is_file():
        errors.append("missing file: context.md")
    if review.is_file():
        text = review.read_text(encoding="utf-8")
        upper = text.upper()
        if "APPROVED" not in upper and "REJECTED" not in upper:
            errors.append("review.md must contain APPROVED or REJECTED")
    return errors


def validate_preflight(run_dir: Path) -> list[str]:
    path = run_dir / "preflight-report.json"
    errors = validate_json(path, ["passed"])
    if errors:
        return errors
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("skipped"):
        return []
    if data.get("passed") is not True:
        errors.append("preflight-report.json passed must be true")
    return errors


def validate_mechanical_prerequisite(run_dir: Path) -> list[str]:
    path = run_dir / "mechanical-verdict.json"
    if not path.is_file():
        return [
            "missing mechanical-verdict.json — run run_mechanical_verdict.py before release judge"
        ]
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("passed"):
        return ["mechanical-verdict.json passed must be true before release judge"]
    return []


def delegate_dev_validation(run_dir: Path, agent: str) -> dict:
    if not DEV_VALIDATE_SCRIPT.is_file():
        return {"valid": False, "errors": [f"dev validator not found: {DEV_VALIDATE_SCRIPT}"]}
    proc = subprocess.run(
        [
            sys.executable,
            str(DEV_VALIDATE_SCRIPT),
            "--run-dir",
            str(run_dir),
            "--agent",
            agent,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "valid": False,
            "errors": [proc.stdout or proc.stderr or "dev validation failed"],
        }


def validate_e2e_agent(run_dir: Path, agent: str, spec: dict) -> list[str]:
    errors: list[str] = []
    filename = spec.get("file", "")

    if spec.get("skip_artifacts"):
        return []

    if agent == "guardian" or "files" in spec:
        return validate_guardian(run_dir)

    if filename.endswith(".json"):
        path = run_dir / filename
        errors = validate_json(path, spec.get("required", []), spec.get("if_false"))
        if agent == "e2e-intake" and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
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

    if agent == "e2e-implementer":
        errors.extend(validate_preflight(run_dir))

    if spec.get("requires_mechanical"):
        errors.extend(validate_mechanical_prerequisite(run_dir))

    return errors


def validate_agent(run_dir: Path, agent: str) -> dict:
    if agent.startswith("dev-"):
        return delegate_dev_validation(run_dir, agent)

    if agent in GLOBAL_AGENTS:
        spec = AGENT_ARTIFACTS.get(agent, {})
        errors = validate_e2e_agent(run_dir, agent, spec) if spec else []
        return {"valid": len(errors) == 0, "agent": agent, "errors": errors}

    if agent not in AGENT_ARTIFACTS:
        return {"valid": False, "agent": agent, "errors": [f"unknown agent: {agent}"]}

    spec = AGENT_ARTIFACTS[agent]
    errors = validate_e2e_agent(run_dir, agent, spec)
    return {"valid": len(errors) == 0, "agent": agent, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Absolute path to run directory")
    parser.add_argument(
        "--agent", required=True, help="Agent id (e.g. e2e-intake, dev-spec-writer)"
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    result = validate_agent(run_dir, args.agent)
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
