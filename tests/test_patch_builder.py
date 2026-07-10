"""셀렉터 오토픽스 패치 제안(순수 빌더) 단위 테스트."""

from __future__ import annotations

from app.healing.patch_builder import apply_replacement, build_patch_drafts

SOURCE = '''LOGIN_BUTTON_SELECTOR = "#btnRA"


def submit(page):
    page.locator("#btnRA").click()
    page.locator('#btnRA').click()
'''


def test_apply_replacement_handles_both_quote_styles():
    replaced, count = apply_replacement(SOURCE, "#btnRA", "#btnRA2")
    assert count == 3
    assert '"#btnRA2"' in replaced
    assert "'#btnRA2'" in replaced
    assert "#btnRA\"" not in replaced.replace("#btnRA2", "")


def test_apply_replacement_switches_quote_when_healed_contains_double_quote():
    source = "SEL = '#a'\n"
    replaced, count = apply_replacement(source, "#a", 'button:has-text("확인")')
    assert count == 1
    # 작은따옴표 리터럴이었지만 대체 셀렉터에 " 가 있어도 유효한 리터럴이 된다.
    assert "button:has-text(\"확인\")" in replaced


def test_apply_replacement_escapes_when_healed_contains_both_quote_styles():
    source = 'S = "#old"\n'
    healed = 'text="ok" and id=\'x\''
    replaced, count = apply_replacement(source, "#old", healed)
    assert count == 1
    # 큰따옴표 리터럴 안의 " 와 \\ 가 escape 되어 문법적으로 유효하다.
    assert replaced == 'S = "text=\\"ok\\" and id=\'x\'"\n'


def test_no_occurrence_returns_zero():
    _, count = apply_replacement(SOURCE, "#missing", "#x")
    assert count == 0


def test_build_patch_drafts_produces_unified_diff_per_file():
    sources = {
        "app/systems/hrp/steps/login.py": SOURCE,
        "app/systems/fp/steps/other.py": "X = '#unrelated'\n",
    }
    drafts = build_patch_drafts(sources, broken_selector="#btnRA", healed_selector="#btnRA2")

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.file_path == "app/systems/hrp/steps/login.py"
    assert draft.occurrences == 3
    assert "--- a/app/systems/hrp/steps/login.py" in draft.diff
    assert '-LOGIN_BUTTON_SELECTOR = "#btnRA"' in draft.diff
    assert '+LOGIN_BUTTON_SELECTOR = "#btnRA2"' in draft.diff


def test_fragile_replacement_gets_tech_debt_warning():
    drafts = build_patch_drafts(
        {"a.py": 'S = "#old"\n'},
        broken_selector="#old",
        healed_selector='div:has-text("확인") >> nth=0',
    )
    assert drafts
    warnings = " ".join(drafts[0].warnings)
    assert "취약 패턴" in warnings
    assert "nth=0" in warnings


def test_stable_replacement_has_no_warning():
    drafts = build_patch_drafts(
        {"a.py": 'S = "#old"\n'}, broken_selector="#old", healed_selector="#newId"
    )
    assert drafts[0].warnings == []
