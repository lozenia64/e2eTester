"""E2E 테스트 결과 보고서 메일의 '고정 디자인' HTML 렌더러.

이 모듈은 메일 본문 HTML 을 **결정적으로(deterministic)** 생성한다. Gemini 는
레이아웃/CSS 를 만들지 않고 분석 '콘텐츠'(핵심 요약, 화면/로그 관찰, 실패 분석)만
구조화 JSON 으로 돌려주며(`app/notifications/run_completion_email.py` 의
`GeminiReportContentComposer` 참고), 실제 시각 디자인은 전부 여기 박혀 있는 토큰과
컴포넌트로 찍어낸다. 따라서 Gemini 응답이 매번 달라지거나 아예 비어 있어도(=AI 비활성/
실패) 메일 레이아웃·색·간격은 **항상 동일**하고, AI 서술 문구만 채워지거나 비워진다.

`ai_content` dict 스키마(없는 키는 모두 선택적이며, 비면 결정적 기본값으로 대체된다):
  run  : {headline, comparison_comment,
          module_findings:[{module_id, screen_observation, log_observation}],
          failure_details:[{module_id, symptom, evidence, probable_cause, recommended_action}]}
  suite: {headline,
          systems:[{system_code, summary,
                    module_findings:[...], failure_details:[...]}]}
"""

from __future__ import annotations

from html import escape

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.status_labels import (
    MODULE_STATUS_LABELS,
    RUN_STATUS_LABELS,
    SUITE_STATUS_LABELS,
)

# --- 디자인 토큰 (이 값만 바꾸면 전체 메일 룩앤필이 일관되게 바뀐다) -----------------
FONT_STACK = "Arial,'Noto Sans KR','Malgun Gothic',sans-serif"
PAGE_BG = "#f4f5f7"
CARD_BG = "#ffffff"
INK = "#1f2328"
MUTED = "#6b7280"
BORDER = "#e5e7eb"
SOFT_BG = "#f7f8fa"
LABEL_BG = "#f4f6f8"

PASS_COLOR = "#2f8f4e"
PASS_SOFT_BG = "#e9f6ee"
FAIL_COLOR = "#c0392b"
FAIL_SOFT_BG = "#fdecea"
WARN_COLOR = "#b7791f"
WARN_SOFT_BG = "#fdf6e3"
NEUTRAL_COLOR = "#6b7280"
NEUTRAL_SOFT_BG = "#f1f3f5"
INFO_COLOR = "#2563eb"
INFO_SOFT_BG = "#eef3ff"

# --- 스크린샷 크기 규칙 -------------------------------------------------------------
# Outlook(윈도우)은 Word 렌더링 엔진이라 CSS max-width/height 를 무시하고 HTML
# width/height '속성'만 존중한다. 따라서 스크린샷은 실제 픽셀 크기를 읽어 px 속성으로
# 고정해야 모든 클라이언트에서 같은 크기로 나온다. Outlook 은 96dpi 기준이므로
# 높이 상한 11cm = 11 / 2.54 * 96 ≈ 416px.
SCREENSHOT_MAX_HEIGHT_PX = 416
# 가로형(PC) 스크린샷 1장 배치 시 최대 표시 너비.
SCREENSHOT_FULL_MAX_WIDTH_PX = 600
# 세로형(모바일) 스크린샷은 가로 2장 배치하므로 셀 폭에 맞는 최대 표시 너비.
SCREENSHOT_PAIR_MAX_WIDTH_PX = 280

_STATUS_LABELS = (
    {key.value: value for key, value in MODULE_STATUS_LABELS.items()}
    | {key.value: value for key, value in RUN_STATUS_LABELS.items()}
    | {key.value: value for key, value in SUITE_STATUS_LABELS.items()}
)

_STATUS_COLORS = {
    ModuleStatus.PASSED.value: PASS_COLOR,
    ModuleStatus.ANOMALY.value: WARN_COLOR,
    ModuleStatus.ERROR.value: FAIL_COLOR,
    ModuleStatus.FAILED.value: WARN_COLOR,
    ModuleStatus.BLOCKED.value: WARN_COLOR,
    ModuleStatus.SKIPPED.value: NEUTRAL_COLOR,
    ModuleStatus.CANCELLED.value: NEUTRAL_COLOR,
    ModuleStatus.WAITING_INPUT.value: WARN_COLOR,
    RunStatus.PASSED.value: PASS_COLOR,
    RunStatus.ANOMALY.value: WARN_COLOR,
    RunStatus.ERROR.value: FAIL_COLOR,
    RunStatus.FAILED.value: WARN_COLOR,
    RunStatus.CANCELLED.value: NEUTRAL_COLOR,
    SuiteStatus.PASSED.value: PASS_COLOR,
    SuiteStatus.ANOMALY.value: WARN_COLOR,
    SuiteStatus.ERROR.value: FAIL_COLOR,
    SuiteStatus.FAILED.value: WARN_COLOR,
    SuiteStatus.SKIPPED.value: NEUTRAL_COLOR,
    SuiteStatus.CANCELLED.value: NEUTRAL_COLOR,
}


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status)


