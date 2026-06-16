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

_STATUS_LABELS = {
    ModuleStatus.PASSED.value: "성공",
    ModuleStatus.FAILED.value: "실패",
    ModuleStatus.BLOCKED.value: "차단",
    ModuleStatus.SKIPPED.value: "제외",
    ModuleStatus.CANCELLED.value: "취소",
    ModuleStatus.RUNNING.value: "실행 중",
    ModuleStatus.QUEUED.value: "대기",
    ModuleStatus.PENDING.value: "대기",
    ModuleStatus.WAITING_INPUT.value: "입력 대기",
}

_STATUS_COLORS = {
    ModuleStatus.PASSED.value: PASS_COLOR,
    ModuleStatus.FAILED.value: FAIL_COLOR,
    ModuleStatus.BLOCKED.value: WARN_COLOR,
    ModuleStatus.SKIPPED.value: NEUTRAL_COLOR,
    ModuleStatus.CANCELLED.value: NEUTRAL_COLOR,
    ModuleStatus.WAITING_INPUT.value: WARN_COLOR,
    RunStatus.PASSED.value: PASS_COLOR,
    RunStatus.FAILED.value: FAIL_COLOR,
    RunStatus.CANCELLED.value: NEUTRAL_COLOR,
    SuiteStatus.PASSED.value: PASS_COLOR,
    SuiteStatus.FAILED.value: FAIL_COLOR,
    SuiteStatus.SKIPPED.value: NEUTRAL_COLOR,
    SuiteStatus.CANCELLED.value: NEUTRAL_COLOR,
}


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status)


def _status_color(status: str) -> str:
    return _STATUS_COLORS.get(status, NEUTRAL_COLOR)


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
        f"<div style=\"margin:0;padding:24px 12px;background:{PAGE_BG};"
        f"font-family:{FONT_STACK};color:{INK};line-height:1.6;\">"
        f"<div style=\"max-width:960px;margin:0 auto;background:{CARD_BG};"
        f"border:1px solid {BORDER};border-radius:18px;overflow:hidden;\">"
        f"<div style=\"padding:28px 28px 8px;\">{title_html}</div>"
        f"<div style=\"padding:0 28px 28px;\">{body_html}</div>"
        "</div></div>"
    )


def _status_badge(status: str, status_label: str) -> str:
    passed = _is_passed(status)
    color = PASS_COLOR if passed else FAIL_COLOR
    if status in {RunStatus.CANCELLED.value, SuiteStatus.CANCELLED.value}:
        color = NEUTRAL_COLOR
    return (
        f"<span style=\"display:inline-block;padding:5px 14px;border-radius:999px;"
        f"background:{color};color:#ffffff;font-size:13px;font-weight:700;"
        f"vertical-align:middle;\">{escape(status_label)} ({escape(status.upper())})</span>"
    )


def _title_block(title: str, status: str, status_label: str, subtitle: str) -> str:
    accent = PASS_COLOR if _is_passed(status) else FAIL_COLOR
    if status in {RunStatus.CANCELLED.value, SuiteStatus.CANCELLED.value}:
        accent = NEUTRAL_COLOR
    return (
        f"<div style=\"border-bottom:3px solid {accent};padding-bottom:16px;\">"
        f"<div style=\"font-size:22px;font-weight:800;color:{INK};margin-bottom:10px;\">"
        f"{escape(title)}</div>"
        f"<div>{_status_badge(status, status_label)}"
        f"<span style=\"margin-left:10px;font-size:13px;color:{MUTED};\">{escape(subtitle)}</span>"
        "</div></div>"
    )


def _section(number: int, title: str, body_html: str, accent: str = PASS_COLOR) -> str:
    return (
        f"<h3 style=\"margin:26px 0 12px;padding-left:11px;border-left:4px solid {accent};"
        f"font-size:16px;font-weight:700;color:{INK};line-height:1.35;\">"
        f"{number}. {escape(title)}</h3>{body_html}"
    )


def _kpi_cards(cards: list[tuple[str, str, str]]) -> str:
    """[(label, value, value_color), ...] → 균등 너비 KPI 카드 행."""
    width = f"{100 // max(len(cards), 1)}%"
    cells = "".join(
        (
            f"<td width=\"{width}\" style=\"background:{SOFT_BG};border:1px solid {BORDER};"
            "border-radius:12px;padding:14px 10px;text-align:center;vertical-align:top;\">"
            f"<div style=\"font-size:12px;color:{MUTED};margin-bottom:6px;\">{escape(label)}</div>"
            f"<div style=\"font-size:24px;font-weight:800;color:{value_color};\">{escape(value)}</div>"
            "</td>"
        )
        for label, value, value_color in cards
    )
    return (
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" role=\"presentation\" "
        "style=\"border-collapse:separate;border-spacing:8px;margin:0 -8px;\"><tr>"
        f"{cells}</tr></table>"
    )


