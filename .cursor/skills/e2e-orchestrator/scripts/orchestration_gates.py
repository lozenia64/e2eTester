#!/usr/bin/env python3
"""Shared orchestration gate validators (research, planning, mechanical verdict)."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

RESEARCH_SECTIONS = [
    "## 요약",
    "## 조사 질문",
    "## 핵심 발견",
    "## e2eTester 적용 권장",
    "## 불확실성 / 추가 확인 필요",
    "## 참고 URL",
]

URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")

PROFILE_LAST_PLANNER: dict[str, str] = {
    "step_fix": "e2e-selector-healer",
    "new_module": "e2e-docs-guardian",
    "new_system": "e2e-docs-guardian",
    "platform": "e2e-platform-architect",
    "healing_patch": "e2e-selector-healer",
    "docs_only": "e2e-docs-guardian",
}

PROFILES_SKIP_RESEARCH = frozenset({"docs_only"})
PROFILES_SKIP_PLANNING = frozenset({"spike", "docs_only"})


def load_gates_module(workspace: Path) -> Any:
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


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def read_intake(run_dir: Path) -> dict[str, Any]:
    data = read_json(run_dir / "intake.json")
    return data or {}


def e2e_profile(data: dict[str, Any]) -> str:
    """Resolve e2e pipeline profile from run.json or intake.json."""
    return str(data.get("e2e_pipeline_profile") or data.get("pipeline_profile") or "")


def check(
    name: str, passed: bool, message: str, *, failed_agent: str | None = None
) -> dict[str, Any]:
    item: dict[str, Any] = {"name": name, "passed": passed, "message": message}
    if failed_agent:
        item["failed_agent"] = failed_agent
    return item


def validate_research_brief(run_dir: Path, profile: str) -> dict[str, Any]:
    if profile in PROFILES_SKIP_RESEARCH:
        return {
            "passed": True,
            "skipped": True,
            "checks": [check("research_brief", True, f"skipped for profile {profile}")],
            "failed_agent": None,
        }

    path = run_dir / "research-brief.md"
    checks: list[dict[str, Any]] = []
    if not path.is_file():
        checks.append(
            check(
                "research_brief_exists",
                False,
                "missing research-brief.md",
                failed_agent="e2e-researcher",
            )
        )
        return {"passed": False, "checks": checks, "failed_agent": "e2e-researcher"}

    text = path.read_text(encoding="utf-8")
    for section in RESEARCH_SECTIONS:
        checks.append(
            check(
                f"section_{section}",
                section in text,
                f"missing section: {section}",
                failed_agent="e2e-researcher",
            )
        )

    urls = URL_PATTERN.findall(text)
    checks.append(
        check(
            "url_count",
            len(urls) >= 2,
            f"expected >= 2 URLs, found {len(urls)}",
            failed_agent="e2e-researcher",
        )
    )

    findings_start = text.find("## 핵심 발견")
    findings_len = 0
    if findings_start >= 0:
        rest = text[findings_start + len("## 핵심 발견") :]
        next_heading = rest.find("\n## ")
        block = rest[:next_heading] if next_heading >= 0 else rest
        findings_len = len(block.strip())
    checks.append(
        check(
            "findings_length",
            findings_len >= 200,
            f"## 핵심 발견 must be >= 200 chars (got {findings_len})",
            failed_agent="e2e-researcher",
        )
    )

    passed = all(c["passed"] for c in checks)
    return {
        "passed": passed,
        "checks": checks,
        "failed_agent": None if passed else "e2e-researcher",
    }


def _manifest_module_ids(workspace: Path, system_code: str | None) -> set[str]:
    if not system_code:
        return set()
    manifest_path = workspace / "app" / "systems" / system_code / "manifest.yaml"
    if not manifest_path.is_file():
        return set()
    text = manifest_path.read_text(encoding="utf-8")
    return set(re.findall(r"module_id:\s*(\S+)", text))


def validate_planning_gate(run_dir: Path, workspace: Path, profile: str) -> dict[str, Any]:
    if profile in PROFILES_SKIP_PLANNING:
        return {
            "passed": True,
            "skipped": True,
            "checks": [check("planning_gate", True, f"skipped for profile {profile}")],
            "failed_agent": None,
        }

    intake = read_intake(run_dir)
    system_code = intake.get("system_code")
    if isinstance(system_code, str) and system_code.lower() == "null":
        system_code = None
    failed_agent = PROFILE_LAST_PLANNER.get(profile, "e2e-manifest-planner")
    checks: list[dict[str, Any]] = []
    gates_mod = load_gates_module(workspace)

    if profile not in PROFILES_SKIP_RESEARCH:
        research = validate_research_brief(run_dir, profile)
        for item in research.get("checks", []):
            checks.append(item)

    context_path = run_dir / "context-map.md"
    if context_path.is_file():
        text = context_path.read_text(encoding="utf-8")
        paths = gates_mod.extract_paths_from_markdown(text)
        existing = [p for p in paths if (workspace / p).is_file()]
        checks.append(
            check(
                "context_map_paths",
                len(existing) >= 3,
                f"expected >= 3 existing repo paths, found {len(existing)}",
                failed_agent="e2e-domain-scout",
            )
        )
    elif profile != "healing_patch":
        checks.append(
            check(
                "context_map_exists",
                False,
                "missing context-map.md",
                failed_agent="e2e-domain-scout",
            )
        )

    scenario_path = run_dir / "scenario-impact.md"
    if scenario_path.is_file() and system_code:
        text = scenario_path.read_text(encoding="utf-8")
        manifest_ids = _manifest_module_ids(workspace, system_code)
        overlap = {mid for mid in manifest_ids if mid.lower() in text.lower()}
        if manifest_ids:
            checks.append(
                check(
                    "scenario_module_ids",
                    bool(overlap),
                    "scenario-impact should mention at least one manifest module_id",
                    failed_agent="e2e-scenario-analyst",
                )
            )
    elif system_code and profile not in {"platform"}:
        checks.append(
            check(
                "scenario_impact_exists",
                scenario_path.is_file(),
                "missing scenario-impact.md",
                failed_agent="e2e-scenario-analyst",
            )
        )

    manifest_plan = run_dir / "manifest-plan.yaml"
    if manifest_plan.is_file():
        text = manifest_plan.read_text(encoding="utf-8")
        checks.append(
            check(
                "manifest_plan_action",
                "action:" in text and ("add" in text or "modify" in text or "reorder" in text),
                "manifest-plan.yaml needs action add|modify|reorder",
                failed_agent="e2e-manifest-planner",
            )
        )
        checks.append(
            check(
                "manifest_plan_workflow_step",
                "workflow_step:" in text,
                "manifest-plan.yaml needs workflow_step",
                failed_agent="e2e-manifest-planner",
            )
        )

    arch_path = run_dir / "architecture-delta.md"
    if profile in {"platform", "new_system"}:
        if arch_path.is_file():
            text = arch_path.read_text(encoding="utf-8")
            boundary = ""
            if "## 경계" in text:
                start = text.find("## 경계")
                rest = text[start:]
                nxt = rest.find("\n## ", 1)
                boundary = rest[:nxt] if nxt >= 0 else rest
            has_keywords = any(k in boundary.lower() for k in ("port", "aggregate", "event"))
            checks.append(
                check(
                    "architecture_boundary",
                    has_keywords,
                    "## 경계 must mention port/aggregate/event",
                    failed_agent="e2e-platform-architect",
                )
            )
        else:
            checks.append(
                check(
                    "architecture_delta_exists",
                    False,
                    "missing architecture-delta.md",
                    failed_agent="e2e-platform-architect",
                )
            )

    docs_path = run_dir / "docs-checklist.md"
    if docs_path.is_file():
        text = docs_path.read_text(encoding="utf-8")
        guard_section = ""
        if "## 가드 항목" in text:
            start = text.find("## 가드 항목")
            rest = text[start:]
            nxt = rest.find("\n## ", 1)
            guard_section = rest[:nxt] if nxt >= 0 else rest
        checks.append(
            check(
                "docs_guard_items",
                len(guard_section.strip()) > 20,
                "## 가드 항목 must list docs consistency risks",
                failed_agent="e2e-docs-guardian",
            )
        )
    elif profile in {"new_module", "new_system"}:
        checks.append(
            check(
                "docs_checklist_exists",
                False,
                "missing docs-checklist.md",
                failed_agent="e2e-docs-guardian",
            )
        )

    passed = all(c["passed"] for c in checks) if checks else True
    resolved_failed = None
    if not passed:
        for item in checks:
            if not item["passed"]:
                resolved_failed = item.get("failed_agent", failed_agent)
                break
    return {"passed": passed, "checks": checks, "failed_agent": resolved_failed}


def report_passed(path: Path) -> bool | None:
    data = read_json(path)
    if data is None:
        return None
    return bool(data.get("passed"))


def compute_mechanical_verdict(run_dir: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    reports = {
        "research-gate-report.json": "research_gate",
        "planning-gate-report.json": "planning_gate",
        "preflight-report.json": "preflight",
        "gates-report.json": "full_ci",
        "review-report.json": "code_review",
        "security-report.json": "security_review",
    }

    intake = read_intake(run_dir)
    profile = e2e_profile(intake)

    for filename, name in reports.items():
        path = run_dir / filename
        if not path.is_file():
            if name == "security_review":
                continue
            if name == "research_gate" and profile in PROFILES_SKIP_RESEARCH:
                checks.append(check(name, True, "skipped"))
                continue
            if name == "planning_gate" and profile in PROFILES_SKIP_PLANNING:
                checks.append(check(name, True, "skipped"))
                continue
            if name == "code_review":
                checks.append(
                    check(name, False, f"missing {filename}", failed_agent="e2e-code-reviewer")
                )
                continue
            checks.append(check(name, False, f"missing {filename}"))
            continue

        data = read_json(path) or {}
        if data.get("skipped"):
            checks.append(check(name, True, "skipped"))
            continue
        passed = bool(data.get("passed"))
        agent_hint = {
            "preflight": "e2e-implementer",
            "full_ci": "e2e-implementer",
            "planning_gate": PROFILE_LAST_PLANNER.get(profile, "e2e-manifest-planner"),
            "research_gate": "e2e-researcher",
            "code_review": "e2e-code-reviewer",
            "security_review": "e2e-security-auditor",
        }.get(name)
        checks.append(
            check(
                name,
                passed,
                "passed" if passed else "failed",
                failed_agent=agent_hint if not passed else None,
            )
        )

    passed = all(c["passed"] for c in checks)
    failed_agent = None
    if not passed:
        for item in checks:
            if not item["passed"]:
                failed_agent = item.get("failed_agent")
                break

    return {"passed": passed, "checks": checks, "failed_agent": failed_agent}
