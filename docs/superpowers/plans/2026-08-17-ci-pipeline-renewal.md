# CI 파이프라인 전면 리뉴얼 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/ci/gates.py` 를 GitHub Actions 의 실제 SSOT 로 만들어, 게이트가 CI 에서 조용히 누락되는 드리프트를 구조적으로 불가능하게 한다.

**Architecture:** `ci.yml` 이 게이트 목록을 인라인으로 중복 기재하던 구조를 `plan → gate(matrix) → required` 3-job 으로 교체한다. `plan` job 이 `gates.py` 를 읽어 게이트 목록 JSON 을 뱉고, `gate` job 이 matrix 로 게이트당 job 하나를 만든다. 경로 글롭도 YAML 에서 `gates.py` 로 옮겨 단위 테스트로 덮고, `ci_config_valid` 게이트가 유령 경로를 스스로 잡는다.

**Tech Stack:** GitHub Actions, Python 3.13, ruff, pytest + pytest-cov, import-linter, pyright, bandit, pip-audit.

**Spec:** `docs/superpowers/specs/2026-08-17-ci-pipeline-renewal-design.md`

## Global Constraints

- **Python 3.13 단일 기준.** `ci.yml`, `[tool.ruff] target-version = "py313"`, `[tool.pyright] pythonVersion = "3.13"`, `docs/INSTALL.md` 의 `Python 3.13+` 가 모두 일치해야 한다.
- **커버리지 바닥선은 57** (실측 58% 바로 아래). `pyproject.toml` 의 `[tool.coverage.report] fail_under` 가 SSOT.
- **한국어 문자열 불변** — UI·로그·문서 문자열은 한국어 (AGENTS.md 제약).
- **`gates.py` 가 CI 의 SSOT.** 게이트 목록·경로 글롭을 `ci.yml` 에 중복 기재하지 않는다. 이 계획이 존재하는 이유 자체다.
- **CI 밖 유지:** 라이브 Playwright E2E 는 CI 에 넣지 않는다.
- **Windows 로컬 검증:** 모든 검증 명령은 `python3 -m ...` 형태. `.sh` 는 `bash <path>.sh`.
- **비목표(넣지 않음):** Python 3.11+3.13 매트릭스, `pip_audit` 상시 실행, PR 요약 코멘트.
- **최종 확인:** 전 태스크 완료 후 `python3 scripts/ci/run_all_gates.py --profile full` 통과.

## File Structure

| File | Action | Responsibility |
| --- | --- | --- |
| `scripts/ci/gates.py` | **Modify** | 게이트 SSOT + 경로 글롭 + CI 설정 검증 로직 |
| `scripts/ci/check_ci_config.py` | **Create** | `ci_config_valid` 게이트 실행 진입점 |
| `scripts/ci/plan.py` | **Create** | 변경 파일 → 게이트 목록 JSON (matrix 입력) |
| `scripts/ci/run_all_gates.py` | **Modify** | `--gate` 단일 게이트 모드 추가 |
| `.github/workflows/ci.yml` | **Rewrite** | plan → gate(matrix) → required |
| `pyproject.toml` | **Modify** | ruff/pyright 3.13, `[tool.coverage.*]` |
| `requirements-dev.txt` | **Modify** | `pytest-cov` 추가 |
| `app/ai/gemini_client.py` | **Modify** | PEP 695 (UP047 ×2) |
| `app/realtime/listener_registry.py` | **Modify** | PEP 695 (UP046) |
| `docs/CI.md` | **Modify** | 게이트 표·required check 갱신 |
| `docs/INSTALL.md` | **Modify** | `Python 3.11+` → `3.13+` |
| `tests/test_ci_config_valid.py` | **Create** | 유령 경로 회귀 테스트 |
| `tests/test_ci_plan.py` | **Create** | 게이트 목록 판정 테스트 |

**Do not touch:** `app/automation/`, `app/systems/`, `docs/specs/`, `docs/scenarios/`, `.github/dependabot.yml`.

---

## Task 1: `ci_config_valid` 게이트 + 유령 경로 수정

`ci.yml` 에 흩어져 있던 경로 글롭을 `gates.py` 로 옮기고, 그 글롭이 실파일에 매칭되는지 CI 가 스스로 검사하게 한다. 오늘 발견된 `app/storage/*` 유령 경로를 회귀 테스트로 고정한다.

**Files:**
- Modify: `scripts/ci/gates.py`
- Create: `scripts/ci/check_ci_config.py`
- Test: `tests/test_ci_config_valid.py`