def _callout(text_html: str, accent: str, bg: str) -> str:
    return (
        f"<div style=\"margin-top:4px;padding:14px 16px;background:{bg};"
        f"border-left:4px solid {accent};border-radius:0 10px 10px 0;font-size:14px;\">"
        f"{text_html}</div>"
    )


def _info_table(rows: list[tuple[str, str, str, str]]) -> str:
    """4열(라벨/값/라벨/값) 메타데이터 표. 값에는 이미 escape 된 HTML 을 넣는다."""
    label_style = (
        f"padding:10px 12px;background:{LABEL_BG};border:1px solid {BORDER};"
        f"font-size:13px;font-weight:600;color:{MUTED};white-space:nowrap;width:18%;"
    )
    value_style = f"padding:10px 12px;border:1px solid {BORDER};font-size:13px;color:{INK};width:32%;"
    body = "".join(
        (
            "<tr>"
            f"<td style=\"{label_style}\">{escape(left_label)}</td>"
            f"<td style=\"{value_style}\">{left_value}</td>"
            f"<td style=\"{label_style}\">{escape(right_label)}</td>"
            f"<td style=\"{value_style}\">{right_value}</td>"
            "</tr>"
        )
        for left_label, left_value, right_label, right_value in rows
    )
    return (
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" role=\"presentation\" "
        f"style=\"border-collapse:collapse;\">{body}</table>"
    )


