#!/usr/bin/env python3
"""아키텍처 정책 게이트 (policy-as-code).

규칙:
  AG-001  app/ 내 list_runs() 직접 호출 금지 (RunSummaryQueryPort 등 프로젝션 질의 사용)
  AG-002  app/orchestrator/ 에서 playwright import 금지
  AG-003  app/domain/ 에 I/O·async 런타임 import 금지 (순수 도메인 유지)
  AG-004  app/orchestrator/ 에서 list_all_runs( / list_runs_since( 금지
  AG-005  app/ 에서 aggregate .snapshot / .suite 접근 금지 (domain/storage/tests 제외)
  AG-006  스텝 계층(automation/systems/runner)에서 print( / redirect_stdout 금지
          (전역 stdout 치환 경합 방지 — step_logging.log / ctx.log 만 사용)
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

# AG-001: 포트 정의·테스트용 인메모리 구현만 허용(프로덕션 blob 스캔 어댑터는 삭제됨)
LIST_RUNS_ALLOWED_SUFFIXES = (
    "storage/ports.py",
    "storage/run_repository.py",
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


# AG-006: 스텝 실행 계층은 전역 stdout 을 건드리지 않는다(동시 스텝 스레드 경합 방지).
# 명시적 로깅 능력(step_logging.log / ctx.log)만 사용한다.
STEP_LAYER_DIRS = ("app/automation", "app/systems", "app/runner")
# login_phone.py 는 매니페스트 워크플로가 아닌 매뉴얼 CLI 진입점이라 print 를 허용한다.
AG006_ALLOWED_SUFFIXES = ("systems/hom/scripts/login_phone.py",)
# step_logging 정의부는 문서 문자열에서 print/redirect_stdout 을 언급한다(정책 설명).
AG006_ALLOWED_FILES = ("runner/step_logging.py",)
PRINT_CALL_PATTERN = re.compile(r"(?<![\w.])print\s*\(")
REDIRECT_STDOUT_PATTERN = re.compile(r"redirect_stdout|redirect_stderr")


def check_ag006_step_layer_no_global_stdout() -> list[str]:
    violations: list[str] = []
    for dir_rel in STEP_LAYER_DIRS:
        base = ROOT / dir_rel
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            rel = _rel(path)
            if any(rel.endswith(suffix) for suffix in AG006_ALLOWED_SUFFIXES):
                continue
            if any(rel.endswith(suffix) for suffix in AG006_ALLOWED_FILES):
                continue
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # 백틱으로 감싼 문서 문자열 내 언급(``print()`` 등)은 코드가 아니므로 제외한다
                # (단일·이중 백틱 모두: 백틱 런 사이 내용을 제거).
                code = re.sub(r"`+[^`]*`+", "", line)
                if PRINT_CALL_PATTERN.search(code) or REDIRECT_STDOUT_PATTERN.search(code):
                    violations.append(f"{rel}:{line_no}: {stripped}")
    return violations


RULES: list[tuple[str, str, Callable[[], list[str]]]] = [
    (
        "AG-001",
        "list_runs() direct usage in app/ (use projection query ports)",
        check_ag001_list_runs,
    ),
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
    (
        "AG-006",
        "print( / redirect_stdout in step layer (use step_logging.log / ctx.log)",
        check_ag006_step_layer_no_global_stdout,
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
