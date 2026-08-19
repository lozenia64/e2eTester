from app.core.status_labels import MODULE_STATUS_LABELS, STATUS_TONES
from scripts.gen_frontend_tokens import render_css, render_ts

VARIANTS = ("solid", "surface", "text", "border")


def test_css_declares_every_tone_and_variant():
    css = render_css()
    for tone in STATUS_TONES:
        for variant in VARIANTS:
            assert f"--st-{tone}-{variant}:" in css, (tone, variant)


def test_css_has_no_dark_mode_branch():
    """라이트 단일 팔레트 — 테마 분기를 만들지 않는다."""
    css = render_css()
    assert "prefers-color-scheme" not in css
    assert "[data-theme" not in css


def test_ts_union_matches_status_tones():
    ts = render_ts()
    expected = " | ".join(f'"{tone}"' for tone in STATUS_TONES)
    assert f"export type StatusTone = {expected};" in ts


def test_ts_carries_korean_module_labels():
    ts = render_ts()
    assert '"passed": "정상"' in ts
    assert '"error": "점검실패"' in ts
    # 파이썬 라벨과 실제로 같은 출처인지 확인
    assert MODULE_STATUS_LABELS[list(MODULE_STATUS_LABELS)[0]] in ts


def test_ts_label_keys_are_lowercase():
    """enum 값은 대문자지만 프론트 규약은 소문자다. 생성 시점에 맞춘다."""
    ts = render_ts()
    assert '"PASSED"' not in ts
    assert '"waiting_input": "입력 대기"' in ts


def test_generated_files_carry_do_not_edit_banner():
    for text in (render_css(), render_ts()):
        assert "자동 생성" in text
        assert "scripts/gen_frontend_tokens.py" in text
