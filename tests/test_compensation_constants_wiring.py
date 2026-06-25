"""보험금청구 result/cancel 단계의 청구 식별 상수 참조 검증.

청구 본문 문구는 `app.scenarios.rep_homepage.constants` 가 단일 진실원천이다.
`compensation_result_common` 은 UI 헬퍼만 제공하며, 상수를 재노출하지 않는다.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_COMPENSATION_STEP_SOURCES = (
    _REPO_ROOT / "app/systems/hom/steps/compensation_result.py",
    _REPO_ROOT / "app/systems/mhm/steps/compensation_result.py",
    _REPO_ROOT / "app/systems/hom/steps/compensation_cancel.py",
    _REPO_ROOT / "app/systems/mhm/steps/compensation_cancel.py",
)


def test_compensation_steps_do_not_read_claim_constants_from_result_common() -> None:
    forbidden = (
        "result_common.TARGET_CLAIM_TEXT",
        "result_common.CLAIM_CONTENT_TEXT",
    )
    for path in _COMPENSATION_STEP_SOURCES:
        source = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert pattern not in source, (
                f"{path.relative_to(_REPO_ROOT)}: "
                f"{pattern!r} must not be used; import from "
                "app.scenarios.rep_homepage.constants instead"
            )


def test_compensation_result_common_does_not_reexport_claim_constants() -> None:
    from app.systems.hom.steps import compensation_result_common as hom_common
    from app.systems.mhm.steps import compensation_result_common as mhm_common

    for module in (hom_common, mhm_common):
        assert not hasattr(module, "TARGET_CLAIM_TEXT")
        assert not hasattr(module, "CLAIM_CONTENT_TEXT")
