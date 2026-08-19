import json
from pathlib import Path

from scripts.ci.gates import (
    GATE_COMMANDS,
    GATE_TIERS,
    PROFILE_GATES,
    STANDARD_GATES,
)

FRONTEND_GATES = (
    "frontend_gates",
    "frontend_tokens",
    "typecheck_web",
    "eslint_web",
    "build_web",
    "vitest_web",
)

# npm 스크립트를 직접 실행하는 게이트 → 기대 스크립트 이름
NPM_GATES = {
    "typecheck_web": "typecheck",
    "eslint_web": "lint",
    "build_web": "build",
    "vitest_web": "test",
}


def test_frontend_gates_are_registered():
    for name in FRONTEND_GATES:
        assert name in GATE_COMMANDS, name


def test_frontend_gates_are_tier_zero():
    """빠르고 결정적인 검사이므로 fail-fast 계층에 둔다."""
    for name in FRONTEND_GATES:
        assert GATE_TIERS[name] == 0, name


def test_frontend_gates_are_in_standard_profile():
    for name in FRONTEND_GATES:
        assert name in STANDARD_GATES, name


def test_docs_only_profile_excludes_frontend_gates():
    """문서만 바뀐 PR 에서 npm 빌드를 요구하지 않는다."""
    for name in FRONTEND_GATES:
        assert name not in PROFILE_GATES["docs_only"], name


def test_npm_gates_invoke_the_expected_package_json_script():
    """게이트가 실제로 어떤 npm 스크립트를 도는지 고정한다."""
    for gate, script in NPM_GATES.items():
        cmd = GATE_COMMANDS[gate]
        assert cmd[-2:] == ["run", script], (gate, cmd)


def test_npm_gate_scripts_exist_in_package_json():
    """package.json 에서 스크립트가 사라지면 게이트가 조용히 유령이 된다."""
    package = json.loads(
        (Path(__file__).resolve().parents[2] / "package.json").read_text(encoding="utf-8")
    )
    for gate, script in NPM_GATES.items():
        assert script in package["scripts"], (gate, script)


def test_build_and_vitest_gates_are_wired():
    """정적 검사(typecheck·lint)만으로는 빌드 파이프라인 파손·Vitest 회귀를 못 막는다."""
    for name in ("build_web", "vitest_web"):
        assert name in GATE_COMMANDS, name
        assert GATE_TIERS[name] == 0, name
        assert name in STANDARD_GATES, name
        assert name not in PROFILE_GATES["docs_only"], name