def _status_color(status: str) -> str:
    return _STATUS_COLORS.get(status, NEUTRAL_COLOR)


def _status_soft_bg(status: str) -> str:
    if status in {RunStatus.PASSED.value, SuiteStatus.PASSED.value, ModuleStatus.PASSED.value}:
        return PASS_SOFT_BG
    if status in {RunStatus.ERROR.value, SuiteStatus.ERROR.value, ModuleStatus.ERROR.value}:
        return FAIL_SOFT_BG
    if status in {
        RunStatus.ANOMALY.value,
        SuiteStatus.ANOMALY.value,
        ModuleStatus.ANOMALY.value,
        RunStatus.FAILED.value,
        ModuleStatus.FAILED.value,
    }:
        return WARN_SOFT_BG
    return NEUTRAL_SOFT_BG


def _is_passed(status: str) -> bool:
    return status in {RunStatus.PASSED.value, SuiteStatus.PASSED.value, ModuleStatus.PASSED.value}


def _text(value: object, fallback: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return escape(text) if text else fallback


# --- 공통 컴포넌트 ----------------------------------------------------------------
def _shell(title_html: str, body_html: str) -> str:
    """페이지 배경 + 가운데 정렬된 960px 카드로 본문을 감싼다.

    모듈명/비고 같은 표 내용이 가로로 충분히 펼쳐지도록 카드 폭을 넓게 잡는다.
    """
    return (
        f'<div style="margin:0;padding:24px 12px;background:{PAGE_BG};'
        f'font-family:{FONT_STACK};color:{INK};line-height:1.6;">'
        f'<div style="max-width:960px;margin:0 auto;background:{CARD_BG};'
        f'border:1px solid {BORDER};border-radius:18px;overflow:hidden;">'
        f'<div style="padding:28px 28px 8px;">{title_html}</div>'
        f'<div style="padding:0 28px 28px;">{body_html}</div>'
        "</div></div>"
    )


def _status_badge(status: str, status_label: str) -> str:
    passed = _is_passed(status)
    color = PASS_COLOR if passed else FAIL_COLOR
    if status in {RunStatus.CANCELLED.value, SuiteStatus.CANCELLED.value}:
        color = NEUTRAL_COLOR
    return (
        f'<span style="display:inline-block;padding:5px 14px;border-radius:999px;'
        f"background:{color};color:#ffffff;font-size:13px;font-weight:700;"
        f'vertical-align:middle;">{escape(status_label)} ({escape(status.upper())})</span>'
    )


def _title_block(title: str, status: str, status_label: str, subtitle: str) -> str:
    accent = PASS_COLOR if _is_passed(status) else FAIL_COLOR
    if status in {RunStatus.CANCELLED.value, SuiteStatus.CANCELLED.value}:
        accent = NEUTRAL_COLOR
    return (
        f'<div style="border-bottom:3px solid {accent};padding-bottom:16px;">'
        f'<div style="font-size:22px;font-weight:800;color:{INK};margin-bottom:10px;">'
        f"{escape(title)}</div>"
        f"<div>{_status_badge(status, status_label)}"
        f'<span style="margin-left:10px;font-size:13px;color:{MUTED};">{escape(subtitle)}</span>'
        "</div></div>"
    )


def _section(number: int, title: str, body_html: str, accent: str = PASS_COLOR) -> str:
    return (
        f'<h3 style="margin:26px 0 12px;padding-left:11px;border-left:4px solid {accent};'
        f'font-size:16px;font-weight:700;color:{INK};line-height:1.35;">'
        f"{number}. {escape(title)}</h3>{body_html}"
    )


def _kpi_cards(cards: list[tuple[str, str, str]]) -> str:
    """[(label, value, value_color), ...] → 균등 너비 KPI 카드 행."""
    width = f"{100 // max(len(cards), 1)}%"
    cells = "".join(
        (
            f'<td width="{width}" style="background:{SOFT_BG};border:1px solid {BORDER};'
            'border-radius:12px;padding:14px 10px;text-align:center;vertical-align:top;">'
            f'<div style="font-size:12px;color:{MUTED};margin-bottom:6px;">{escape(label)}</div>'
            f'<div style="font-size:24px;font-weight:800;color:{value_color};">{escape(value)}</div>'
            "</td>"
        )
        for label, value, value_color in cards
    )
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        'style="border-collapse:separate;border-spacing:8px;margin:0 -8px;"><tr>'
        f"{cells}</tr></table>"
    )


def _callout(text_html: str, accent: str, bg: str) -> str:
    return (
        f'<div style="margin-top:4px;padding:14px 16px;background:{bg};'
        f'border-left:4px solid {accent};border-radius:0 10px 10px 0;font-size:14px;">'
        f"{text_html}</div>"
    )