**Interfaces:**
- Consumes: 기존 `GATE_COMMANDS`, `GATE_TIERS`, `PROFILE_GATES`, `PREFLIGHT_GATES`
- Produces:
  - `SECURITY_PATHS: list[str]`
  - `DOCS_ONLY_PATHS: list[str]`
  - `validate_ci_config(workspace: Path) -> list[str]` — 문제 목록, 빈 리스트면 정상
  - 게이트 이름 `"ci_config_valid"`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_ci_config_valid.py` 생성:

```python
"""CI 설정 자체의 정합성 검사 (유령 경로 재발 차단)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import gates
from scripts.ci.gates import validate_ci_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_current_ci_config_has_no_problems():
    assert validate_ci_config(REPO_ROOT) == []


def test_ghost_security_path_is_detected(monkeypatch: pytest.MonkeyPatch):
    """2026-08-17 회귀: app/storage/ 는 이사 갔는데 CI 가 계속 참조하고 있었다."""
    monkeypatch.setattr(gates, "SECURITY_PATHS", ["app/storage/input_crypto.py"])
    problems = validate_ci_config(REPO_ROOT)
    assert any("app/storage/input_crypto.py" in p for p in problems)


def test_ghost_gate_command_path_is_detected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        gates,
        "GATE_COMMANDS",
        {"bogus": ["python3", "scripts/does_not_exist.py"]},
    )
    problems = validate_ci_config(REPO_ROOT)
    assert any("scripts/does_not_exist.py" in p for p in problems)


def test_profile_referencing_unknown_gate_is_detected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gates, "PROFILE_GATES", {"full": ["no_such_gate"]})
    problems = validate_ci_config(REPO_ROOT)
    assert any("no_such_gate" in p for p in problems)


def test_gate_without_tier_is_detected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gates, "GATE_COMMANDS", {"tierless": ["python3", "--version"]})
    monkeypatch.setattr(gates, "GATE_TIERS", {})
    problems = validate_ci_config(REPO_ROOT)
    assert any("tierless" in p for p in problems)
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m pytest tests/test_ci_config_valid.py -q`
Expected: FAIL — `ImportError: cannot import name 'validate_ci_config'`

- [ ] **Step 3: `gates.py` 에 경로 글롭 상수를 추가한다**

`scripts/ci/gates.py` 의 `GATE_COMMANDS` 정의 **바로 앞**에 삽입:

```python
# --- CI 경로 글롭 (SSOT) ---------------------------------------------------
# ci.yml 에 두면 YAML 이라 테스트가 불가능하고, 코드 이동 시 조용히 유령 경로가 된다.
# (2026-08-17: app/storage/ 가 이사한 뒤로 security 게이트가 발화하지 않고 있었다.)
# 여기 두면 validate_ci_config() 가 실재성을 강제한다.
SECURITY_PATHS: list[str] = [
    "app/contexts/identity/**",
    "app/platform/security/**",
    "app/contexts/*/infrastructure/encrypted_*_input_store.py",
    "app/api/routes_trigger.py",
    "app/api/routes_otp.py",
    "requirements.txt",
    "requirements-dev.txt",
]

# 이 글롭에만 매칭되는 변경은 docs-only 로 판정한다.
# `*.md` 가 반드시 필요하다 — fnmatch 는 `**/*.md` 로 루트의 README.md 를 매칭하지
# 못한다(`**/` 가 슬래시를 요구). 실측 확인: fnmatch("README.md","**/*.md") == False.
DOCS_ONLY_PATHS: list[str] = [
    "docs/**",
    "*.md",
    "**/*.md",
]
```

- [ ] **Step 4: `GATE_COMMANDS` 와 `GATE_TIERS` 에 새 게이트를 등록한다**

`GATE_COMMANDS` 딕셔너리 안, `"docs_consistency"` 줄 바로 아래에 추가:

```python
    "ci_config_valid": _py("scripts/ci/check_ci_config.py"),
```

`GATE_TIERS` 딕셔너리 안, `"docs_consistency": 0,` 바로 아래에 추가:

```python
    "ci_config_valid": 0,
```

`STANDARD_GATES` 리스트의 맨 앞(`"docs_consistency",` 앞)에 추가:

```python
    "ci_config_valid",
```

`PROFILE_GATES` 의 `"docs_only"` 항목을 교체:

```python
    "docs_only": ["ci_config_valid", "docs_consistency", "architecture_gates"],
```

- [ ] **Step 4b: bandit 스캔 범위에 암호화 구현체를 추가한다**

기존 `bandit_security` 게이트는 `app/contexts/identity`, `routes_trigger.py`, `routes_otp.py`
만 스캔한다. 정작 AES-GCM 구현체인 `app/platform/security/input_crypto.py` 와 암호화
저장소가 빠져 있다. `GATE_COMMANDS` 의 `"bandit_security"` 항목을 교체:

```python
    "bandit_security": _py(
        "-m",
        "bandit",
        "-c",
        "pyproject.toml",
        "-r",
        "app/contexts/identity",
        # at-rest 암호화 구현체 — 원래 app/storage/ 에 있어 스캔 대상이었으나
        # 이사 후 범위에서 누락돼 있었다(2026-08-17).
        "app/platform/security",
        "app/contexts/run/infrastructure/encrypted_run_input_store.py",
        "app/contexts/suite/infrastructure/encrypted_suite_input_store.py",
        "app/api/routes_trigger.py",
        "app/api/routes_otp.py",
    ),
```

확인: `python3 scripts/ci/run_all_gates.py --gate bandit_security`
Expected: `{"passed": true, ...}` — 실측 결과 신규 findings 0건(596 LOC 스캔)

- [ ] **Step 5: `validate_ci_config()` 를 구현한다**

`scripts/ci/gates.py` 파일 **맨 끝**에 추가. 상단 import 에 `import glob as _glob` 을 추가한다(`import json` 아래).

```python
def validate_ci_config(workspace: Path) -> list[str]:
    """CI 설정 자체의 정합성을 검사한다. 반환값이 빈 리스트면 정상.

    ci.yml 에 경로를 하드코딩하던 시절 `app/storage/*` 가 이사한 뒤에도 계속 참조되어
    security 게이트가 조용히 죽어 있었다. 그 부류를 CI 가 스스로 잡게 하는 검사다.
    """
    problems: list[str] = []
    root = str(workspace)

    # 1) 경로 글롭이 최소 1개 실파일에 매칭되는가
    for label, patterns in (("SECURITY_PATHS", SECURITY_PATHS), ("DOCS_ONLY_PATHS", DOCS_ONLY_PATHS)):
        for pattern in patterns:
            if not _glob.glob(pattern, root_dir=root, recursive=True):
                problems.append(f"{label} 글롭이 아무 파일에도 매칭되지 않음: `{pattern}`")

    # 2) 게이트 명령의 파일 경로 인자가 실재하는가
    for name, cmd in GATE_COMMANDS.items():
        for arg in cmd[1:]:
            if not arg.startswith(("app/", "scripts/", "tests/", "docs/")):
                continue
            if not (workspace / arg).exists():
                problems.append(f"게이트 `{name}` 의 경로 인자가 실재하지 않음: `{arg}`")

    known = set(GATE_COMMANDS) | set(PREFLIGHT_GATES)

    # 3) 모든 게이트에 tier 가 지정돼 있는가 (누락 시 tier 99 로 조용히 밀린다)
    for name in sorted(known - set(GATE_TIERS)):
        problems.append(f"GATE_TIERS 에 tier 가 없는 게이트: `{name}`")

    # 4) 프로필이 존재하지 않는 게이트를 참조하지 않는가
    for profile, names in PROFILE_GATES.items():
        for name in names:
            if name not in known:
                problems.append(f"프로필 `{profile}` 이 존재하지 않는 게이트를 참조: `{name}`")

    return problems
```

- [ ] **Step 6: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_ci_config_valid.py -q`
Expected: PASS (5 passed)

만약 `test_current_ci_config_has_no_problems` 가 실패하면 실제 유령 경로를 찾은 것이다. 출력된 경로를 확인하고 `SECURITY_PATHS` 를 실제 위치로 고친다.

- [ ] **Step 7: 게이트 진입점 스크립트를 만든다**

`scripts/ci/check_ci_config.py` 생성:

```python
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
```

- [ ] **Step 8: 게이트를 직접 실행해 확인한다**

Run: `python3 scripts/ci/check_ci_config.py`
Expected: `[OK]   모든 경로·게이트 참조가 실재합니다.` / exit 0

Run: `python3 -m ruff check scripts/ci/ tests/test_ci_config_valid.py && python3 -m ruff format --check scripts/ci/ tests/test_ci_config_valid.py`
Expected: 통과

- [ ] **Step 9: 커밋한다**

```bash
git add scripts/ci/gates.py scripts/ci/check_ci_config.py tests/test_ci_config_valid.py
git commit -m "feat(ci): ci_config_valid 게이트 추가 및 security 경로 글롭 SSOT 이관

app/storage/ 가 app/platform/security/ 및 contexts/*/infrastructure/ 로
이사한 뒤에도 ci.yml 이 옛 경로를 참조해 security 게이트가 발화하지
않고 있었다. 경로 글롭을 gates.py 로 옮기고 실재성을 CI 가 강제한다.
같은 이사로 스캔 범위에서 빠져 있던 암호화 구현체를 bandit 대상에 복구.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: `run_all_gates.py --gate` 단일 게이트 모드

matrix 의 각 leg 가 게이트 하나만 실행할 수 있게 한다. 기존 `--profile` 동작은 로컬 pre-PR 용도로 그대로 둔다.

**Files:**
- Modify: `scripts/ci/run_all_gates.py`
- Test: `tests/test_ci_plan.py`

**Interfaces:**
- Consumes: Task 1 의 `GATE_COMMANDS`, `PREFLIGHT_GATES`
- Produces: CLI 플래그 `--gate <name>` — 종료코드 0(통과)/1(실패 또는 미지 게이트명)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_ci_plan.py` 생성 (Task 4 에서 같은 파일에 계속 추가한다):

```python
"""CI 게이트 러너·플래너 계약."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_gates_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/ci/run_all_gates.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def test_single_gate_mode_runs_one_gate():
    proc = _run_gates_cli("--gate", "ci_config_valid")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert '"gate_count": 1' in proc.stdout


