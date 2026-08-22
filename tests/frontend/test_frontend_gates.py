from pathlib import Path

from scripts.check_frontend_gates import (
    check_fg001_no_cdn,
    check_fg002_no_hex,
    check_fg003_status_source,
    check_fg004_file_size,
    check_fg005_no_static_ref,
    check_fg006_no_template_status_literals,
    check_fg007_mail_status_colors_from_ssot,
)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_fg001_flags_external_script(tmp_path):
    _write(
        tmp_path, "app/web/templates/x.html", '<script src="https://unpkg.com/htmx.org@2"></script>'
    )
    problems = check_fg001_no_cdn(tmp_path)
    assert len(problems) == 1
    assert "unpkg.com" in problems[0]


def test_fg001_allows_local_script(tmp_path):
    _write(tmp_path, "app/web/templates/x.html", '<script src="/static/dashboard.js"></script>')
    assert check_fg001_no_cdn(tmp_path) == []


def test_fg001_flags_chart_cdn_without_exception(tmp_path):
    """차트 라이브러리 예외는 P3-4 가 self-host 로 바꾸며 없앴다 — 이제 걸려야 한다."""
    _write(
        tmp_path,
        "app/web/templates/insights.html",
        '<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js" '
        'crossorigin="anonymous"></script>',
    )
    problems = check_fg001_no_cdn(tmp_path)
    assert len(problems) == 1
    assert "plotly" in problems[0]


def test_fg001_has_no_exception_mechanism():
    """예외 딕셔너리가 되살아나면 이 게이트는 다시 조용히 새기 시작한다."""
    import scripts.check_frontend_gates as gates

    assert not hasattr(gates, "FG001_EXCEPTIONS")


def test_fg002_flags_hex_in_frontend(tmp_path):
    _write(tmp_path, "app/web/frontend/components/a/styles.css", ".x { color: #ff0000; }")
    problems = check_fg002_no_hex(tmp_path)
    assert len(problems) == 1
    assert "#ff0000" in problems[0]


def test_fg002_ignores_generated_tokens(tmp_path):
    """생성물은 팔레트 원본이므로 hex 를 담는 유일한 예외다."""
    _write(
        tmp_path,
        "app/web/frontend/styles/tokens.generated.css",
        ":root { --st-passed-solid: #10b981; }",
    )
    assert check_fg002_no_hex(tmp_path) == []


def test_fg003_flags_hardcoded_korean_status_label(tmp_path):
    _write(tmp_path, "app/web/frontend/lib/x.ts", 'const label = "점검실패";')
    problems = check_fg003_status_source(tmp_path)
    assert len(problems) == 1
    assert "점검실패" in problems[0]


def test_fg003_allows_generated_module(tmp_path):
    _write(
        tmp_path,
        "app/web/frontend/lib/status.generated.ts",
        'export const X = { "error": "점검실패" };',
    )
    assert check_fg003_status_source(tmp_path) == []


def test_fg003_allows_literal_labels_in_test_files(tmp_path):
    """*.test.ts 는 기대값 단언에 라벨 리터럴이 필요하므로 예외다."""
    _write(
        tmp_path,
        "app/web/frontend/components/status-badge/index.test.ts",
        'expect(statusLabel("error")).toBe("점검실패");',
    )
    assert check_fg003_status_source(tmp_path) == []


def test_fg003_still_flags_non_test_file_with_test_like_name(tmp_path):
    """`.test.ts` 접미사가 아닌 파일은 여전히 걸린다(접두 문자열 매치 아님)."""
    _write(
        tmp_path,
        "app/web/frontend/components/status-badge/index.testing.ts",
        'const label = "점검실패";',
    )
    problems = check_fg003_status_source(tmp_path)
    assert len(problems) == 1
    assert "점검실패" in problems[0]


def test_fg004_flags_oversized_file(tmp_path):
    _write(
        tmp_path,
        "app/web/frontend/entries/big.ts",
        "\n".join(f"const x{i} = {i};" for i in range(401)),
    )
    problems = check_fg004_file_size(tmp_path)
    assert len(problems) == 1
    assert "401" in problems[0]


def test_fg004_allows_file_at_limit(tmp_path):
    _write(
        tmp_path,
        "app/web/frontend/entries/ok.ts",
        "\n".join(f"const x{i} = {i};" for i in range(400)),
    )
    assert check_fg004_file_size(tmp_path) == []


