#!/usr/bin/env python3
"""아키텍처 게이트 — ``app/`` 에 ``list_runs(`` 직접 호출이 남아 있으면 실패."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"

# 포트 정의·이력 조회 어댑터·하위 호환 인메모리 구현은 허용
ALLOWED_SUFFIXES = (
    "storage/ports.py",
    "storage/run_repository.py",
    "storage/sqlite_run_repository.py",
    "storage/sqlite_run_history_query.py",
    "storage/composite_run_repository.py",
    "api/routes_runs.py",
    "api/routes_admin.py",
)

# 메서드/함수 호출만 검사 (API 라우트 함수 정의 `def list_runs` 는 제외)
PATTERN = re.compile(r"\.list_runs\s*\(")


def main() -> int:
    violations: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if any(rel.endswith(suffix) for suffix in ALLOWED_SUFFIXES):
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if PATTERN.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()}")
    if violations:
        print("Architecture gate failed: list_runs() usage in app/ (use RunHistoryQueryPort):")
        for item in violations:
            print(f"  - {item}")
        return 1
    print("Architecture gate passed: no disallowed list_runs() in app/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