def _info_table(rows: list[tuple[str, str, str, str]]) -> str:
    """4열(라벨/값/라벨/값) 메타데이터 표. 값에는 이미 escape 된 HTML 을 넣는다."""
    label_style = (
        f"padding:10px 12px;background:{LABEL_BG};border:1px solid {BORDER};"
        f"font-size:13px;font-weight:600;color:{MUTED};white-space:nowrap;width:18%;"
    )
    value_style = (
        f"padding:10px 12px;border:1px solid {BORDER};font-size:13px;color:{INK};width:32%;"
    )
    body = "".join(
        (
            "<tr>"
            f'<td style="{label_style}">{escape(left_label)}</td>'
            f'<td style="{value_style}">{left_value}</td>'
            f'<td style="{label_style}">{escape(right_label)}</td>'
            f'<td style="{value_style}">{right_value}</td>'
            "</tr>"
        )
        for left_label, left_value, right_label, right_value in rows
    )
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="border-collapse:collapse;">{body}</table>'
    )


def _module_table(modules: list[dict]) -> str:
    head = (
        f'<thead><tr style="background:{SOFT_BG};">'
        + "".join(
            f'<th style="text-align:{align};padding:10px 12px;border-bottom:2px solid {BORDER};'
            f'font-size:12px;color:{MUTED};font-weight:700;{extra}">{escape(label)}</th>'
            for label, align, extra in (
                ("순번", "center", "width:48px;"),
                ("모듈명", "left", "white-space:nowrap;"),
                ("상태", "center", "width:72px;"),
                ("소요시간", "right", "width:88px;"),
                ("비고", "left", ""),
            )
        )
        + "</tr></thead>"
    )
    rows = []
    for module in modules:
        status = module["status"]
        color = _status_color(status)
        label = module.get("status_label") or _status_label(status)
        dim = (
            ""
            if status not in {ModuleStatus.SKIPPED.value, ModuleStatus.CANCELLED.value}
            else f"color:{MUTED};"
        )
        # 자동 복구 가시성(설계 §3.4) — 통과했지만 재시도를 거쳤음을 알린다(주의 계열,
        # 실패 계열 아님). plain-text 본문의 "자동 복구된 모듈: ..." 문구와 같은 어휘.
        recovery_badge = (
            f'<br><span style="display:inline-block;margin-top:4px;padding:2px 8px;'
            f'border-radius:999px;background:{WARN_SOFT_BG};color:{WARN_COLOR};'
            f'font-size:11px;font-weight:700;">자동 복구됨 '
            f'({module.get("retry_count") or 0}회 재시도)</span>'
            if module.get("recovered")
            else ""
        )
        rows.append(
            "<tr>"
            f'<td style="padding:10px 12px;border-bottom:1px solid {BORDER};text-align:center;'
            f'font-size:13px;{dim}">{module["seq"]}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid {BORDER};font-size:13px;'
            f'font-weight:600;white-space:nowrap;{dim}">{_text(module["module_name"])}'
            f"{recovery_badge}</td>"
            f'<td style="padding:10px 12px;border-bottom:1px solid {BORDER};text-align:center;'
            f'font-size:13px;font-weight:700;color:{color};">{escape(label)}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid {BORDER};text-align:right;'
            f'font-size:13px;white-space:nowrap;{dim}">{_text(module.get("duration_text"), "-")}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid {BORDER};font-size:13px;'
            f'color:{MUTED};word-break:break-all;">{_text(module.get("message"), "-")}</td>'
            "</tr>"
        )
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="border-collapse:collapse;border:1px solid {BORDER};border-radius:10px;">'
        f"{head}<tbody>{''.join(rows)}</tbody></table>"
    )


def _observation_list(
    modules: list[dict], findings: dict[str, dict], key: str, empty_text: str
) -> str:
    items = []
    for module in modules:
        observation = (findings.get(module["module_id"], {}).get(key) or "").strip()
        if not observation:
            continue
        items.append(
            f'<li style="margin-bottom:10px;"><strong>{_text(module["module_name"])}</strong> '
            f'<span style="color:{MUTED};font-size:12px;">(순번 {module["seq"]})</span><br>'
            f'<span style="color:{INK};">{escape(observation.strip())}</span></li>'
        )
    if not items:
        return f'<div style="font-size:13px;color:{MUTED};">{escape(empty_text)}</div>'
    return f'<ul style="margin:0;padding-left:18px;font-size:14px;">{"".join(items)}</ul>'


