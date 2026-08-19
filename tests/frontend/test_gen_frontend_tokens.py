from app.core.enums import ModuleStatus, RunStatus
from app.core.status_labels import (
    MODULE_STATUS_LABELS,
    STATUS_TONES,
    module_status_badge_tone,
    run_status_badge_tone,
)
from scripts.gen_frontend_tokens import build_tone_map, render_css, render_ts

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


def test_tone_map_covers_every_run_and_module_status():
    """톤 규칙은 파이썬이 SSOT — 프론트가 손으로 다시 적지 않는다."""
    tone_map = build_tone_map()
    for status in RunStatus:
        assert tone_map[status.value.lower()] == run_status_badge_tone(status), status
    for status in ModuleStatus:
        assert tone_map[status.value.lower()] == module_status_badge_tone(status), status


def test_tone_map_has_no_run_module_conflict():
    """두 축이 겹치는 키는 값이 같아야 병합이 안전하다(달라지면 생성기가 죽는다)."""
    run_tones = {s.value.lower(): run_status_badge_tone(s) for s in RunStatus}
    module_tones = {s.value.lower(): module_status_badge_tone(s) for s in ModuleStatus}
    overlap = set(run_tones) & set(module_tones)
    assert overlap, "두 축이 전혀 겹치지 않으면 이 테스트의 전제가 무너진 것이다"
    for key in sorted(overlap):
        assert run_tones[key] == module_tones[key], key


def test_tone_map_values_are_all_declared_tones():
    for key, tone in build_tone_map().items():
        assert tone in STATUS_TONES, (key, tone)


def test_ts_emits_status_tone_map():
    ts = render_ts()
    assert "export const STATUS_TONE_MAP: Record<string, StatusTone> = {" in ts
    # 손으로 적혀 있던 TONE_ALIASES 가 덮던 항목이 실제로 생성물에 있는지 확인
    assert '"failed": "anomaly",' in ts
    assert '"queued": "pending",' in ts
    assert '"waiting_input": "waiting_input",' in ts
    assert '"skipped": "skipped",' in ts
    assert '"cancelled": "cancelled",' in ts


def test_ts_tone_map_keys_are_lowercase():
    ts = render_ts()
    for status in RunStatus:
        assert f'"{status.value.lower()}": ' in ts, status


def test_generated_files_carry_do_not_edit_banner():
    for text in (render_css(), render_ts()):
        assert "자동 생성" in text
        assert "scripts/gen_frontend_tokens.py" in text