def test_unknown_gate_name_is_rejected():
    proc = _run_gates_cli("--gate", "no_such_gate")
    assert proc.returncode == 1
    assert "no_such_gate" in proc.stdout
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m pytest tests/test_ci_plan.py -q`
Expected: FAIL — `--gate` 를 모르는 인자로 거부하며 returncode 2

- [ ] **Step 3: `--gate` 플래그를 추가한다**

`scripts/ci/run_all_gates.py` 의 `--fail-fast` 인자 정의 **바로 아래**에 추가:

```python
    parser.add_argument(
        "--gate",
        default=None,
        help="단일 게이트만 실행 (GitHub Actions matrix leg 용)",
    )
```

- [ ] **Step 4: 단일 게이트 분기를 구현한다**

같은 파일에서 import 문을 교체:

```python
from scripts.ci.gates import (  # noqa: E402
    GATE_COMMANDS,
    PREFLIGHT_GATES,
    resolve_gates,
    run_gates,
)
```

`gate_names = resolve_gates(...)` 를 감싼 `try/except KeyError` 블록 **전체**를 아래로 교체:

```python
    if args.gate:
        known = set(GATE_COMMANDS) | set(PREFLIGHT_GATES)
        if args.gate not in known:
            print(json.dumps({"error": f"unknown gate: {args.gate}"}, ensure_ascii=False))
            return 1
        gate_names = [args.gate]
    else:
        try:
            gate_names = resolve_gates(args.profile, risk_flags or None)
        except KeyError as exc:
            print(json.dumps({"error": exc.args[0] if exc.args else str(exc)}))
            return 1