def test_fg004_allows_exact_allow_listed_legacy_stylesheet(tmp_path):
    """FG004_ALLOWLIST 에 등록된 레거시 모놀리식 스타일시트는 400줄을 넘어도 통과한다."""
    _write(
        tmp_path,
        "app/web/frontend/styles/app.css",
        "\n".join(f".x{i} {{ color: red; }}" for i in range(1411)),
    )
    assert check_fg004_file_size(tmp_path) == []


def test_fg004_flags_oversized_file_not_on_allowlist(tmp_path):
    """allowlist 에 없는 새 파일이 400줄을 넘으면 여전히 걸린다(디렉터리 전체 예외 아님)."""
    _write(
        tmp_path,
        "app/web/frontend/styles/other.css",
        "\n".join(f".x{i} {{ color: red; }}" for i in range(1411)),
    )
    problems = check_fg004_file_size(tmp_path)
    assert len(problems) == 1
    assert "other.css" in problems[0]


def test_fg005_flags_direct_static_reference(tmp_path):
    _write(
        tmp_path, "app/web/templates/x.html", '<link rel="stylesheet" href="/static/app.css?v=16">'
    )
    problems = check_fg005_no_static_ref(tmp_path)
    assert len(problems) == 1
    assert "app.css" in problems[0]


def test_fg005_allows_legacy_page_scripts(tmp_path):
    """P3 이관 전까지 페이지별 레거시 JS 는 허용한다(ALLOWLIST)."""
    _write(
        tmp_path,
        "app/web/templates/x.html",
        '<script src="/static/dashboard.js?v=22" defer></script>',
    )
    assert check_fg005_no_static_ref(tmp_path) == []


# ── 컴포넌트 폴더의 .jinja 매크로도 스캔 대상이다 ────────────────────────────
# templates/**.html 만 훑던 시절엔 macro.jinja 가 CDN·hex·/static 을 담아도
# 어떤 게이트에도 걸리지 않았다.

MACRO_REL = "app/web/frontend/components/status-badge/macro.jinja"


def test_fg001_flags_external_script_in_component_jinja(tmp_path):
    _write(tmp_path, MACRO_REL, '<script src="https://unpkg.com/htmx.org@2"></script>')
    problems = check_fg001_no_cdn(tmp_path)
    assert len(problems) == 1
    assert "unpkg.com" in problems[0]
    assert "macro.jinja" in problems[0]


def test_fg002_flags_hex_in_component_jinja(tmp_path):
    _write(tmp_path, MACRO_REL, '<span style="color: #ff0000">x</span>')
    problems = check_fg002_no_hex(tmp_path)
    assert len(problems) == 1
    assert "#ff0000" in problems[0]
    assert "macro.jinja" in problems[0]


def test_fg005_flags_static_ref_in_component_jinja(tmp_path):
    _write(tmp_path, MACRO_REL, '<link rel="stylesheet" href="/static/badge.css">')
    problems = check_fg005_no_static_ref(tmp_path)
    assert len(problems) == 1
    assert "badge.css" in problems[0]
    assert "macro.jinja" in problems[0]


def test_component_jinja_without_violations_passes(tmp_path):
    """실제 macro.jinja 형태 — 새로 스캔 대상이 됐다고 오발화하면 안 된다."""
    _write(
        tmp_path,
        MACRO_REL,
        '{% macro status_badge(status, label, size="md") -%}\n'
        '<span class="status-badge" data-tone="{{ status }}" data-size="{{ size }}">'
        "{{ label }}</span>\n"
        "{%- endmacro %}",
    )
    assert check_fg001_no_cdn(tmp_path) == []
    assert check_fg002_no_hex(tmp_path) == []
    assert check_fg005_no_static_ref(tmp_path) == []


# ── node_modules / 점 디렉터리는 스캔하지 않는다 ─────────────────────────────


def test_node_modules_is_not_scanned(tmp_path):
    """서드파티 소스는 우리 규칙의 대상이 아니다 — .css/.ts 가 들어와도 오발화 금지."""
    _write(tmp_path, "app/web/frontend/node_modules/some-pkg/dist/x.css", ".x { color: #ff0000; }")
    _write(tmp_path, "app/web/frontend/node_modules/some-pkg/dist/x.ts", 'const l = "점검실패";')
    _write(
        tmp_path,
        "app/web/frontend/node_modules/some-pkg/dist/big.ts",
        "\n".join(f"const x{i} = {i};" for i in range(401)),
    )
    _write(
        tmp_path,
        "app/web/frontend/node_modules/some-pkg/dist/m.jinja",
        '<script src="https://unpkg.com/whatever@1"></script>',
    )
    assert check_fg002_no_hex(tmp_path) == []
    assert check_fg003_status_source(tmp_path) == []
    assert check_fg004_file_size(tmp_path) == []
    assert check_fg001_no_cdn(tmp_path) == []