def _failure_cards(
    modules_by_id: dict[str, dict], failure_details: list[dict], failed_modules: list[dict]
) -> str:
    detail_by_id = {
        item.get("module_id"): item for item in failure_details if item.get("module_id")
    }
    cards = []
    for failed in failed_modules:
        module_id = failed["module_id"]
        detail = detail_by_id.get(module_id, {})
        rows = []
        for label, value in (
            ("증상", detail.get("symptom") or failed.get("message")),
            ("근거", detail.get("evidence")),
            ("추정 원인", detail.get("probable_cause") or failed.get("analysis_summary")),
            ("권장 조치", detail.get("recommended_action") or failed.get("recommended_action")),
        ):
            text = str(value).strip() if value else ""
            if not text:
                continue
            rows.append(
                f'<div style="margin-top:6px;"><span style="display:inline-block;width:72px;'
                f'color:{MUTED};font-size:12px;vertical-align:top;">{escape(label)}</span>'
                f'<span style="font-size:13px;color:{INK};">{escape(text)}</span></div>'
            )
        body = (
            "".join(rows)
            or f'<div style="font-size:13px;color:{MUTED};">추가 분석 정보가 없습니다.</div>'
        )
        name = modules_by_id.get(module_id, {}).get(
            "module_name", failed.get("module_name", module_id)
        )
        cards.append(
            f'<div style="margin-top:12px;padding:14px 16px;background:{FAIL_SOFT_BG};'
            f'border:1px solid rgba(192,57,43,0.22);border-radius:12px;">'
            f'<div style="font-size:14px;font-weight:700;color:{FAIL_COLOR};">{_text(name)} '
            f'<span style="color:{MUTED};font-weight:400;font-size:12px;">({escape(module_id)})</span></div>'
            f"{body}</div>"
        )
    return "".join(cards)


def _comparison_block(comparison: dict, comment: str) -> str:
    if not comparison.get("has_baseline"):
        return _callout(
            f'<span style="color:{MUTED};">이전 실행 이력(Baseline)이 없어 직전 실행 대비 변화 분석 대상에서 제외되었습니다.</span>',
            NEUTRAL_COLOR,
            NEUTRAL_SOFT_BG,
        )
    parts = []
    if comment.strip():
        parts.append(f'<div style="margin-bottom:8px;color:{INK};">{escape(comment.strip())}</div>')
    parts.append(
        f'<div style="font-size:12px;color:{MUTED};">기준 Run: <code>'
        f"{_text(comparison.get('baseline_run_id'), '-')}</code> ({_text(comparison.get('baseline_requested_at'), '-')})</div>"
    )
    for label, names, color in (
        ("새 이상징후", comparison.get("newly_failed") or [], WARN_COLOR),
        ("복구됨", comparison.get("recovered") or [], PASS_COLOR),
        ("지속 이상징후", comparison.get("still_failing") or [], WARN_COLOR),
    ):
        if not names:
            continue
        parts.append(
            f'<div style="margin-top:6px;font-size:13px;"><strong style="color:{color};">'
            f"{escape(label)} {len(names)}건</strong>: {escape(', '.join(names))}</div>"
        )
    if not (
        comparison.get("newly_failed")
        or comparison.get("recovered")
        or comparison.get("still_failing")
    ):
        parts.append(
            f'<div style="margin-top:6px;font-size:13px;color:{MUTED};">직전 실행과 비교해 모듈 상태 변화가 없습니다.</div>'
        )
    return _callout("".join(parts), INFO_COLOR, INFO_SOFT_BG)


def _omitted_warning(email_summary: dict, gemini_summary: dict) -> str:
    blocks = []
    for title, entries in (
        ("메일 첨부에서 제외된 파일", email_summary.get("omitted") or []),
        ("AI 분석 입력에서 제외된 파일", gemini_summary.get("omitted") or []),
    ):
        if not entries:
            continue
        items = "".join(
            f"<li><code>{escape(entry['path'])}</code> — {escape(entry['reason'])}</li>"
            for entry in entries
        )
        blocks.append(
            f'<div style="margin-top:12px;padding:12px 14px;background:{WARN_SOFT_BG};'
            f'border:1px solid rgba(183,121,31,0.25);border-radius:10px;">'
            f'<strong style="display:block;margin-bottom:6px;color:{WARN_COLOR};">{escape(title)}</strong>'
            f'<ul style="margin:0;padding-left:18px;font-size:13px;">{items}</ul></div>'
        )
    return "".join(blocks)


def _screenshot_display_size(
    width: int, height: int, max_width: int = SCREENSHOT_FULL_MAX_WIDTH_PX
) -> tuple[int, int]:
    """원본 픽셀 크기를 높이 상한(11cm≈416px)·너비 상한에 맞게 비율 유지 축소한다.

    확대는 하지 않는다(원본보다 작을 때 늘리면 흐려진다).
    """
    scale = min(SCREENSHOT_MAX_HEIGHT_PX / height, max_width / width, 1.0)
    return max(1, round(width * scale)), max(1, round(height * scale))