```

그리고 최종 출력의 `"profile"` 값이 단일 게이트 모드에서도 의미를 갖도록 교체:

```python
    print(
        json.dumps(
            {
                "passed": passed,
                "profile": args.gate or args.profile,
                "gate_count": len(results),
            },
            ensure_ascii=False,
        )
    )
```

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_ci_plan.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: 기존 동작이 깨지지 않았는지 확인한다**

Run: `python3 scripts/ci/run_all_gates.py --profile docs_only`
Expected: `{"passed": true, "profile": "docs_only", "gate_count": 3}`

- [ ] **Step 7: 커밋한다**

```bash
git add scripts/ci/run_all_gates.py tests/test_ci_plan.py
git commit -m "feat(ci): run_all_gates.py 에 --gate 단일 게이트 모드 추가

GitHub Actions matrix 의 각 leg 가 게이트 하나만 실행하기 위한 진입점.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: `coverage` 게이트 + `CI_STANDARD_GATES`

테스트 실행과 커버리지 측정을 한 번에 하는 게이트를 만들고, CI 용 게이트 목록을 로컬용과 분리한다.

**Files:**
- Modify: `requirements-dev.txt`, `pyproject.toml`, `scripts/ci/gates.py`

**Interfaces:**
- Consumes: Task 1 의 `STANDARD_GATES`
- Produces:
  - 게이트 이름 `"coverage"`
  - `CI_STANDARD_GATES: list[str]` — `STANDARD_GATES` 에서 `pytest` 를 빼고 `coverage` 를 넣은 목록

- [ ] **Step 1: `pytest-cov` 를 의존성에 추가한다**

`requirements-dev.txt` 의 `pytest-asyncio` 줄 아래에 추가:

```
# 커버리지 래칫 게이트(coverage) — 임계값은 pyproject [tool.coverage.report] fail_under 가 SSOT
pytest-cov>=7.0,<8.0
```

- [ ] **Step 2: 설치하고 현재 수치를 재확인한다**

Run: `python3 -m pip install -r requirements-dev.txt`
Run: `python3 -m pytest tests/ -q --cov=app --cov=worker --cov-report=term | tail -3`
Expected: `TOTAL ... 58%` 부근, `621 passed`

측정치가 57 미만이면 **여기서 멈추고 보고한다.** 바닥선 가정이 깨진 것이므로 `fail_under` 를 실측치−1 로 조정해야 한다.

- [ ] **Step 3: `pyproject.toml` 에 커버리지 설정을 추가한다**

`[tool.pytest.ini_options]` 블록 **바로 앞**에 삽입:

```toml
# 커버리지 래칫 — 하락만 차단한다. 수치가 오르면 fail_under 를 올리는 PR 을 별도로 낸다
# (자동 상향은 리뷰 없이 기준이 바뀌어 나중에 왜 빨간지 설명할 수 없게 된다).
# 실측 58%(2026-08-17, 18416 구문 중 7648 미커버) 바로 아래인 57 에서 시작한다.
# 정확히 58 로 잡으면 무해한 리팩터링에도 CI 가 빨개져 게이트가 우회당한다.
[tool.coverage.run]
source = ["app", "worker"]
omit = ["*/__pycache__/*", "app/web/static/*"]

[tool.coverage.report]
fail_under = 57
skip_covered = false
```

- [ ] **Step 4: 게이트를 등록한다**

`scripts/ci/gates.py` 의 `GATE_COMMANDS` 에서 `"pytest"` 줄 **바로 아래**에 추가:

```python
    "coverage": _py(
        "-m",
        "pytest",
        "tests/",
        "-q",
        "--cov",
        "--cov-report=term-missing:skip-covered",
    ),
```

`GATE_TIERS` 에서 `"pytest": 2,` **바로 아래**에 추가:

```python
    "coverage": 2,
```

`SECURITY_GATES` 정의 **바로 아래**에 추가:

