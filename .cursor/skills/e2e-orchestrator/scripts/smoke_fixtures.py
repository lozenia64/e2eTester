#!/usr/bin/env python3
"""Create sample artifacts and validate orchestration chains (dry-run)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

STEP_FIX_AGENTS = [
    "e2e-intake",
    "e2e-researcher",
    "dev-context-scout",
    "e2e-domain-scout",
    "e2e-scenario-analyst",
    "e2e-selector-healer",
    "guardian",
    "e2e-implementer",
    "e2e-test-runner",
    "e2e-code-reviewer",
    "dev-build-integrator",
    "e2e-release-judge",
]

PLATFORM_AGENTS = [
    "e2e-intake",
    "e2e-researcher",
    "dev-spec-writer",
    "dev-context-scout",
    "dev-architect",
    "dev-task-planner",
    "e2e-domain-scout",
    "e2e-platform-architect",
    "guardian",
    "e2e-implementer",
    "e2e-test-runner",
    "e2e-code-reviewer",
    "dev-build-integrator",
    "e2e-release-judge",
]


def _sample_research_brief() -> str:
    return """## 요약
Playwright role-based locators preferred for HOM login fix.

## 조사 질문
- Best locator strategy for auth buttons?

## 핵심 발견
Playwright recommends get_by_role over brittle CSS selectors.
See https://playwright.dev/docs/locators and https://playwright.dev/docs/best-practices.
Role-based locators survive label and class changes better than XPath.

## e2eTester 적용 권장
Update hom login step to use get_by_role for 인증요청 button.

## 불확실성 / 추가 확인 필요
Live site label must be verified manually.

## 참고 URL
- https://playwright.dev/docs/locators
- https://playwright.dev/docs/best-practices
"""


def _unified_intake(profile: str, **extra: object) -> dict:
    base = {
        "e2e_pipeline_profile": profile,
        "pipeline_profile": profile,
        "system_code": "hom" if profile == "step_fix" else None,
        "layer": "steps" if profile == "step_fix" else "web",
        "touch_surfaces": ["selector"] if profile == "step_fix" else ["api", "web"],
        "affected_modules": ["hom.login"] if profile == "step_fix" else [],
        "risk_flags": ["selector_fragile", "auth"] if profile == "step_fix" else ["user_facing"],
        "conditional_agents": [],
        "dev_path": "standard",
        "ship_requested": False,
        "agent_graph": None,
        "summary": f"smoke {profile}",
    }
    base.update(extra)
    return base


def write_step_fix_samples(run_dir: Path) -> None:
    (run_dir / "intake.json").write_text(
        json.dumps(_unified_intake("step_fix"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "research-brief.md").write_text(_sample_research_brief(), encoding="utf-8")
    (run_dir / "context-map.md").write_text(
        """## 관련 파일
- `app/systems/hom/manifest.yaml` — module manifest

## 패턴
- Prefer role selectors

## 계층
- steps
""",
        encoding="utf-8",
    )
    (run_dir / "scenario-impact.md").write_text(
        """## 시스템
- hom

## 모듈 영향
- hom.login

## 시나리오 문서
- docs/scenarios/hom.md
""",
        encoding="utf-8",
    )
    (run_dir / "healing-plan.md").write_text(
        """## 깨진 셀렉터
- button timeout

## 치유 전략
- get_by_role

## 검증
- manual run
""",
        encoding="utf-8",
    )
    (run_dir / "review.md").write_text("APPROVED\n", encoding="utf-8")
    (run_dir / "context.md").write_text("# context\n", encoding="utf-8")
    (run_dir / "implementation-notes.md").write_text(
        "## 변경 요약\n- smoke dry-run\n", encoding="utf-8"
    )
    _write_gate_reports(run_dir, "step_fix")


def write_platform_samples(run_dir: Path) -> None:
    (run_dir / "intake.json").write_text(
        json.dumps(_unified_intake("platform"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "research-brief.md").write_text(_sample_research_brief(), encoding="utf-8")
    (run_dir / "spec.md").write_text(
        """## 목표
Dashboard redesign

## 범위
daily dashboard only

## 수용 기준
- matrix view

## 비범위
- admin
""",
        encoding="utf-8",
    )
    (run_dir / "context-map.md").write_text(
        """## 관련 파일
- app/web/templates/dashboard.html

## 계층
- web

## 패턴
- HTMX partials
""",
        encoding="utf-8",
    )
    (run_dir / "architecture.md").write_text(
        """## 개요
UI refactor

## 컴포넌트
dashboard

## 데이터 흐름
API to template
""",
        encoding="utf-8",
    )
    (run_dir / "tasks.yaml").write_text(
        "tasks:\n  - id: t1\n    title: matrix\n    deps: []\n  - id: t2\n",
        encoding="utf-8",
    )
    (run_dir / "architecture-delta.md").write_text(
        """## 개요
Dashboard zones

## 경계
web only

## 변경 범위
templates + static
""",
        encoding="utf-8",
    )
    (run_dir / "review.md").write_text("APPROVED\n", encoding="utf-8")
    (run_dir / "context.md").write_text("# context\n", encoding="utf-8")
    (run_dir / "implementation-notes.md").write_text(
        "## 변경 요약\n- smoke dry-run\n", encoding="utf-8"
    )
    _write_gate_reports(run_dir, "platform")


def _write_gate_reports(run_dir: Path, profile: str) -> None:
    reports = {
        "research-gate-report.json": {"passed": True},
        "planning-gate-report.json": {"passed": True},
        "preflight-report.json": {"passed": True, "skipped": True},
        "gates-report.json": {"passed": True, "profile": profile, "gates": {}},
        "mechanical-verdict.json": {"passed": True, "checks": []},
        "review-report.json": {"passed": True, "issues": []},
        "build-report.json": {"passed": True, "commands": []},
        "release-verdict.json": {
            "passed": True,
            "failed_agent": None,
            "feedback": "",
            "invariants_checked": ["manifest_docs_sync"],
        },
    }
    for name, payload in reports.items():
        (run_dir / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run_smoke(workspace: Path, profile: str, writers: dict, agents: list[str]) -> int:
    init = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "init_run.py"),
            str(workspace),
            f"smoke {profile}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(init.stdout.strip())
    run_dir = Path(data["run_dir"])
    writers[profile](run_dir)

    resolve = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "resolve_graph.py"), "--run-dir", str(run_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if resolve.returncode != 0:
        print(resolve.stdout + resolve.stderr)
        return 1

    failed: list[str] = []
    for agent in agents:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "validate_artifacts.py"),
                "--run-dir",
                str(run_dir),
                "--agent",
                agent,
            ],
            capture_output=True,
            text=True,
        )
        result = json.loads(proc.stdout.strip())
        ok = result.get("valid")
        print(f"[{profile}] {agent}: {'OK' if ok else 'FAIL'}")
        if not ok:
            failed.append(f"{agent}: {result.get('errors')}")

    if failed:
        print(json.dumps({"smoke_passed": False, "profile": profile, "failures": failed}))
        return 1
    print(json.dumps({"smoke_passed": True, "profile": profile, "run_dir": str(run_dir)}))
    return 0


def main() -> int:
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    writers = {"step_fix": write_step_fix_samples, "platform": write_platform_samples}
    agents_map = {"step_fix": STEP_FIX_AGENTS, "platform": PLATFORM_AGENTS}
    rc = 0
    for profile in ("step_fix", "platform"):
        rc |= _run_smoke(workspace, profile, writers, agents_map[profile])
    return rc


if __name__ == "__main__":
    sys.exit(main())
