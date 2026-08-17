#!/usr/bin/env python3
"""변경 파일 → 실행할 CI 게이트 목록 (GitHub Actions matrix 입력).

ci.yml 이 게이트 목록을 인라인으로 들고 있으면 gates.py 와 표류한다(2026-08-17:
게이트 4개가 CI 에서 한 번도 실행되지 않고 있었다). 판정을 여기로 모아
단위 테스트로 덮고, ci.yml 은 이 스크립트의 출력만 소비한다.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.platform.stdio_utf8 import configure_stdio_utf8  # noqa: E402
from scripts.ci.gates import (  # noqa: E402
    CI_STANDARD_GATES,
    DOCS_ONLY_PATHS,
    PROFILE_GATES,
    SECURITY_GATES,
    SECURITY_PATHS,
)

# gates.py 의 PROFILE_GATES["docs_only"] 를 그대로 참조한다 — 여기서 리스트를
# 다시 타이핑하면 이 작업 전체가 없애려는 것과 똑같은 표류(drift)가 재발한다.
DOCS_ONLY_GATES: list[str] = PROFILE_GATES["docs_only"]


def matches_any(path: str, patterns: list[str]) -> bool:
    """경로가 글롭 중 하나에 매칭되는가 (`**` 는 임의 깊이)."""
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        # fnmatch 는 `**` 를 `*` 와 동일하게 다루므로 디렉터리 접두 매칭을 보강한다.
        if pattern.endswith("/**") and normalized.startswith(pattern[:-2]):
            return True
    return False


def _dedup(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def resolve_ci_gates(changed: list[str], *, event_name: str) -> list[str]:
    """실행할 게이트 목록. 절대 빈 리스트를 반환하지 않는다."""
    if event_name == "schedule":
        return _dedup([*CI_STANDARD_GATES, *SECURITY_GATES])

    if changed and all(matches_any(p, DOCS_ONLY_PATHS) for p in changed):
        return _dedup(DOCS_ONLY_GATES)

    gates = list(CI_STANDARD_GATES)
    if any(matches_any(p, SECURITY_PATHS) for p in changed):
        gates.extend(SECURITY_GATES)
    return _dedup(gates) or list(DOCS_ONLY_GATES)


def _scope_of(changed: list[str], gates: list[str]) -> str:
    if set(gates) == set(DOCS_ONLY_GATES):
        return "docs_only"
    if any(name in gates for name in SECURITY_GATES):
        return "security"
    return "code"


def resolve_changed_vs_base(workspace: Path, base_ref: str) -> list[str]:
    """base_ref 대비 변경된 repo-상대 경로. 판정 불가 시 빈 리스트(= 전체 실행)."""
    if not base_ref:
        return []
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    configure_stdio_utf8()
    parser = argparse.ArgumentParser(description="CI 게이트 목록 계획")
    parser.add_argument("--base-ref", default="", help="비교 기준 ref (PR base 등)")
    parser.add_argument("--event-name", default="pull_request", help="GitHub 이벤트 이름")
    parser.add_argument("--github-output", default=None, help="$GITHUB_OUTPUT 경로")
    args = parser.parse_args()

    changed = resolve_changed_vs_base(ROOT, args.base_ref)
    gates = resolve_ci_gates(changed, event_name=args.event_name)
    scope = _scope_of(changed, gates)

    lines = [f"gates={json.dumps(gates, ensure_ascii=False)}", f"scope={scope}"]
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    print(f"event={args.event_name} base={args.base_ref or '(none)'} scope={scope}")
    print(f"changed={len(changed)} files")
    for path in changed[:50]:
        print(f"  {path}")
    print(f"gates={gates}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