```python
# CI 는 pytest 대신 coverage 를 쓴다 — coverage 가 pytest --cov 를 한 번 실행해
# 테스트 실행과 커버리지 측정을 겸하므로, 둘을 함께 넣으면 621개 테스트가 두 번 돈다.
# 로컬 STANDARD_GATES 는 빠른 pytest 를 유지한다(측정 시 136초 vs 116초).
CI_STANDARD_GATES: list[str] = [
    name for name in STANDARD_GATES if name != "pytest"
] + ["coverage"]
```

- [ ] **Step 5: 게이트가 도는지 확인한다**

Run: `python3 scripts/ci/run_all_gates.py --gate coverage`
Expected: `{"passed": true, "profile": "coverage", "gate_count": 1}` (약 2분 20초)

Run: `python3 -m pytest tests/test_ci_config_valid.py -q`
Expected: PASS — 새 게이트도 tier·프로필 검사를 통과해야 한다

- [ ] **Step 6: 래칫이 실제로 작동하는지 확인한다**

임시로 `pyproject.toml` 의 `fail_under = 57` 을 `fail_under = 99` 로 바꾼 뒤:

Run: `python3 scripts/ci/run_all_gates.py --gate coverage`
Expected: `{"passed": false, ...}` — 래칫이 하락을 막는다는 증거

확인 후 **반드시 57 로 되돌린다.**

- [ ] **Step 7: 커밋한다**

```bash
git add requirements-dev.txt pyproject.toml scripts/ci/gates.py
git commit -m "feat(ci): 커버리지 래칫 게이트 추가 (fail_under=57)

실측 58% 바로 아래를 바닥선으로 잡아 하락만 차단한다. CI 게이트 목록은
pytest 대신 coverage 를 쓴다(테스트 2회 실행 방지).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: `scripts/ci/plan.py` — 변경 파일 → 게이트 목록

matrix 에 넣을 게이트 목록을 결정하는 판정 로직. YAML 로는 테스트가 불가능하므로 전부 Python 으로 옮기고 단위 테스트로 덮는다.

**Files:**
- Create: `scripts/ci/plan.py`
- Modify: `tests/test_ci_plan.py`

**Interfaces:**
- Consumes: Task 1 의 `SECURITY_PATHS`·`DOCS_ONLY_PATHS`, Task 3 의 `CI_STANDARD_GATES`, 기존 `SECURITY_GATES`
- Produces:
  - `matches_any(path: str, patterns: list[str]) -> bool`
  - `resolve_ci_gates(changed: list[str], *, event_name: str) -> list[str]`
  - `resolve_changed_vs_base(workspace: Path, base_ref: str) -> list[str]`
  - CLI: `--base-ref`, `--event-name`, `--github-output` → `gates=<json>` / `scope=<str>`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_ci_plan.py` **끝에** 추가:

```python
from scripts.ci.gates import SECURITY_PATHS  # noqa: E402
from scripts.ci.plan import matches_any, resolve_ci_gates  # noqa: E402


def test_docs_only_change_runs_minimal_gates():
    gates = resolve_ci_gates(["docs/CI.md", "README.md"], event_name="pull_request")
    assert gates == ["ci_config_valid", "docs_consistency", "architecture_gates"]


def test_code_change_runs_full_gates():
    gates = resolve_ci_gates(["app/api/routes_runs.py"], event_name="pull_request")
    assert "coverage" in gates
    assert "import_contracts" in gates
    assert "pyright_decider" in gates
    assert "pytest" not in gates  # coverage 가 흡수한다


def test_security_path_adds_security_gates():
    gates = resolve_ci_gates(
        ["app/platform/security/input_crypto.py"], event_name="pull_request"
    )
    assert "pip_audit" in gates
    assert "bandit_security" in gates


def test_encrypted_input_store_is_a_security_path():
    """2026-08-17 회귀: 이 경로가 security 필터에서 빠져 있었다."""
    assert matches_any(
        "app/contexts/run/infrastructure/encrypted_run_input_store.py",
        SECURITY_PATHS,
    )


def test_non_security_code_change_skips_security_gates():
    gates = resolve_ci_gates(["app/web/static/dashboard.js"], event_name="pull_request")
    assert "pip_audit" not in gates


def test_schedule_event_runs_everything():
    gates = resolve_ci_gates([], event_name="schedule")
    assert "pip_audit" in gates
    assert "coverage" in gates


def test_never_returns_empty_list():
    """빈 matrix 는 GitHub Actions 가 오류로 처리한다."""
    assert resolve_ci_gates([], event_name="pull_request") != []


def test_gate_list_has_no_duplicates():
    gates = resolve_ci_gates(
        ["app/contexts/identity/service.py", "requirements.txt"],
        event_name="pull_request",
    )
    assert len(gates) == len(set(gates))
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m pytest tests/test_ci_plan.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.ci.plan'`

- [ ] **Step 3: `plan.py` 를 구현한다**

`scripts/ci/plan.py` 생성:

