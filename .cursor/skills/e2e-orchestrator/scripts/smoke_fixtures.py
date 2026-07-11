#!/usr/bin/env python3
"""Create sample step_fix artifacts and validate the full chain (dry-run)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

STEP_FIX_GRAPH = [
    "e2e-intake",
    "e2e-domain-scout",
    "e2e-scenario-analyst",
    "e2e-selector-healer",
    "e2e-implementer",
    "e2e-test-runner",
    "e2e-code-reviewer",
    "e2e-release-judge",
]

SCRIPTS_DIR = Path(__file__).resolve().parent


def write_samples(run_dir: Path) -> None:
    intake = {
        "pipeline_profile": "step_fix",
        "system_code": "hom",
        "layer": "steps",
        "touch_surfaces": ["selector"],
        "affected_modules": ["login"],
        "risk_flags": ["selector_fragile", "auth"],
        "conditional_agents": [],
        "agent_graph": [
            "e2e-domain-scout",
            "e2e-scenario-analyst",
            "e2e-selector-healer",
            "e2e-implementer",
        ],
        "summary": "HOM login 스텝 셀렉터 수정",
    }
    (run_dir / "intake.json").write_text(
        json.dumps(intake, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    (run_dir / "context-map.md").write_text(
        """## 관련 파일
- `app/systems/hom/steps/phone_login.py` — phone login selectors
- `app/systems/hom/steps/login_common.py` — shared login patterns

## 계층
- steps

## 패턴
- Prefer role/name selectors per login_common.py
""",
        encoding="utf-8",
    )

    (run_dir / "scenario-impact.md").write_text(
        """## 시스템
- hom (PC channel)

## 모듈 영향
- login module, workflow_step login

## 시나리오 문서
- `docs/scenarios/hom.md` login section if behavior changes
""",
        encoding="utf-8",
    )

    (run_dir / "healing-plan.md").write_text(
        """## 깨진 셀렉터
- `page.get_by_role("button", name="인증요청")` timeout

## 치유 전략
- Re-scan for updated button label; prefer get_by_role

## 검증
- Manual headed run on login module
""",
        encoding="utf-8",
    )

    (run_dir / "implementation-notes.md").write_text(
        """## 변경 요약
- (dry-run) no code changes — smoke test only
""",
        encoding="utf-8",
    )

    gates = {
        "passed": True,
        "profile": "step_fix",
        "gates": {},
        "ran_at": "smoke-test",
    }
    (run_dir / "gates-report.json").write_text(json.dumps(gates, indent=2) + "\n", encoding="utf-8")

    (run_dir / "review-report.json").write_text(
        json.dumps({"passed": True, "issues": []}, indent=2) + "\n", encoding="utf-8"
    )

    (run_dir / "release-verdict.json").write_text(
        json.dumps(
            {
                "passed": True,
                "failed_agent": None,
                "feedback": "",
                "invariants_checked": ["manifest_docs_sync", "otp_policy", "view_projection"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    init = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "init_run.py"),
            str(workspace),
            "HOM login 스텝 셀렉터 수정",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(init.stdout.strip())
    run_dir = Path(data["run_dir"])
    write_samples(run_dir)

    run_json_path = run_dir / "run.json"
    run_json = json.loads(run_json_path.read_text(encoding="utf-8"))
    run_json["pipeline_profile"] = "step_fix"
    run_json_path.write_text(
        json.dumps(run_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    failed: list[str] = []
    for agent in STEP_FIX_GRAPH:
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
        if not result.get("valid"):
            failed.append(f"{agent}: {result.get('errors')}")
        print(f"{agent}: {'OK' if result.get('valid') else 'FAIL'}")

    if failed:
        print(json.dumps({"smoke_passed": False, "failures": failed}, ensure_ascii=False))
        return 1

    print(json.dumps({"smoke_passed": True, "run_dir": str(run_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