def _module_table(modules: list[dict]) -> str:
    head = (
        f"<thead><tr style=\"background:{SOFT_BG};\">"
        + "".join(
            f"<th style=\"text-align:{align};padding:10px 12px;border-bottom:2px solid {BORDER};"
            f"font-size:12px;color:{MUTED};font-weight:700;{extra}\">{escape(label)}</th>"
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
        dim = "" if status not in {ModuleStatus.SKIPPED.value, ModuleStatus.CANCELLED.value} else f"color:{MUTED};"
        rows.append(
            "<tr>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};text-align:center;"
            f"font-size:13px;{dim}\">{module['seq']}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};font-size:13px;"
            f"font-weight:600;white-space:nowrap;{dim}\">{_text(module['module_name'])}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};text-align:center;"
            f"font-size:13px;font-weight:700;color:{color};\">{escape(label)}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};text-align:right;"
            f"font-size:13px;white-space:nowrap;{dim}\">{_text(module.get('duration_text'), '-')}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid {BORDER};font-size:13px;"
            f"color:{MUTED};word-break:break-all;\">{_text(module.get('message'), '-')}</td>"
            "</tr>"
        )
    return (
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" role=\"presentation\" "
        f"style=\"border-collapse:collapse;border:1px solid {BORDER};border-radius:10px;\">"
        f"{head}<tbody>{''.join(rows)}</tbody></table>"
    )


def _observation_list(modules: list[dict], findings: dict[str, dict], key: str, empty_text: str) -> str:
    items = []
    for module in modules:
        observation = (findings.get(module["module_id"], {}).get(key) or "").strip()
        if not observation:
            continue
        items.append(
            f"<li style=\"margin-bottom:10px;\"><strong>{_text(module['module_name'])}</strong> "
            f"<span style=\"color:{MUTED};font-size:12px;\">(순번 {module['seq']})</span><br>"
            f"<span style=\"color:{INK};\">{escape(observation.strip())}</span></li>"
        )
    if not items:
        return f"<div style=\"font-size:13px;color:{MUTED};\">{escape(empty_text)}</div>"
    return f"<ul style=\"margin:0;padding-left:18px;font-size:14px;\">{''.join(items)}</ul>"


def _failure_cards(modules_by_id: dict[str, dict], failure_details: list[dict], failed_modules: list[dict]) -> str:
    detail_by_id = {item.get("module_id"): item for item in failure_details if item.get("module_id")}
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
            text = (str(value).strip() if value else "")
            if not text:
                continue
            rows.append(
                f"<div style=\"margin-top:6px;\"><span style=\"display:inline-block;width:72px;"
                f"color:{MUTED};font-size:12px;vertical-align:top;\">{escape(label)}</span>"
                f"<span style=\"font-size:13px;color:{INK};\">{escape(text)}</span></div>"
            )
        body = "".join(rows) or f"<div style=\"font-size:13px;color:{MUTED};\">추가 분석 정보가 없습니다.</div>"
        name = modules_by_id.get(module_id, {}).get("module_name", failed.get("module_name", module_id))
        cards.append(
            f"<div style=\"margin-top:12px;padding:14px 16px;background:{FAIL_SOFT_BG};"
            f"border:1px solid rgba(192,57,43,0.22);border-radius:12px;\">"
            f"<div style=\"font-size:14px;font-weight:700;color:{FAIL_COLOR};\">{_text(name)} "
            f"<span style=\"color:{MUTED};font-weight:400;font-size:12px;\">({escape(module_id)})</span></div>"
            f"{body}</div>"
        )
    return "".join(cards)


def _comparison_block(comparison: dict, comment: str) -> str:
    if not comparison.get("has_baseline"):
        return _callout(
            f"<span style=\"color:{MUTED};\">이전 실행 이력(Baseline)이 없어 직전 실행 대비 변화 분석 대상에서 제외되었습니다.</span>",
            NEUTRAL_COLOR,
            NEUTRAL_SOFT_BG,
        )
    parts = []
    if comment.strip():
        parts.append(f"<div style=\"margin-bottom:8px;color:{INK};\">{escape(comment.strip())}</div>")
    parts.append(
        f"<div style=\"font-size:12px;color:{MUTED};\">기준 Run: <code>"
        f"{_text(comparison.get('baseline_run_id'), '-')}</code> ({_text(comparison.get('baseline_requested_at'), '-')})</div>"
    )
    for label, names, color in (
        ("새로 실패", comparison.get("newly_failed") or [], FAIL_COLOR),
        ("복구됨", comparison.get("recovered") or [], PASS_COLOR),
        ("계속 실패", comparison.get("still_failing") or [], WARN_COLOR),
    ):
        if not names:
            continue
        parts.append(
            f"<div style=\"margin-top:6px;font-size:13px;\"><strong style=\"color:{color};\">"
            f"{escape(label)} {len(names)}건</strong>: {escape(', '.join(names))}</div>"
        )
    if not (comparison.get("newly_failed") or comparison.get("recovered") or comparison.get("still_failing")):
        parts.append(f"<div style=\"margin-top:6px;font-size:13px;color:{MUTED};\">직전 실행과 비교해 모듈 상태 변화가 없습니다.</div>")
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
            f"<li><code>{escape(entry['path'])}</code> — {escape(entry['reason'])}</li>" for entry in entries
        )
        blocks.append(
            f"<div style=\"margin-top:12px;padding:12px 14px;background:{WARN_SOFT_BG};"
            f"border:1px solid rgba(183,121,31,0.25);border-radius:10px;\">"
            f"<strong style=\"display:block;margin-bottom:6px;color:{WARN_COLOR};\">{escape(title)}</strong>"
            f"<ul style=\"margin:0;padding-left:18px;font-size:13px;\">{items}</ul></div>"
        )
    return "".join(blocks)


def _footer() -> str:
    return (
        f"<hr style=\"margin:28px 0 14px;border:none;border-top:1px solid {BORDER};\">"
        f"<div style=\"font-size:12px;color:{MUTED};\">본 메일은 사내 E2E 자동화 테스트 플랫폼이 자동 발송한 메일입니다. "
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
    failed = summary.get(ModuleStatus.FAILED.value, 0)
    skipped = summary.get(ModuleStatus.SKIPPED.value, 0)
    executed = passed + failed
    pass_rate = f"{round(passed / executed * 100)}%" if executed else "-"
    accent = PASS_COLOR if _is_passed(run["status"]) else FAIL_COLOR

    title = _title_block(
        f"[E2E] {run['system_name']} 테스트 결과 보고서",
        run["status"],
        run["status_label"],
        f"{run['system_code']} · {run['ended_at_kst']}",
    )

    kpi = _kpi_cards(
        [
            ("전체 모듈", str(len(modules)), INK),
            ("성공", str(passed), PASS_COLOR),
            ("실패", str(failed), FAIL_COLOR if failed else MUTED),
            ("통과율", pass_rate, accent),
        ]
    )

    overview = _info_table(
        [
            ("Run ID", f"<code>{escape(run['run_id'])}</code>", "대상 시스템", f"{escape(run['system_name'])} ({escape(run['system_code'])})"),
            ("요청 시각", escape(run["requested_at_kst"]), "실행 주체", escape(run["triggered_by"])),
            ("시작/종료", f"{escape(run['started_at_kst'])} ~ {escape(run['ended_at_kst'])}", "소요 시간", escape(run["duration_text"])),
            ("최종 상태", _status_badge(run["status"], run["status_label"]), "제외 모듈", f"{skipped}개"),
        ]
    )

    headline = (ai.get("headline") or "").strip() or (
        f"{run['system_name']} 테스트가 {run['status_label']} 상태로 종료되었습니다. "
        f"전체 {len(modules)}개 모듈 중 {passed}개 성공, {failed}개 실패, {skipped}개 제외되었습니다."
    )

    sections = [
        _section(1, "실행 개요", kpi + "<div style=\"height:12px;\"></div>" + overview, accent),
        _section(2, "핵심 요약", _callout(f"<span style=\"color:{INK};\">{escape(headline)}</span>", accent, PASS_SOFT_BG if _is_passed(run["status"]) else FAIL_SOFT_BG), accent),
        _section(3, "직전 실행 대비 변화", _comparison_block(context["comparison"], ai.get("comparison_comment") or ""), INFO_COLOR),
        _section(4, "모듈별 결과", _module_table(modules), accent),
        _section(5, "화면 검증 (스크린샷 분석)", _observation_list(modules, findings, "screen_observation", "분석할 스크린샷 자료가 없습니다."), accent),
        _section(6, "로그 분석", _observation_list(modules, findings, "log_observation", "분석할 실행 로그가 없습니다."), accent),
    ]

    if context["failed_modules"]:
        sections.append(
            _section(7, "실패 상세 분석", _failure_cards(modules_by_id, ai.get("failure_details") or [], context["failed_modules"]), FAIL_COLOR)
        )

    next_no = len(sections) + 1
    attachment = context["email_attachment_summary"]
    attach_body = (
        f"<div style=\"font-size:14px;\">첨부 스크린샷 <strong>{attachment['screenshot_count']}건</strong> · "
        f"첨부 로그 <strong>{attachment['log_count']}건</strong></div>"
        + _omitted_warning(attachment, context["gemini_input_summary"])
    )
    sections.append(_section(next_no, "첨부 및 제외 파일 안내", attach_body, accent))

    return _shell(title, "".join(sections) + _footer())


# --- Suite 보고서 -----------------------------------------------------------------
def render_suite_report_html(context: dict, ai_content: dict | None = None) -> str:
    ai = ai_content or {}
    suite = context["suite"]
    system_runs = context["system_runs"]
    ai_systems = {item.get("system_code"): item for item in (ai.get("systems") or []) if item.get("system_code")}
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
            ("실패", str(suite["step_failed"]), FAIL_COLOR if suite["step_failed"] else MUTED),
            ("소요 시간", suite["duration_text"], accent),
        ]
    )

    overview = _info_table(
        [
            ("Suite ID", f"<code>{escape(suite['suite_id'])}</code>", "브라우저 모드", escape(str(suite.get("browser_mode") or "-"))),
            ("요청 시각", escape(suite["requested_at_kst"]), "종료 시각", escape(suite["ended_at_kst"])),
            ("최종 상태", _status_badge(suite["status"], suite["status_label"]), "제외 시스템", f"{suite.get('step_skipped', 0)}개"),
        ]
    )

    summary_rows = []
    for step in context["step_summary"]:
        color = _status_color(step["status"])
        summary_rows.append(
            "<tr>"
            f"<td style=\"padding:9px 12px;border-bottom:1px solid {BORDER};text-align:center;font-size:13px;\">{step['order'] + 1}</td>"
            f"<td style=\"padding:9px 12px;border-bottom:1px solid {BORDER};font-size:13px;font-weight:600;white-space:nowrap;\">"
            f"{_text(step['system_name'])} <span style=\"color:{MUTED};font-weight:400;font-size:12px;\">({escape(step['system_code'])})</span></td>"
            f"<td style=\"padding:9px 12px;border-bottom:1px solid {BORDER};font-size:13px;word-break:break-all;\"><code>{_text(step.get('run_id'), '-')}</code></td>"
            f"<td style=\"padding:9px 12px;border-bottom:1px solid {BORDER};text-align:center;font-size:13px;font-weight:700;color:{color};\">{escape(_status_label(step['status']))}</td>"
            f"<td style=\"padding:9px 12px;border-bottom:1px solid {BORDER};text-align:center;font-size:13px;\">{step['module_passed']}/{step['module_total']}</td>"
            "</tr>"
        )
    summary_head = (
        f"<thead><tr style=\"background:{SOFT_BG};\">"
        + "".join(
            f"<th style=\"text-align:{align};padding:10px 12px;border-bottom:2px solid {BORDER};font-size:12px;color:{MUTED};font-weight:700;\">{escape(label)}</th>"
            for label, align in (("#", "center"), ("시스템", "left"), ("Run ID", "left"), ("상태", "center"), ("모듈", "center"))
        )
        + "</tr></thead>"
    )
    summary_table = (
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" role=\"presentation\" "
        f"style=\"border-collapse:collapse;border:1px solid {BORDER};border-radius:10px;\">"
        f"{summary_head}<tbody>{''.join(summary_rows)}</tbody></table>"
    )

    system_sections = []
    for index, system_run in enumerate(system_runs, start=1):
        sys_status = system_run["status"]
        sys_color = _status_color(sys_status)
        ai_system = ai_systems.get(system_run["system_code"], {})
        modules = system_run.get("modules", [])
        modules_by_id = {module["module_id"]: module for module in modules}
        findings = {item["module_id"]: item for item in (ai_system.get("module_findings") or []) if item.get("module_id")}

        header = (
            f"<div style=\"margin-top:20px;padding:14px 16px;background:{SOFT_BG};"
            f"border:1px solid {BORDER};border-radius:12px 12px 0 0;\">"
            f"<div style=\"font-size:15px;font-weight:700;color:{sys_color};\">{index}. {_text(system_run['system_name'])} "
            f"<span style=\"color:{MUTED};font-weight:400;font-size:12px;\">({escape(system_run['system_code'])})</span> "
            f"· {escape(system_run.get('status_label', _status_label(sys_status)))}</div>"
            f"<div style=\"margin-top:4px;font-size:12px;color:{MUTED};\">Run ID: <code>{_text(system_run.get('run_id'), '-')}</code> · "
            f"모듈 통과 {system_run.get('module_passed', 0)}/{system_run.get('module_total', 0)} · 소요 {escape(system_run.get('duration_text', '-'))}</div>"
            "</div>"
        )

        if modules:
            body_parts = [_module_table(modules)]
            sys_summary = (ai_system.get("summary") or "").strip()
            if sys_summary:
                body_parts.insert(0, _callout(f"<span style=\"color:{INK};\">{escape(sys_summary)}</span>", sys_color, PASS_SOFT_BG if _is_passed(sys_status) else FAIL_SOFT_BG))
            screen_obs = _observation_list(modules, findings, "screen_observation", "")
            if "분석" not in screen_obs and findings:
                body_parts.append(f"<div style=\"margin-top:10px;font-size:13px;font-weight:700;color:{MUTED};\">화면·로그 관찰</div>{screen_obs}")
            if system_run.get("failed_modules"):
                body_parts.append(_failure_cards(modules_by_id, ai_system.get("failure_details") or [], system_run["failed_modules"]))
            body_inner = "".join(body_parts)
        else:
            body_inner = f"<div style=\"font-size:13px;color:{MUTED};\">{escape(system_run.get('note', '실행된 모듈이 없습니다.'))}</div>"

        system_sections.append(
            header
            + f"<div style=\"padding:14px 16px;border:1px solid {BORDER};border-top:none;border-radius:0 0 12px 12px;\">{body_inner}</div>"
        )

    next_no = 4
    attachment = context["email_attachment_summary"]
    attach_body = (
        f"<div style=\"font-size:14px;\">첨부 스크린샷 <strong>{attachment['screenshot_count']}건</strong> · "
        f"첨부 로그 <strong>{attachment['log_count']}건</strong></div>"
        + _omitted_warning(attachment, context["gemini_input_summary"])
    )

    headline = (ai.get("headline") or "").strip() or (
        f"전체 {suite['step_total']}개 시스템 순차 점검이 {suite['status_label']} 상태로 종료되었습니다. "
        f"통과 {suite['step_passed']}개, 실패 {suite['step_failed']}개입니다."
    )

    sections = [
        _section(1, "점검 개요", kpi + "<div style=\"height:12px;\"></div>" + overview, accent),
        _section(2, "핵심 요약", _callout(f"<span style=\"color:{INK};\">{escape(headline)}</span>", accent, PASS_SOFT_BG if _is_passed(suite["status"]) else FAIL_SOFT_BG), accent),
        _section(3, "시스템 요약", summary_table, accent),
        _section(next_no, "시스템별 상세 결과", "".join(system_sections), accent),
        _section(5, "첨부 및 제외 파일 안내", attach_body, accent),
    ]

    return _shell(title, "".join(sections) + _footer())