```python
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
    SECURITY_GATES,
    SECURITY_PATHS,
)

DOCS_ONLY_GATES: list[str] = ["ci_config_valid", "docs_consistency", "architecture_gates"]


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
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_ci_plan.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: CLI 를 직접 실행해 확인한다**

Run: `python3 scripts/ci/plan.py --base-ref HEAD~1 --event-name pull_request`
Expected: `gates=[...]` 가 출력되고 exit 0

Run: `python3 -m ruff check scripts/ci/ tests/ && python3 -m ruff format --check scripts/ci/ tests/`
Expected: 통과

- [ ] **Step 6: 커밋한다**

```bash
git add scripts/ci/plan.py tests/test_ci_plan.py
git commit -m "feat(ci): 변경 파일 기반 게이트 계획 스크립트(plan.py) 추가

matrix 입력을 gates.py 에서 파생시켜 ci.yml 의 게이트 목록 중복을 제거한다.
판정 로직은 전부 단위 테스트로 덮었다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Python 3.13 상향 + PEP 695 마이그레이션

**Files:**
- Modify: `pyproject.toml`, `app/ai/gemini_client.py`, `app/realtime/listener_registry.py`, `docs/INSTALL.md`

**Interfaces:**
- Produces: 공개 시그니처 변화 없음. `ListenerRegistry[E]` 사용처(`app/realtime/adapter.py`, `app/contexts/run/infrastructure/in_memory_run_repository.py`)는 **수정 불필요**.

- [ ] **Step 1: 현재 상태를 기록한다 (변경 전 기준선)**

Run: `python3 -m pytest tests/ -q | tail -2`
Expected: `621 passed, 1 skipped`

- [ ] **Step 2: `listener_registry.py` 를 PEP 695 로 바꾼다**

`app/realtime/listener_registry.py` 의 1–10행을 아래로 교체:

```python
from __future__ import annotations

import asyncio
from collections import defaultdict


class ListenerRegistry[E]:
```

(`from typing import Generic, TypeVar` 와 `E = TypeVar("E")` 두 줄이 사라진다. 클래스 본문은 그대로 둔다.)

- [ ] **Step 3: `gemini_client.py` 를 PEP 695 로 바꾼다**

`app/ai/gemini_client.py:8` 의 `from typing import TypeVar` 를 **삭제**하고, `:22` 의 `T = TypeVar("T", bound=BaseModel)` 도 **삭제**한다.

`:61` 의 함수 시그니처를 교체:

```python
def _parse_structured_response[T: BaseModel](
    response: types.GenerateContentResponse, schema: type[T]
) -> T:
```

`:73` 의 함수 시그니처를 교체:

```python
def generate_structured_with_fallback[T: BaseModel](
```

(나머지 매개변수 줄과 `-> tuple[T, str]:` 는 그대로 둔다.)

- [ ] **Step 4: 테스트로 런타임 동작 불변을 확인한다**

Run: `python3 -m pytest tests/ -q | tail -2`
Expected: `621 passed, 1 skipped` — Step 1 과 동일

- [ ] **Step 5: `pyproject.toml` 의 툴 타깃을 올린다**

`[tool.ruff]` 의 `target-version = "py311"` → `target-version = "py313"`
`[tool.pyright]` 의 `pythonVersion = "3.11"` → `pythonVersion = "3.13"`

- [ ] **Step 6: 린트·타입체크가 깨끗한지 확인한다**

Run: `python3 -m ruff check .`
Expected: `All checks passed!` — UP046/UP047 3건이 사라져야 한다

Run: `python3 -m ruff format --check .`
Expected: 통과 (실패 시 `python3 -m ruff format .` 후 재확인)

Run: `python3 -m pyright app/contexts/run/domain/decider.py app/contexts/suite/domain/decider.py`
Expected: `0 errors`

- [ ] **Step 7: `docs/INSTALL.md` 의 선언을 맞춘다**

`docs/INSTALL.md:7` 의 `**준비:** Python 3.11+, Git, Redis.` 를 교체:

```markdown
**준비:** Python 3.13+, Git, Redis.
```

**이 줄을 빼먹으면 안 된다.** CI 가 3.13 만 검증하는데 문서가 3.11+ 를 공표하면, 아무도 검증하지 않는 지원 선언이 남는다.

- [ ] **Step 8: 문서 정합성 게이트를 확인한다**

Run: `python3 scripts/check_docs_consistency.py | tail -3`
Expected: `모든 정합성 검사를 통과했습니다.`

- [ ] **Step 9: 커밋한다**

```bash
git add pyproject.toml app/ai/gemini_client.py app/realtime/listener_registry.py docs/INSTALL.md
git commit -m "refactor: Python 3.13 단일 기준으로 상향 + PEP 695 마이그레이션

ruff target-version·pyright pythonVersion·INSTALL.md 지원 선언을 3.13 으로
일치시킨다. py313 타깃에서 뜨는 UP046/UP047 3건을 PEP 695 문법으로 해소.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: `ci.yml` 전면 재작성

**Files:**
- Rewrite: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: Task 2 의 `--gate`, Task 4 의 `plan.py`
- Produces: required check 이름 **`ci / required`** (단일)

- [ ] **Step 1: `plan.py` 가 CI 환경에서 쓸 base-ref 를 확인한다**

이벤트별 base ref 는 아래를 쓴다.

| 이벤트 | base ref |
| --- | --- |
| `pull_request` | `origin/${{ github.base_ref }}` |
| `push` | `${{ github.event.before }}` |
| `merge_group` | `origin/${{ github.event.merge_group.base_ref }}` |
| `schedule` | (없음 — `plan.py` 가 전체 실행으로 판정) |

- [ ] **Step 2: `ci.yml` 을 통째로 교체한다**

`.github/workflows/ci.yml` 전체 내용을 아래로 교체:

```yaml
name: ci

