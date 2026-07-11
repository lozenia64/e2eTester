#!/usr/bin/env python3
"""아키텍처 정책 게이트 (policy-as-code).

규칙:
  AG-001  app/ 내 list_runs() 직접 호출 금지 (RunHistoryQueryPort 사용)
  AG-002  app/orchestrator/ 에서 playwright import 금지
  AG-003  app/domain/ 에 I/O·async 런타임 import 금지 (순수 도메인 유지)
  AG-004  app/orchestrator/ 에서 list_all_runs( / list_runs_since( 금지
  AG-005  app/ 에서 aggregate .snapshot / .suite 접근 금지 (domain/storage/tests 제외)
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
ORCHESTRATOR_DIR = APP_DIR / "orchestrator"
DOMAIN_DIR = APP_DIR / "domain"
AGGREGATE_ALLOWED_PREFIXES = (
    "app/domain/",
    "app/storage/",
    "tests/",
)

# AG-001: 포트 정의·이력 조회 어댑터·하위 호환 인메모리 구현은 허용
LIST_RUNS_ALLOWED_SUFFIXES = (
    "storage/ports.py",
    "storage/run_repository.py",
    "storage/sqlite_run_repository.py",
    "storage/sqlite_run_history_query.py",
    "storage/composite_run_repository.py",
    "api/routes_runs.py",
    "api/routes_admin.py",
)
LIST_RUNS_PATTERN = re.compile(r"\.list_runs\s*\(")

# AG-003: domain 레이어 금지 import 목록 (denylist — I/O·async 런타임 모듈 차단)
DOMAIN_FORBIDDEN_IMPORTS = (
    "asyncio",
    "sqlite3",
    "playwright",
    "httpx",
    "requests",
    "aiohttp",
    "subprocess",
    "socket",
    "redis",
)


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def check_ag001_list_runs() -> list[str]:
    violations: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        rel = _rel(path)
        if any(rel.endswith(suffix) for suffix in LIST_RUNS_ALLOWED_SUFFIXES):
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if LIST_RUNS_PATTERN.search(line):
                violations.append(f"{rel}:{line_no}: {line.strip()}")
    return violations


def check_ag002_orchestrator_no_playwright() -> list[str]:
    violations: list[str] = []
    if not ORCHESTRATOR_DIR.is_dir():
        return violations
    for path in ORCHESTRATOR_DIR.rglob("*.py"):
        rel = _rel(path)
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"\b(from|import)\s+playwright\b", line):
                violations.append(f"{rel}:{line_no}: {stripped}")
    return violations


def check_ag003_domain_purity() -> list[str]:
    violations: list[str] = []
    if not DOMAIN_DIR.is_dir():
        return violations
    import_re = re.compile(r"^\s*(?:from|import)\s+([\w.]+)")
    for path in DOMAIN_DIR.rglob("*.py"):
        rel = _rel(path)
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = import_re.match(line)
            if not match:
                continue
            module = match.group(1).split(".")[0]
            if module in DOMAIN_FORBIDDEN_IMPORTS:
                violations.append(f"{rel}:{line_no}: {line.strip()}")
    return violations


LIST_ALL_RUNS_PATTERN = re.compile(r"\.list_all_runs\s*\(")
LIST_RUNS_SINCE_PATTERN = re.compile(r"\.list_runs_since\s*\(")
AGGREGATE_SNAPSHOT_PATTERN = re.compile(r"\.snapshot\b")
AGGREGATE_SUITE_PATTERN = re.compile(r"aggregate\.suite\b")


def check_ag004_orchestrator_history_scan() -> list[str]:
    violations: list[str] = []
    if not ORCHESTRATOR_DIR.is_dir():
        return violations
    for path in ORCHESTRATOR_DIR.rglob("*.py"):
        rel = _rel(path)
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if LIST_ALL_RUNS_PATTERN.search(line) or LIST_RUNS_SINCE_PATTERN.search(line):
                violations.append(f"{rel}:{line_no}: {stripped}")
    return violations


def check_ag005_aggregate_encapsulation() -> list[str]:
    violations: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        rel = _rel(path)
        if any(rel.startswith(prefix) for prefix in AGGREGATE_ALLOWED_PREFIXES):
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if AGGREGATE_SNAPSHOT_PATTERN.search(line) or AGGREGATE_SUITE_PATTERN.search(line):
                violations.append(f"{rel}:{line_no}: {stripped}")
    return violations


RULES: list[tuple[str, str, Callable[[], list[str]]]] = [
    ("AG-001", "list_runs() direct usage in app/ (use RunHistoryQueryPort)", check_ag001_list_runs),
    ("AG-002", "playwright import in app/orchestrator/", check_ag002_orchestrator_no_playwright),
    ("AG-003", "I/O or async runtime import in app/domain/", check_ag003_domain_purity),
    (
        "AG-004",
        "list_all_runs() / list_runs_since() in app/orchestrator/",
        check_ag004_orchestrator_history_scan,
    ),
    (
        "AG-005",
        "aggregate .snapshot / .suite outside app/domain/",
        check_ag005_aggregate_encapsulation,
    ),
]


def main() -> int:
    failed = False
    for rule_id, description, checker in RULES:
        violations = checker()
        if violations:
            failed = True
            print(f"Architecture gate {rule_id} failed: {description}")
            for item in violations:
                print(f"  - {item}")
    if failed:
        return 1
    print(f"Architecture gates passed ({len(RULES)} rules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
