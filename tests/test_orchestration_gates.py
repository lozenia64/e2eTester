"""Unit tests for e2e-orchestrator verification gate validators."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".cursor" / "skills" / "e2e-orchestrator" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from orchestration_gates import (  # noqa: E402
    compute_mechanical_verdict,
    validate_planning_gate,
    validate_research_brief,
)


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"workspace": str(ROOT), "pipeline_profile": "step_fix"}),
        encoding="utf-8",
    )
    (run_dir / "intake.json").write_text(
        json.dumps(
            {
                "pipeline_profile": "step_fix",
                "system_code": "hom",
                "layer": "steps",
                "touch_surfaces": ["selector"],
                "risk_flags": [],
                "conditional_agents": [],
                "agent_graph": ["e2e-domain-scout"],
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def _sample_research_brief() -> str:
    return """## 요약
Playwright role-based locators are preferred.

## 조사 질문
- What locator strategy is most resilient?

## 핵심 발견
Official Playwright docs recommend get_by_role and get_by_test_id over CSS/XPath for stability.
See https://playwright.dev/docs/locators and https://playwright.dev/docs/best-practices for details.
Using semantic locators reduces breakage when CSS classes change during site updates.

## e2eTester 적용 권장
Prefer role/name in hom login steps.

## 불확실성 / 추가 확인 필요
None for this test.

## 참고 URL
- https://playwright.dev/docs/locators
- https://playwright.dev/docs/best-practices
"""


def test_validate_research_brief_passes(run_dir: Path) -> None:
    (run_dir / "research-brief.md").write_text(_sample_research_brief(), encoding="utf-8")
    result = validate_research_brief(run_dir, "step_fix")
    assert result["passed"] is True


def test_validate_research_brief_fails_without_urls(run_dir: Path) -> None:
    text = _sample_research_brief().replace("https://playwright.dev/docs/locators", "")
    text = text.replace("https://playwright.dev/docs/best-practices", "")
    (run_dir / "research-brief.md").write_text(text, encoding="utf-8")
    result = validate_research_brief(run_dir, "step_fix")
    assert result["passed"] is False


def test_validate_research_brief_skipped_for_docs_only(run_dir: Path) -> None:
    result = validate_research_brief(run_dir, "docs_only")
    assert result["passed"] is True
    assert result.get("skipped") is True


def test_validate_planning_gate_with_context_map(run_dir: Path) -> None:
    (run_dir / "research-brief.md").write_text(_sample_research_brief(), encoding="utf-8")
    (run_dir / "context-map.md").write_text(
        """## 관련 파일
- `app/systems/hom/manifest.yaml` — module manifest
- `app/systems/hom/executor.py` — workflow executor
- `docs/scenarios/hom.md` — scenario SSOT

## 계층
steps

## 패턴
registry
""",
        encoding="utf-8",
    )
    (run_dir / "scenario-impact.md").write_text(
        """## 시스템
hom

## 모듈 영향
- hom.login module

## 시나리오 문서
docs/scenarios/hom.md
""",
        encoding="utf-8",
    )
    (run_dir / "healing-plan.md").write_text(
        """## 깨진 셀렉터
x

## 치유 전략
y

## 검증
z
""",
        encoding="utf-8",
    )
    result = validate_planning_gate(run_dir, ROOT, "step_fix")
    assert result["passed"] is True


def test_compute_mechanical_verdict_all_pass(run_dir: Path) -> None:
    for name in (
        "research-gate-report.json",
        "planning-gate-report.json",
        "preflight-report.json",
        "gates-report.json",
        "review-report.json",
    ):
        (run_dir / name).write_text(json.dumps({"passed": True}) + "\n", encoding="utf-8")
    result = compute_mechanical_verdict(run_dir)
    assert result["passed"] is True


def test_compute_mechanical_verdict_preflight_fail(run_dir: Path) -> None:
    for name, passed in (
        ("research-gate-report.json", True),
        ("planning-gate-report.json", True),
        ("preflight-report.json", False),
        ("gates-report.json", True),
        ("review-report.json", True),
    ):
        (run_dir / name).write_text(json.dumps({"passed": passed}) + "\n", encoding="utf-8")
    result = compute_mechanical_verdict(run_dir)
    assert result["passed"] is False
    assert result["failed_agent"] == "e2e-implementer"


def test_gates_resolve_changed_files() -> None:
    from scripts.ci.gates import filter_python_files, resolve_changed_files

    changed = resolve_changed_files(ROOT)
    assert isinstance(changed, list)
    py_only = filter_python_files(changed)
    assert all(p.endswith(".py") for p in py_only)