# e2eTester PR/push CI
# SSOT: scripts/ci/gates.py — 게이트 목록·경로 글롭은 전부 거기서 온다.
#       이 파일에 게이트를 인라인으로 적지 말 것(2026-08-17 이전 구조에서
#       게이트 4개가 CI 에서 한 번도 실행되지 않는 드리프트가 발생했다).
# 로컬:  python3 scripts/ci/run_all_gates.py --profile full
# 규칙:  docs/CI.md, docs/DOCS_GOVERNANCE.md

on:
  pull_request:
  push:
    branches:
      - main
  merge_group:
    types:
      - checks_requested
  schedule:
    # Tier 3 보안 게이트 — 주 1회 전체 의존성 감사
    - cron: "0 3 * * 1"

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  # merge queue 검증은 취소하지 않는다 — 부분 검증 상태로 큐가 진행되면 위험하다.
  cancel-in-progress: ${{ github.event_name != 'merge_group' }}

permissions:
  contents: read

env:
  PYTHON_VERSION: "3.13"
  PYTHONUTF8: "1"

jobs:
  plan:
    name: ci / plan
    runs-on: ubuntu-latest
    outputs:
      gates: ${{ steps.plan.outputs.gates }}
      scope: ${{ steps.plan.outputs.scope }}
    steps:
      - uses: actions/checkout@v7
        with:
          # plan.py 가 base ref 와 diff 하려면 전체 히스토리가 필요하다.
          fetch-depth: 0

      - uses: actions/setup-python@v7
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Resolve gate list from gates.py
        id: plan
        env:
          BASE_REF: ${{ github.event_name == 'pull_request' && format('origin/{0}', github.base_ref) || (github.event_name == 'push' && github.event.before || '') }}
        run: |
          python3 scripts/ci/plan.py \
            --base-ref "$BASE_REF" \
            --event-name "${{ github.event_name }}" \
            --github-output "$GITHUB_OUTPUT"

  gate:
    name: ci / ${{ matrix.gate }}
    needs: plan
    runs-on: ubuntu-latest
    strategy:
      # 하나가 깨져도 나머지 게이트 결과를 전부 보여준다.
      fail-fast: false
      matrix:
        gate: ${{ fromJSON(needs.plan.outputs.gates) }}
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-python@v7
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip
          # requirements-dev.txt 는 `-r requirements.txt` 를 포함한다.
          # 둘 다 키에 넣지 않으면 런타임 의존성 변경 시 낡은 휠을 재사용한다.
          cache-dependency-path: |
            requirements.txt
            requirements-dev.txt

      - name: Install dev dependencies
        env:
          PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: "1"
        run: python3 -m pip install -r requirements-dev.txt

      - name: Run gate — ${{ matrix.gate }}
        run: python3 scripts/ci/run_all_gates.py --gate "${{ matrix.gate }}"

  required:
    name: ci / required
    needs: [plan, gate]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Verify every gate succeeded
        run: |
          if [ "${{ contains(needs.*.result, 'failure') }}" = "true" ] || \
             [ "${{ contains(needs.*.result, 'cancelled') }}" = "true" ]; then
            echo "::error::하나 이상의 게이트가 실패했습니다. 위 job 목록을 확인하세요."
            exit 1
          fi
          echo "모든 게이트 통과."
```

- [ ] **Step 3: YAML 문법을 검증한다**

Run:
```bash
python3 -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text(encoding='utf-8')); print('YAML OK')"
```
Expected: `YAML OK`

- [ ] **Step 4: `plan.py` 출력이 matrix 가 소비 가능한 형태인지 확인한다**

Run:
```bash
python3 scripts/ci/plan.py --base-ref HEAD~1 --event-name pull_request --github-output /tmp/gh-out.txt && cat /tmp/gh-out.txt
```
Expected: `gates=["ci_config_valid", ...]` 형태의 **유효한 JSON 배열** 한 줄 + `scope=...`

Run: `python3 -c "import json;print(json.loads(open('/tmp/gh-out.txt',encoding='utf-8').read().split('gates=')[1].split('\n')[0]))"`
Expected: 파이썬 리스트가 오류 없이 출력

- [ ] **Step 5: 전체 게이트를 로컬에서 통과시킨다**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: `{"passed": true, ...}`

- [ ] **Step 6: 커밋한다**

```bash
git add .github/workflows/ci.yml
git commit -m "refactor(ci): ci.yml 을 gates.py 기반 matrix 구조로 전면 재작성

