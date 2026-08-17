#!/usr/bin/env python3
"""CI 설정 정합성 게이트 — 유령 경로·미등록 게이트를 차단한다."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.platform.stdio_utf8 import configure_stdio_utf8  # noqa: E402
from scripts.ci.gates import validate_ci_config  # noqa: E402


def main() -> int:
    configure_stdio_utf8()
    problems = validate_ci_config(ROOT)
    print("CI 설정 정합성 검사 (ci_config_valid)")
    print("=" * 44)
    if not problems:
        print("[OK]   모든 경로·게이트 참조가 실재합니다.")
        return 0
    for problem in problems:
        print(f"[FAIL] {problem}")
    print("-" * 44)
    print(f"{len(problems)}건의 문제가 있습니다.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
