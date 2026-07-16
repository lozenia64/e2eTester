"""Contract tests — rep_homepage PageObject selector surface."""

from __future__ import annotations

from pathlib import Path

_FIXTURE = (
    Path(__file__).resolve().parents[2] / "app" / "automation" / "fixtures" / "hom_login_form.html"
)

_EXPECTED_SELECTORS = ("#custNm", "#btnSendCrtfNo", "#smsCertNo", "#btnNext2")


def test_hom_login_fixture_contains_core_selectors():
    html = _FIXTURE.read_text(encoding="utf-8")
    for selector in _EXPECTED_SELECTORS:
        element_id = selector.lstrip("#")
        assert f'id="{element_id}"' in html


def test_hom_page_objects_are_importable():
    from app.automation.page_objects.hom import (
        compensation_cancel,
        compensation_charge,
        contract_list,
        login_move,
        main_access,
        marketing_consent_apply,
        marketing_consent_withdraw,
        phone_login,
    )

    for module in (
        main_access,
        login_move,
        phone_login,
        contract_list,
        compensation_charge,
        compensation_cancel,
        marketing_consent_apply,
        marketing_consent_withdraw,
    ):
        assert callable(getattr(module, "run", None)) or hasattr(module, "request_sms")


def test_hom_compensation_constants_importable():
    from app.automation.scenarios.rep_homepage.constants import (
        CLAIM_CONTENT_TEXT,
        TARGET_CLAIM_TEXT,
        TARGET_CLAIM_TEXT_TRUNCATED,
    )

    assert CLAIM_CONTENT_TEXT in TARGET_CLAIM_TEXT
    assert TARGET_CLAIM_TEXT.startswith(TARGET_CLAIM_TEXT_TRUNCATED)