plan -> gate(matrix) -> required 3-job 구조. 게이트 목록이 gates.py 에서
파생되므로 CI 누락 드리프트가 구조적으로 불가능해진다. required check 은
'ci / required' 하나로 고정돼 게이트 증감 시 브랜치 보호를 손댈 필요가 없다.

캐시 키에 requirements.txt 추가, merge_group 취소 방지도 함께 수정.

BREAKING: required check 이름이 바뀐다. 머지 전에 브랜치 보호 규칙에
'ci / required' 를 추가하고 기존 ci / docs, ci / lint, ci / test 를 제거해야 한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: 문서 갱신

**Files:**
- Modify: `docs/CI.md`, `.github/pull_request_template.md`

- [ ] **Step 1: `docs/CI.md` 의 게이트 계층 표를 갱신한다**

`## 게이트 계층` 아래 표를 교체:

```markdown
| Tier | 게이트 |
| --- | --- |
| 0 | `ci_config_valid`, `ruff`, `ruff_format`, `docs_consistency` |
| 1 | `architecture_gates` (AG-001~009), `import_contracts`, `pyright_decider`, `projection_validate`, `snapshot_validate` |
| 2 | `coverage` (= `pytest --cov`, 바닥선 57%) |
| 3 | `pip_audit`, `bandit_security` (auth/PII 경로·주간) |

로컬 러너(`--profile full`)는 Tier 2 에서 `coverage` 대신 빠른 `pytest` 를 쓴다.
커버리지 확인이 필요하면 `--gate coverage`.
```

- [ ] **Step 2: GitHub Actions 표를 갱신한다**

`## GitHub Actions` 아래 표와 그 뒤 문단을 교체:

```markdown
| Job | 내용 |
| --- | --- |
| `ci / plan` | `gates.py` + 변경 파일로 실행할 게이트 목록 결정 |
| `ci / <게이트명>` | matrix — 게이트당 job 하나 (`fail-fast: false`) |
| `ci / required` | 집계. **브랜치 보호가 거는 유일한 required check** |

게이트를 추가하려면 `scripts/ci/gates.py` 에만 등록하면 된다. `ci.yml` 은 목록을
들고 있지 않으므로 CI job 이 자동으로 생긴다. required check 이름은 게이트가
늘거나 줄어도 `ci / required` 로 고정이라 브랜치 보호를 다시 손댈 일이 없다.

조건부 게이트(`pip_audit` 등)는 해당되지 않으면 matrix 에 아예 들어가지 않는다.
skip 된 체크가 남지 않으므로 merge queue 가 멈추지 않는다.
```

- [ ] **Step 3: 실행 섹션에 `ci_config_valid` 를 언급한다**

`## 실행` 섹션의 코드블록 아래에 한 줄 추가:

```markdown
`ci_config_valid` 는 CI 설정 자체를 검사한다 — `gates.py` 의 경로 글롭이 실재
파일에 매칭되는지, 프로필이 없는 게이트를 참조하지 않는지. 코드 이동으로 CI 가
조용히 죽는 것을 막는다.
```

- [ ] **Step 4: PR 템플릿의 DoD 를 확인한다**

`.github/pull_request_template.md` 의 첫 체크박스가 여전히 유효한지 확인한다(`run_all_gates.py --profile full`). 유효하므로 **변경 불필요**하지만, 커버리지 항목을 추가한다:

```markdown
- [ ] 커버리지 하락 없음 (`python3 scripts/ci/run_all_gates.py --gate coverage`)
```

- [ ] **Step 5: 문서 정합성 게이트를 확인한다**

Run: `python3 scripts/check_docs_consistency.py | tail -3`
Expected: `모든 정합성 검사를 통과했습니다.`

- [ ] **Step 6: 전체 게이트 최종 확인**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: `{"passed": true, "profile": "full", ...}`

Run: `python3 -m pytest tests/ -q | tail -2`
Expected: `636 passed, 1 skipped` — 기존 621 + 신규 15개
(Task 1 의 `test_ci_config_valid.py` 5개, Task 2 의 2개, Task 4 의 8개)

- [ ] **Step 7: 커밋한다**

```bash
git add docs/CI.md .github/pull_request_template.md
git commit -m "docs(ci): 새 matrix 구조와 신규 게이트 반영

게이트 계층 표에 ci_config_valid·coverage 추가, GitHub Actions 표를
단일 required check 구조로 교체.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## 완료 후 사람이 해야 할 일 (자동화 불가)

이 계획은 required check 이름을 바꾼다. **머지 전에** GitHub 브랜치 보호 규칙을 갱신해야 하며, 하지 않으면 존재하지 않는 체크를 기다리며 PR 이 영구히 머지되지 않는다.

1. PR 을 올려 `ci / required` 가 실제로 도는 것을 확인한다
2. 브랜치 보호에 `ci / required` 를 **추가** (기존 3개는 아직 유지)
3. 새 체크가 통과하는 것을 확인한다
4. 기존 `ci / docs`, `ci / lint`, `ci / test` 를 **제거**한다
5. 머지

이후로는 게이트가 늘거나 줄어도 브랜치 보호는 불변이다.