def test_dot_directories_are_not_scanned(tmp_path):
    """도구 캐시(.vite 등)도 스캔 대상이 아니다."""
    _write(tmp_path, "app/web/frontend/.vite/cache/x.css", ".x { color: #ff0000; }")
    assert check_fg002_no_hex(tmp_path) == []


def test_sibling_of_node_modules_is_still_scanned(tmp_path):
    """디렉터리 이름이 정확히 node_modules 일 때만 건너뛴다(접두 매치 아님)."""
    _write(tmp_path, "app/web/frontend/node_modules_helpers/x.css", ".x { color: #ff0000; }")
    problems = check_fg002_no_hex(tmp_path)
    assert len(problems) == 1
    assert "#ff0000" in problems[0]


def test_fg006_flags_status_keyed_map(tmp_path):
    """이것이 P3-1 이 고친 실제 버그다 — run.html:6 의 status_pill 원문."""
    _write(
        tmp_path,
        "app/web/templates/x.html",
        "{% set status_pill = {'pending': 'bg-gray-100 text-gray-600', "
        "'running': 'bg-blue-100 text-blue-700', 'passed': 'bg-emerald-100 text-emerald-700'} %}",
    )
    problems = check_fg006_no_template_status_literals(tmp_path)
    assert problems, problems
    assert "상태 키 맵" in problems[0]


def test_fg006_flags_js_status_map_in_template(tmp_path):
    """mobile_trigger.html 이 인라인 JS 로 들고 있던 상태→라벨+클래스 맵."""
    _write(
        tmp_path,
        "app/web/templates/x.html",
        '  running: { label: "실행 중", cls: "a" }, passed: { label: "정상", cls: "b" },',
    )
    assert check_fg006_no_template_status_literals(tmp_path)


def test_fg006_flags_map_written_one_entry_per_line(tmp_path):
    """줄당 항목이 하나인 맵도 잡아야 한다.

    규칙이 "한 줄에 상태 키 2개 이상" 이던 동안 mobile_trigger.html 의
    8개짜리 STATUS_VIEW 가 통째로 보이지 않았다(설계 §3.3).
    """
    _write(
        tmp_path,
        "app/web/templates/x.html",
        "<script>\n"
        "const STATUS_VIEW = {\n"
        '    PENDING: { label: "대기" },\n'
        '    RUNNING: { label: "실행 중" },\n'
        '    PASSED: { label: "정상" },\n'
        "};\n"
        "</script>\n",
    )
    problems = check_fg006_no_template_status_literals(tmp_path)
    assert any("상태 키 맵" in problem for problem in problems)


def test_fg006_flags_enum_and_label_on_one_line(tmp_path):
    """<option value="PASSED">정상</option> — 생성물을 써야 할 자리."""
    _write(tmp_path, "app/web/templates/x.html", '<option value="ANOMALY">이상징후</option>')
    problems = check_fg006_no_template_status_literals(tmp_path)
    assert problems
    assert "enum" in problems[0]


def test_fg006_flags_cancelled_label(tmp_path):
    _write(tmp_path, "app/web/templates/x.html", '<option value="CANCELLED">취소</option>')
    problems = check_fg006_no_template_status_literals(tmp_path)
    assert len(problems) == 1
    assert "CANCELLED" in problems[0]