def _screenshot_image_html(
    image_src: str, module_title: str, display_size: tuple[int, int] | None = None
) -> str:
    """Outlook 호환 CID 이미지 마크업.

    원본 크기를 알면 축소 계산한 px 를 width/height '속성'으로 고정한다(Outlook 은
    CSS 크기를 무시하므로 속성이 유일하게 확실한 수단). 크기를 모르면 기존처럼
    너비 600px 기준으로 렌더링한다.
    """
    safe_title = escape(module_title)
    safe_src = image_src.replace('"', "")
    if display_size is None:
        size_attrs = 'width="600"'
        size_style = "width:100%;max-width:600px;height:auto;"
    else:
        display_width, display_height = display_size
        size_attrs = f'width="{display_width}" height="{display_height}"'
        size_style = f"width:{display_width}px;height:{display_height}px;"
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        'style="border-collapse:collapse;"><tr><td align="center" '
        f'style="padding:0;line-height:0;font-size:0;background:{SOFT_BG};">'
        f'<img src="{safe_src}" alt="{safe_title} 스크린샷" {size_attrs} border="0" '
        f'style="display:inline-block;{size_style}border:0;outline:none;'
        f'text-decoration:none;-ms-interpolation-mode:bicubic;" />'
        "</td></tr></table>"
    )


def _screenshot_original_size(screenshot: dict) -> tuple[int, int] | None:
    width = screenshot.get("image_width")
    height = screenshot.get("image_height")
    if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
        return width, height
    return None


def _is_portrait_screenshot(screenshot: dict) -> bool:
    size = _screenshot_original_size(screenshot)
    return size is not None and size[1] > size[0]


def _screenshot_card(
    screenshot: dict,
    observation: str = "",
    max_image_width: int = SCREENSHOT_FULL_MAX_WIDTH_PX,
) -> str:
    """모듈별 CID 인라인 스크린샷 카드."""
    status = screenshot.get("status") or ""
    status_label = screenshot.get("status_label") or _status_label(status)
    accent = _status_color(status) if status else INFO_COLOR
    module_title = _text(screenshot.get("module_name"))
    seq = screenshot.get("seq", "-")
    cid = (screenshot.get("cid") or "").strip()
    if not cid:
        return ""
    image_src = f"cid:{cid}"
    original_size = _screenshot_original_size(screenshot)
    display_size = (
        _screenshot_display_size(*original_size, max_width=max_image_width)
        if original_size
        else None
    )
    observation_html = ""
    if observation.strip():
        observation_html = (
            f'<div style="margin-top:10px;padding:10px 12px;background:{SOFT_BG};'
            f'border-radius:8px;font-size:13px;color:{INK};line-height:1.5;">'
            f'<span style="display:block;font-size:11px;font-weight:700;color:{MUTED};'
            f'margin-bottom:4px;text-transform:uppercase;letter-spacing:0.04em;">AI 화면 관찰</span>'
            f"{escape(observation.strip())}</div>"
        )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="border-collapse:separate;border-spacing:0;margin-bottom:16px;">'
        f'<tr><td style="padding:0;border:1px solid {BORDER};border-radius:14px;overflow:hidden;'
        f'background:{CARD_BG};">'
        f'<div style="height:4px;background:{accent};font-size:0;line-height:0;">&nbsp;</div>'
        f'<div style="padding:14px 16px 12px;">'
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f"<tr>"
        f'<td style="font-size:14px;font-weight:700;color:{INK};vertical-align:middle;">'
        f'<span style="display:inline-block;min-width:28px;color:{MUTED};font-weight:600;">#{seq}</span> '
        f"{module_title}</td>"
        f'<td align="right" style="vertical-align:middle;white-space:nowrap;">'
        f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:11px;'
        f'font-weight:700;color:{accent};background:{_status_soft_bg(status)};">'
        f"{escape(status_label)}</span></td>"
        f"</tr></table>"
        f'<div style="margin-top:12px;border:1px solid {BORDER};border-radius:10px;overflow:hidden;'
        f'background:{SOFT_BG};line-height:0;font-size:0;">'
        f"{_screenshot_image_html(image_src, module_title, display_size)}"
        f"</div>"
        f"{observation_html}"
        f"</div></td></tr></table>"
    )


def _screenshot_pair_row(left_card: str, right_card: str | None) -> str:
    """세로형(모바일) 스크린샷 카드 2장을 나란히 배치하는 2열 테이블 행.

    Outlook(Word 엔진)은 flexbox/float 를 지원하지 않으므로 테이블 셀 분할이
    유일하게 안전한 다단 배치 수단이다.
    """
    right_html = right_card if right_card else "&nbsp;"
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        'style="border-collapse:collapse;"><tr>'
        f'<td width="50%" valign="top" style="padding:0 6px 0 0;">{left_card}</td>'
        f'<td width="50%" valign="top" style="padding:0 0 0 6px;">{right_html}</td>'
        "</tr></table>"
    )


