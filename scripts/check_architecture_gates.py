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
  AG-007  *QueryPort 프로토콜은 Run/SuiteRun 반환 금지 (화면형 Row DTO 만 — blob 재수화 봉쇄)
  AG-008  오케스트레이터 서비스에서 run/suite/step/module 필드 직접 변이 금지
          (애그리거트가 유일한 상태 변이자 — 서비스가 우회 변이하는 이중 권위 차단)
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
CONTEXTS_DIR = APP_DIR / "contexts"


def _application_dirs() -> list[Path]:
    """애플리케이션(오케스트레이션) 계층 디렉터리 — 레거시 orchestrator + 컨텍스트별 application."""
    dirs = [ORCHESTRATOR_DIR] if ORCHESTRATOR_DIR.is_dir() else []
    if CONTEXTS_DIR.is_dir():
        dirs += [p for p in CONTEXTS_DIR.glob("*/application") if p.is_dir()]
    return dirs


def _domain_dirs() -> list[Path]:
    """도메인 계층 디렉터리 — 레거시 domain + 컨텍스트별 domain."""
    dirs = [DOMAIN_DIR] if DOMAIN_DIR.is_dir() else []
    if CONTEXTS_DIR.is_dir():
        dirs += [p for p in CONTEXTS_DIR.glob("*/domain") if p.is_dir()]
    return dirs


AGGREGATE_ALLOWED_PREFIXES = (
    "app/domain/",
    "app/contexts/",
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
    for base in _application_dirs():
        for path in base.rglob("*.py"):
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
    import_re = re.compile(r"^\s*(?:from|import)\s+([\w.]+)")
    for base in _domain_dirs():
        for path in base.rglob("*.py"):
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
    for base in _application_dirs():
        for path in base.rglob("*.py"):
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


# AG-007: *QueryPort 프로토콜 메서드는 도메인 엔티티(Run/SuiteRun)를 반환하지 않는다.
# 화면형 행(Row DTO)만 반환하도록 강제해 blob 재수화 경로 부활을 타입 수준에서 봉쇄한다.
PORTS_FILE = APP_DIR / "storage" / "ports.py"
QUERY_PORT_CLASS_PATTERN = re.compile(r"^class\s+(\w*QueryPort)\b")
ANY_CLASS_PATTERN = re.compile(r"^class\s+\w+")
ENTITY_RETURN_PATTERN = re.compile(r"->\s*(?:list\[)?(?:Run|SuiteRun)\b")


def check_ag007_query_ports_return_rows() -> list[str]:
    violations: list[str] = []
    if not PORTS_FILE.is_file():
        return violations
    in_query_port = False
    for line_no, line in enumerate(PORTS_FILE.read_text(encoding="utf-8").splitlines(), start=1):
        if ANY_CLASS_PATTERN.match(line):
            in_query_port = bool(QUERY_PORT_CLASS_PATTERN.match(line))
            continue
        if in_query_port and ENTITY_RETURN_PATTERN.search(line):
            violations.append(f"storage/ports.py:{line_no}: {line.strip()}")
    return violations


# AG-008: 오케스트레이터 서비스는 도메인 엔티티 필드를 직접 변이하지 않는다(유일 변이자 =
# 애그리거트). run.<field> = / suite.<field> = / step.<field> = / module.<field> = 대입을 금지해
# 서비스가 애그리거트를 우회해 상태를 바꾸는 이중 권위를 막는다. 로컬 변수 재바인딩
# (run = ..., suite = ...)은 대상이 아니다(속성 대입만 탐지).
# run/suite 서비스는 레거시 orchestrator/ 또는 컨텍스트 application/ 어디에 있든 스캔한다.
AG008_SERVICE_BASENAMES = ("run_service.py", "suite_service.py", "service.py")
DIRECT_MUTATION_PATTERN = re.compile(
    r"\b(?:run|suite|step|module)\.(?:status|started_at|ended_at|awaiting_input_module_id|"
    r"awaiting_input_prompt|awaiting_input_run_id|current_step_index|active_run_id|"
    r"created_by_user_id|created_by_user_name|run_id)\s*=\s*(?!=)"
)


def check_ag008_service_no_direct_entity_mutation() -> list[str]:
    violations: list[str] = []
    for base in _application_dirs():
        for path in base.rglob("*.py"):
            if path.name not in AG008_SERVICE_BASENAMES:
                continue
            rel = _rel(path)
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                code = re.sub(r"`+[^`]*`+", "", line)
                if DIRECT_MUTATION_PATTERN.search(code):
                    violations.append(f"{rel}:{line_no}: {stripped}")
    return violations


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
    (
        "AG-007",
        "*QueryPort returns Run/SuiteRun (query ports must return screen-shaped rows)",
        check_ag007_query_ports_return_rows,
    ),
    (
        "AG-008",
        "direct entity mutation in orchestrator services (aggregate is the sole mutator)",
        check_ag008_service_no_direct_entity_mutation,
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
