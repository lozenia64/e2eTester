from scripts.ci.gates import (
    GATE_COMMANDS,
    GATE_TIERS,
    PROFILE_GATES,
    STANDARD_GATES,
)

FRONTEND_GATES = ("frontend_gates", "frontend_tokens", "typecheck_web", "eslint_web")


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