def _screenshot_gallery(
    inline_screenshots: list[dict],
    findings_by_module: dict | None = None,
    *,
    system_code: str | None = None,
) -> str:
    findings_by_module = findings_by_module or {}
    filtered = [
        item
        for item in inline_screenshots
        if not system_code or (item.get("system_code") or "").upper() == system_code.upper()
    ]
    if not filtered:
        return ""
    entries: list[tuple[bool, str]] = []
    for screenshot in sorted(filtered, key=lambda item: (item.get("order", 0), item.get("seq", 0))):
        module_id = screenshot.get("module_id") or ""
        observation = (findings_by_module.get(module_id) or {}).get("screen_observation", "")
        if isinstance(observation, str):
            observation_text = observation
        else:
            observation_text = ""
        portrait = _is_portrait_screenshot(screenshot)
        card = _screenshot_card(
            screenshot,
            observation_text,
            max_image_width=(
                SCREENSHOT_PAIR_MAX_WIDTH_PX if portrait else SCREENSHOT_FULL_MAX_WIDTH_PX
            ),
        )
        if card:
            entries.append((portrait, card))
    if not entries:
        return ""
    # 세로형(모바일) 카드는 연속 2장씩 나란히 묶어 상하 스크롤을 줄이고,
    # 가로형(PC) 카드는 가독성을 위해 한 장씩 전체 폭으로 배치한다.
    blocks: list[str] = []
    index = 0
    while index < len(entries):
        portrait, card = entries[index]
        if not portrait:
            blocks.append(card)
            index += 1
            continue
        next_card = None
        if index + 1 < len(entries) and entries[index + 1][0]:
            next_card = entries[index + 1][1]
            index += 1
        blocks.append(_screenshot_pair_row(card, next_card))
        index += 1
    return "".join(blocks)


def _attachment_notice_body(attachment: dict, gemini_summary: dict) -> str:
    return (
        f'<div style="font-size:14px;">본문 스크린샷 <strong>{attachment["inline_screenshot_count"]}건</strong> · '
        f"첨부 로그 <strong>{attachment['log_count']}건</strong></div>"
        + _omitted_warning(attachment, gemini_summary)
    )


def _footer() -> str:
    return (
        f'<hr style="margin:28px 0 14px;border:none;border-top:1px solid {BORDER};">'
        f'<div style="font-size:12px;color:{MUTED};">본 메일은 사내 E2E 자동화 테스트 플랫폼이 자동 발송한 메일입니다. '
        "회신하지 마세요.</div>"
    )


# --- Run 보고서 -------------------------------------------------------------------
def render_run_report_html(context: dict, ai_content: dict | None = None) -> str:
    ai = ai_content or {}
    run = context["run"]
    modules = context["modules"]
    modules_by_id = {module["module_id"]: module for module in modules}
    findings = {
        item["module_id"]: item
        for item in (ai.get("module_findings") or [])
        if item.get("module_id")
    }
    summary = context["module_summary"]
    passed = summary.get(ModuleStatus.PASSED.value, 0)
    anomaly = summary.get(ModuleStatus.ANOMALY.value, 0) + summary.get(ModuleStatus.FAILED.value, 0)
    error = summary.get(ModuleStatus.ERROR.value, 0)
    skipped = summary.get(ModuleStatus.SKIPPED.value, 0)
    executed = passed + anomaly + error
    pass_rate = f"{round(passed / executed * 100)}%" if executed else "-"
    accent = PASS_COLOR if _is_passed(run["status"]) else (FAIL_COLOR if error else WARN_COLOR)

    title = _title_block(
        f"[E2E] {run['system_name']} 테스트 결과 보고서",
        run["status"],
        run["status_label"],
        f"{run['system_code']} · {run['ended_at_kst']}",
    )

    kpi = _kpi_cards(
        [
            ("전체 모듈", str(len(modules)), INK),
            ("정상", str(passed), PASS_COLOR),
            ("이상징후", str(anomaly), WARN_COLOR if anomaly else MUTED),
            ("점검실패", str(error), FAIL_COLOR if error else MUTED),
            ("통과율", pass_rate, accent),
        ]
    )

    overview = _info_table(
        [
            (
                "Run ID",
                f"<code>{escape(run['run_id'])}</code>",
                "대상 시스템",
                f"{escape(run['system_name'])} ({escape(run['system_code'])})",
            ),
            (
                "요청 시각",
                escape(run["requested_at_kst"]),
                "실행 주체",
                escape(run["triggered_by"]),
            ),
            (
                "시작/종료",
                f"{escape(run['started_at_kst'])} ~ {escape(run['ended_at_kst'])}",
                "소요 시간",
                escape(run["duration_text"]),
            ),
            (
                "최종 상태",
                _status_badge(run["status"], run["status_label"]),
                "제외 모듈",
                f"{skipped}개",
            ),
        ]
    )

    headline = (ai.get("headline") or "").strip() or (
        f"{run['system_name']} 테스트가 {run['status_label']} 상태로 종료되었습니다. "
        f"전체 {len(modules)}개 모듈 중 {passed}개 정상, {anomaly}개 이상징후, {error}개 점검실패, {skipped}개 제외되었습니다."
    )

    sections = [
        _section(1, "실행 개요", kpi + '<div style="height:12px;"></div>' + overview, accent),
        _section(
            2,
            "핵심 요약",
            _callout(
                f'<span style="color:{INK};">{escape(headline)}</span>',
                accent,
                PASS_SOFT_BG if _is_passed(run["status"]) else FAIL_SOFT_BG,
            ),
            accent,
        ),
        _section(
            3,
            "직전 실행 대비 변화",
            _comparison_block(context["comparison"], ai.get("comparison_comment") or ""),
            INFO_COLOR,
        ),
        _section(4, "모듈별 결과", _module_table(modules), accent),
        _section(
            5,
            "모듈별 스크린샷",
            _screenshot_gallery(context.get("inline_screenshots") or [], findings)
            or f'<div style="font-size:13px;color:{MUTED};">본문에 포함할 스크린샷이 없습니다.</div>',
            accent,
        ),
        _section(
            6,
            "화면 검증 (스크린샷 분석)",
            _observation_list(
                modules, findings, "screen_observation", "분석할 스크린샷 자료가 없습니다."
            ),
            accent,
        ),
        _section(
            7,
            "로그 분석",
            _observation_list(modules, findings, "log_observation", "분석할 실행 로그가 없습니다."),
            accent,
        ),
    ]

    if context["failed_modules"]:
        sections.append(
            _section(
                8,
                "실패 상세 분석",
                _failure_cards(
                    modules_by_id, ai.get("failure_details") or [], context["failed_modules"]
                ),
                FAIL_COLOR,
            )
        )

    next_no = len(sections) + 1
    attachment = context["email_attachment_summary"]
    sections.append(
        _section(
            next_no,
            "첨부 및 제외 파일 안내",
            _attachment_notice_body(attachment, context["gemini_input_summary"]),
            accent,
        )
    )

    return _shell(title, "".join(sections) + _footer())