def test_fg006_allows_body_layout_classes(tmp_path):
    """base.html 의 <body class="… bg-gray-50 text-gray-900 …"> 는 레이아웃이다."""
    _write(
        tmp_path,
        "app/web/templates/x.html",
        '<body class="min-h-screen bg-gray-50 text-gray-900 antialiased">',
    )
    assert check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_allows_nav_active_color_block(tmp_path):
    """{% block nav_runs %}bg-red-50 text-red-700{% endblock %} 는 네비 활성 표시다."""
    _write(
        tmp_path,
        "app/web/templates/x.html",
        "{% block nav_runs %}bg-red-50 text-red-700 font-semibold{% endblock %}",
    )
    assert check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_allows_status_css_custom_properties(tmp_path):
    """상태 토큰용 CSS 변수 이름은 맵 리터럴이 아니다."""
    _write(
        tmp_path,
        "app/web/templates/x.html",
        "<style>\n"
        ".demo {\n"
        "  --st-passed: #0ca30c;\n"
        "  --st-anomaly: #fab219;\n"
        "  --st-error: #d03b3b;\n"
        "  --st-running: #2a78d6;\n"
        "}\n"
        "</style>\n",
    )
    assert check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_allows_cancel_button_without_enum(tmp_path):
    """'취소' 는 버튼 문구로도 흔하다 — enum 값이 없으면 걸리지 않아야 한다."""
    _write(tmp_path, "app/web/templates/x.html", '<button type="button">취소</button>')
    assert check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_allows_prose_mentioning_a_status_word(tmp_path):
    """히어로 문장·설명 산문은 배지가 아니다(zone_a_kpi.html 의 헤드라인)."""
    _write(
        tmp_path,
        "app/web/templates/x.html",
        "{% elif t.error > 0 %}점검실패 {{ t.error }}건 — 우선 확인이 필요합니다",
    )
    assert check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_allows_page_title_naming_a_status(tmp_path):
    """'이상징후 인박스' 는 페이지 이름이다."""
    _write(tmp_path, "app/web/templates/x.html", "<h1>이상징후 인박스</h1>")
    assert check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_allows_substring_collision(tmp_path):
    """'무인 실행 중 셀렉터가…' 의 '실행 중' 은 문장 일부다."""
    _write(
        tmp_path,
        "app/web/templates/x.html",
        "<p>무인 실행 중 셀렉터가 깨지면 자동 복구 시도가 기록됩니다.</p>",
    )
    assert check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_allows_unrelated_keys_far_apart(tmp_path):
    """블록 단위로 넓히면서 무관한 단어가 우연히 묶이지 않아야 한다."""
    lines = ['<div class="error-banner">']
    lines += ["  <p>줄</p>"] * 40
    lines += ['  <span data-state="running"></span>', "</div>"]
    _write(tmp_path, "app/web/templates/x.html", "\n".join(lines))
    assert check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_skips_allowlisted_template(tmp_path, monkeypatch):
    import scripts.check_frontend_gates as gates

    monkeypatch.setattr(gates, "FG006_ALLOWLIST", {"app/web/templates/legacy.html"})
    _write(
        tmp_path,
        "app/web/templates/legacy.html",
        "{% set status_pill = {'passed': 'a', 'error': 'b'} %}",
    )
    assert gates.check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_does_not_allowlist_run_and_suite():
    """P3-1 이 고친 두 템플릿은 처음부터 allowlist 밖에 있어야 한다."""
    import scripts.check_frontend_gates as gates

    assert "app/web/templates/run.html" not in gates.FG006_ALLOWLIST
    assert "app/web/templates/suite.html" not in gates.FG006_ALLOWLIST


def test_fg006_allowlist_holds_only_real_offenders():
    """구조 탐지로 좁힌 뒤 남는 1개. 오탐이 섞이면 allowlist 가 영구히 비지 않는다."""
    import scripts.check_frontend_gates as gates

    assert gates.FG006_ALLOWLIST == {
        "app/web/templates/mobile_trigger.html",
    }


def test_fg007_flags_hardcoded_mail_status_color(tmp_path):
    _write(
        tmp_path,
        "app/notifications/report_renderer.py",
        'PAGE_BG = "#f4f5f7"\nPASS_COLOR = "#2f8f4e"\n',
    )
    problems = check_fg007_mail_status_colors_from_ssot(tmp_path)
    assert len(problems) == 1
    assert "PASS_COLOR" in problems[0]


def test_fg007_allows_palette_derived_status_color(tmp_path):
    _write(
        tmp_path,
        "app/notifications/report_renderer.py",
        'PAGE_BG = "#f4f5f7"\nPASS_COLOR = PALETTE["passed"]["text"]\n',
    )
    assert check_fg007_mail_status_colors_from_ssot(tmp_path) == []


def test_fg007_ignores_layout_colors(tmp_path):
    """레이아웃 색은 상태와 무관하므로 hex 리터럴이 정당하다."""
    _write(
        tmp_path,
        "app/notifications/report_renderer.py",
        'PAGE_BG = "#f4f5f7"\nINK = "#1f2328"\nBORDER = "#e5e7eb"\n',
    )
    assert check_fg007_mail_status_colors_from_ssot(tmp_path) == []
