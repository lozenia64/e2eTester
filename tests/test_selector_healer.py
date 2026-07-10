"""셀렉터 치유 순수 로직(파싱·힌트·스코어링) 단위 테스트 — 브라우저·DB·I/O 없음."""

from __future__ import annotations

from app.healing.selector_healer import (
    build_candidate_selector,
    extract_hints,
    parse_broken_selector,
    score_candidates,
)

# --- 오류 메시지에서 깨진 셀렉터 추출 ---------------------------------------


def test_parse_selector_from_timeout_error():
    error = (
        'Page.click: Timeout 30000ms exceeded.\nCall log:\nwaiting for locator("#btnRA")\n'
    )
    assert parse_broken_selector(error) == "#btnRA"


def test_parse_takes_last_locator_in_frame_chain():
    error = (
        "Timeout 30000ms exceeded.\n"
        'waiting for frame_locator("[id^=\\"__POP_ID_\\"] iframe").locator("#smsNum")'
    )
    assert parse_broken_selector(error) == "#smsNum"


def test_parse_waiting_for_selector_style():
    assert parse_broken_selector('waiting for selector "#firstId" to be visible') == "#firstId"


def test_parse_returns_none_for_non_selector_failure():
    assert parse_broken_selector("net::ERR_CONNECTION_REFUSED at https://example.com") is None
    assert parse_broken_selector("로그인 후 메인화면으로 이동하지 못했습니다.") is None


# --- 힌트 추출 ---------------------------------------------------------------


def test_extract_hints_from_id_selector():
    hints = extract_hints("#btnSMS")
    assert hints.element_id == "btnSMS"


def test_extract_hints_from_composite_selector():
    hints = extract_hints('button.submit:has-text("인증번호 받기")')
    assert hints.tag == "button"
    assert hints.text == "인증번호 받기"
    assert "submit" in hints.classes


def test_extract_hints_name_and_prefix():
    assert extract_hints('input[name="userId"]').name == "userId"
    assert extract_hints('[id^="__POP_ID_"] iframe').id_prefix == "__POP_ID_"


# --- 후보 스코어링 -----------------------------------------------------------


def _candidate(**overrides):
    base = {
        "tag": "button",
        "id": "",
        "name": "",
        "role": "",
        "aria": "",
        "cls": "",
        "text": "",
        "type": "",
        "visible": True,
    }
    return base | overrides


def test_renamed_id_scores_highest():
    hints = extract_hints("#btnRA")
    candidates = [
        _candidate(id="btnRA2", text="로그인"),
        _candidate(id="btnCancel", text="취소"),
        _candidate(tag="a", text="회원가입"),
    ]
    scored = score_candidates(hints, candidates)
    assert scored
    assert scored[0].selector == "#btnRA2"
    assert scored[0].confidence >= 0.8


def test_text_match_finds_moved_button():
    hints = extract_hints('button:has-text("인증번호 받기")')
    scored = score_candidates(
        hints,
        [
            _candidate(id="newSmsBtn", text="인증번호 받기"),
            _candidate(id="btnOk", text="확인"),
        ],
    )
    assert scored[0].selector == "#newSmsBtn"
    assert scored[0].confidence >= 0.9


def test_invisible_candidate_is_penalized():
    hints = extract_hints('button:has-text("확인")')
    visible = score_candidates(hints, [_candidate(id="a", text="확인", visible=True)])
    hidden = score_candidates(hints, [_candidate(id="a", text="확인", visible=False)])
    assert visible[0].confidence > hidden[0].confidence


def test_id_moved_to_name_attribute():
    hints = extract_hints("#userId")
    scored = score_candidates(hints, [_candidate(tag="input", id="", name="userId")])
    assert scored[0].selector == 'input[name="userId"]'
    assert scored[0].confidence >= 0.8


# --- 후보 → 셀렉터 문자열 -----------------------------------------------------


def test_build_selector_prefers_id_then_name_then_text():
    assert build_candidate_selector(_candidate(id="btnOk")) == "#btnOk"
    assert build_candidate_selector(_candidate(name="otp")) == 'button[name="otp"]'
    assert (
        build_candidate_selector(_candidate(text="다음에 할게요"))
        == 'button:has-text("다음에 할게요")'
    )
    assert build_candidate_selector(_candidate()) is None
