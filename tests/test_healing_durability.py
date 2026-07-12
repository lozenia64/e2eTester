"""셀렉터 내구성 맵(정적 스캔 + 치유 이력 결합, 순수 빌더) 단위 테스트."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.contexts.healing.durability import (
    build_durability_map,
    classify_selector,
    extract_selector_refs,
    system_of_path,
)
from app.contexts.healing.models import HealingAction, HealingEvent

SAMPLE_SOURCE = """
USER_ID_SELECTOR = "#firstId"
LOGIN_BUTTON_SELECTOR = "#btnRA"
AUTH_POPUP_IFRAME = '[id^="__POP_ID_"] iframe'
NOT_A_SELECTOR = "인증번호는 4~8자리 숫자여야 합니다."


def run(page):
    page.locator("#smsNum").fill("123456")
    frame.locator('button:has-text("다음에 할게요")').click()
    page.get_by_role("button", name="확인").click()
"""


def test_extract_refs_finds_constants_inline_and_roles():
    refs = extract_selector_refs("app/automation/page_objects/hrp/login.py", SAMPLE_SOURCE)
    selectors = {r["selector"] for r in refs}
    assert "#firstId" in selectors
    assert "#btnRA" in selectors
    assert '[id^="__POP_ID_"] iframe' in selectors
    assert "#smsNum" in selectors
    assert 'button:has-text("다음에 할게요")' in selectors
    assert 'role=button[name="확인"]' in selectors
    # 한글 안내 문구는 셀렉터가 아니다.
    assert "인증번호는 4~8자리 숫자여야 합니다." not in selectors


def test_classification_grades():
    assert classify_selector("#btnRA")[1] == "green"
    assert classify_selector('role=button[name="확인"]')[1] == "green"
    assert classify_selector('input[name="userId"]')[1] == "green"
    assert classify_selector("button.btn-primary")[1] == "amber"
    assert classify_selector('button:has-text("다음에 할게요")')[1] == "red"
    assert classify_selector("li >> nth=3")[1] == "red"
    assert classify_selector("//div[3]/span")[1] == "red"


def test_auto_generated_looking_id_is_downgraded():
    score, grade, notes = classify_selector("#cmp1234_btn")
    assert grade == "amber"
    assert any("자동 생성" in note for note in notes)


def test_system_inference_from_path():
    assert system_of_path("app/automation/page_objects/hrp/login.py") == "hrp"
    assert system_of_path("app/systems/access_common/browser.py") == "공용(access_common)"
    assert system_of_path("app/scenarios/rep_homepage/constants.py").startswith("공용(rep_homepage")


def _event(broken: str) -> HealingEvent:
    return HealingEvent(
        event_id=uuid4().hex,
        run_id="r1",
        module_id="login",
        system_code="hrp",
        broken_selector=broken,
        action=HealingAction.AUTO_HEALED,
        retry_succeeded=True,
        created_at=datetime(2026, 7, 10, tzinfo=UTC),
    )


def test_durability_map_combines_scan_with_heal_history():
    sources = {"app/automation/page_objects/hrp/login.py": SAMPLE_SOURCE}
    events = [_event("#btnRA")] * 3
    result = build_durability_map(sources, events)

    btn_row = next(r for r in result["rows"] if r["selector"] == "#btnRA")
    assert btn_row["heal_count"] == 3
    assert btn_row["chronic"] is True
    # 안정적(#id)이어도 3회 깨졌으면 위험 순위가 취약 텍스트 셀렉터보다 위로 온다.
    assert result["top_risky"][0]["selector"] == "#btnRA"
    assert [r["selector"] for r in result["needs_repair"]] == ["#btnRA"]
    assert result["summary"]["green"] >= 2
    assert result["summary"]["red"] >= 1