# --- Suite 보고서 -----------------------------------------------------------------
def render_suite_report_html(context: dict, ai_content: dict | None = None) -> str:
    ai = ai_content or {}
    suite = context["suite"]
    system_runs = context["system_runs"]
    ai_systems: dict[str, dict] = {}
    for item in ai.get("systems") or []:
        if not isinstance(item, dict):
            continue
        system_code = str(item.get("system_code") or "").strip().upper()
        if system_code:
            ai_systems[system_code] = item
    accent = PASS_COLOR if _is_passed(suite["status"]) else FAIL_COLOR

    title = _title_block(
        "[E2E] 전체 시스템 순차 점검 결과 보고서",
        suite["status"],
        suite["status_label"],
        f"SUITE · {suite['ended_at_kst']}",
    )

    kpi = _kpi_cards(
        [
            ("점검 시스템", str(suite["step_total"]), INK),
            ("통과", str(suite["step_passed"]), PASS_COLOR),
            (
                "이상징후",
                str(suite.get("step_anomaly", suite.get("step_failed", 0))),
                WARN_COLOR if suite.get("step_anomaly", suite.get("step_failed", 0)) else MUTED,
            ),
            (
                "점검실패",
                str(suite.get("step_error", 0)),
                FAIL_COLOR if suite.get("step_error", 0) else MUTED,
            ),
            ("소요 시간", suite["duration_text"], accent),
        ]
    )

    overview = _info_table(
        [
            (
                "Suite ID",
                f"<code>{escape(suite['suite_id'])}</code>",
                "브라우저 모드",
                escape(str(suite.get("browser_mode") or "-")),
            ),
            (
                "요청 시각",
                escape(suite["requested_at_kst"]),
                "종료 시각",
                escape(suite["ended_at_kst"]),
            ),
            (
                "최종 상태",
                _status_badge(suite["status"], suite["status_label"]),
                "제외 시스템",
                f"{suite.get('step_skipped', 0)}개",
            ),
        ]
    )

    summary_rows = []
    for step in context["step_summary"]:
        color = _status_color(step["status"])
        summary_rows.append(
            "<tr>"
            f'<td style="padding:9px 12px;border-bottom:1px solid {BORDER};text-align:center;font-size:13px;">{step["order"] + 1}</td>'
            f'<td style="padding:9px 12px;border-bottom:1px solid {BORDER};font-size:13px;font-weight:600;white-space:nowrap;">'
            f'{_text(step["system_name"])} <span style="color:{MUTED};font-weight:400;font-size:12px;">({escape(step["system_code"])})</span></td>'
            f'<td style="padding:9px 12px;border-bottom:1px solid {BORDER};font-size:13px;word-break:break-all;"><code>{_text(step.get("run_id"), "-")}</code></td>'
            f'<td style="padding:9px 12px;border-bottom:1px solid {BORDER};text-align:center;font-size:13px;font-weight:700;color:{color};">{escape(_status_label(step["status"]))}</td>'
            f'<td style="padding:9px 12px;border-bottom:1px solid {BORDER};text-align:center;font-size:13px;">{step["module_passed"]}/{step["module_total"]}</td>'
            "</tr>"
        )
    summary_head = (
        f'<thead><tr style="background:{SOFT_BG};">'
        + "".join(
            f'<th style="text-align:{align};padding:10px 12px;border-bottom:2px solid {BORDER};font-size:12px;color:{MUTED};font-weight:700;">{escape(label)}</th>'
            for label, align in (
                ("#", "center"),
                ("시스템", "left"),
                ("Run ID", "left"),
                ("상태", "center"),
                ("모듈", "center"),
            )
        )
        + "</tr></thead>"
    )
    summary_table = (
        '<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="border-collapse:collapse;border:1px solid {BORDER};border-radius:10px;">'
        f"{summary_head}<tbody>{''.join(summary_rows)}</tbody></table>"
    )

    system_sections = []
    for index, system_run in enumerate(system_runs, start=1):
        sys_status = system_run["status"]
        sys_color = _status_color(sys_status)
        ai_system = ai_systems.get(system_run["system_code"], {})
        modules = system_run.get("modules", [])
        modules_by_id = {module["module_id"]: module for module in modules}
        findings = {
            item["module_id"]: item
            for item in (ai_system.get("module_findings") or [])
            if item.get("module_id")
        }

        header = (
            f'<div style="margin-top:20px;padding:14px 16px;background:{SOFT_BG};'
            f'border:1px solid {BORDER};border-radius:12px 12px 0 0;">'
            f'<div style="font-size:15px;font-weight:700;color:{sys_color};">{index}. {_text(system_run["system_name"])} '
            f'<span style="color:{MUTED};font-weight:400;font-size:12px;">({escape(system_run["system_code"])})</span> '
            f"· {escape(system_run.get('status_label', _status_label(sys_status)))}</div>"
            f'<div style="margin-top:4px;font-size:12px;color:{MUTED};">Run ID: <code>{_text(system_run.get("run_id"), "-")}</code> · '
            f"모듈 통과 {system_run.get('module_passed', 0)}/{system_run.get('module_total', 0)} · 소요 {escape(system_run.get('duration_text', '-'))}</div>"
            "</div>"
        )

        if modules:
            body_parts = [_module_table(modules)]
            sys_summary = (ai_system.get("summary") or "").strip()
            if sys_summary:
                body_parts.insert(
                    0,
                    _callout(
                        f'<span style="color:{INK};">{escape(sys_summary)}</span>',
                        sys_color,
                        PASS_SOFT_BG if _is_passed(sys_status) else FAIL_SOFT_BG,
                    ),
                )
            screen_obs = _observation_list(modules, findings, "screen_observation", "")
            if "분석" not in screen_obs and findings:
                body_parts.append(
                    f'<div style="margin-top:10px;font-size:13px;font-weight:700;color:{MUTED};">화면·로그 관찰</div>{screen_obs}'
                )
            system_screenshots = _screenshot_gallery(
                context.get("inline_screenshots") or [],
                findings,
                system_code=system_run["system_code"],
            )
            if system_screenshots.strip():
                body_parts.append(
                    f'<div style="margin-top:14px;font-size:13px;font-weight:700;color:{MUTED};">모듈별 스크린샷</div>'
                    f"{system_screenshots}"
                )
            if system_run.get("failed_modules"):
                body_parts.append(
                    _failure_cards(
                        modules_by_id,
                        ai_system.get("failure_details") or [],
                        system_run["failed_modules"],
                    )
                )
            body_inner = "".join(body_parts)
        else:
            body_inner = f'<div style="font-size:13px;color:{MUTED};">{escape(system_run.get("note", "실행된 모듈이 없습니다."))}</div>'

        system_sections.append(
            header
            + f'<div style="padding:14px 16px;border:1px solid {BORDER};border-top:none;border-radius:0 0 12px 12px;">{body_inner}</div>'
        )

    next_no = 4
    attachment = context["email_attachment_summary"]

    headline = (ai.get("headline") or "").strip() or (
        f"전체 {suite['step_total']}개 시스템 순차 점검이 {suite['status_label']} 상태로 종료되었습니다. "
        f"통과 {suite['step_passed']}개, 이상징후 {suite.get('step_anomaly', suite.get('step_failed', 0))}개, 점검실패 {suite.get('step_error', 0)}개입니다."
    )

    sections = [
        _section(1, "점검 개요", kpi + '<div style="height:12px;"></div>' + overview, accent),
        _section(
            2,
            "핵심 요약",
            _callout(
                f'<span style="color:{INK};">{escape(headline)}</span>',
                accent,
                PASS_SOFT_BG if _is_passed(suite["status"]) else FAIL_SOFT_BG,
            ),
            accent,
        ),
        _section(3, "시스템 요약", summary_table, accent),
        _section(next_no, "시스템별 상세 결과", "".join(system_sections), accent),
        _section(
            5,
            "첨부 및 제외 파일 안내",
            _attachment_notice_body(attachment, context["gemini_input_summary"]),
            accent,
        ),
    ]

    return _shell(title, "".join(sections) + _footer())
