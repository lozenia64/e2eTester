import re
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


def test_fg002_flags_hex_in_template(tmp_path):
    """templates/ 는 어떤 색 게이트도 보지 않던 사각지대였다."""
    _write(tmp_path, "app/web/templates/x.html", "<style>.a { color: #0ca30c; }</style>")
    problems = check_fg002_no_hex(tmp_path)
    assert len(problems) == 1
    assert "#0ca30c" in problems[0]


def test_fg002_flags_hex_in_legacy_script(tmp_path):
    _write(tmp_path, "app/web/static/legacy.js", 'const c = "#d03b3b";')
    problems = check_fg002_no_hex(tmp_path)
    assert len(problems) == 1
    assert "#d03b3b" in problems[0]


def test_fg002_ignores_built_bundles(tmp_path):
    """static/dist 는 빌드 산출물이다 — 우리가 쓴 코드가 아니다."""
    _write(tmp_path, "app/web/static/dist/assets/main-abc.js", 'var x="#123456";')
    assert check_fg002_no_hex(tmp_path) == []


def test_fg002_allows_theme_color_meta(tmp_path):
    """<meta name="theme-color"> 는 CSS 변수를 쓸 수 없다 — 브라우저가 리터럴로 읽는다.

    파일 allowlist 로 처리하면 base.html·admin/base.html·login.html 이 영구
    항목으로 남아 "allowlist 가 비면 완성" 전제가 깨진다(FG-006 이 겪은 실패).
    """
    _write(
        tmp_path,
        "app/web/templates/base.html",
        '<meta name="theme-color" content="#4f46e5">',
    )
    assert check_fg002_no_hex(tmp_path) == []


def test_fg002_allowlisted_template_is_skipped(tmp_path):
    import scripts.check_frontend_gates as gates

    _write(tmp_path, "app/web/templates/insights.html", "<style>.a { color: #123456; }</style>")
    original = gates.FG002_ALLOWLIST
    gates.FG002_ALLOWLIST = {"app/web/templates/insights.html"}
    try:
        assert check_fg002_no_hex(tmp_path) == []
    finally:
        gates.FG002_ALLOWLIST = original


def test_fg002_allowlist_only_holds_files_that_still_have_hex():
    """유예 목록이 실효를 잃은 줄을 품고 있으면 '비면 완성' 신호가 거짓이 된다."""
    import scripts.check_frontend_gates as gates

    stale = []
    for rel in gates.FG002_ALLOWLIST:
        path = gates.REPO_ROOT / rel
        assert path.exists(), f"allowlist 가 없는 파일을 가리킨다: {rel}"
        if not re.search(r"#[0-9a-fA-F]{3,8}\b", path.read_text(encoding="utf-8")):
            stale.append(rel)
    assert not stale, f"hex 가 남아 있지 않은 allowlist 항목 — 지우세요: {stale}"


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


def test_fg004_flags_oversized_dashboard_stylesheet_after_component_split(tmp_path):
    """대시보드 분할이 끝났으므로 dashboard.css는 더 이상 allowlist 예외가 아니다."""
    _write(
        tmp_path,
        "app/web/frontend/styles/dashboard.css",
        "\n".join(f".x{i} {{ color: red; }}" for i in range(401)),
    )
    problems = check_fg004_file_size(tmp_path)
    assert len(problems) == 1
    assert "dashboard.css" in problems[0]


def test_dashboard_component_css_stays_with_its_owner():
    """대시보드 레이아웃과 Zone A 컴포넌트 CSS의 소유권을 함께 고정한다."""
    dashboard_css = (
        Path(__file__).resolve().parents[2] / "app/web/frontend/styles/dashboard.css"
    ).read_text(encoding="utf-8")
    status_hero_css = (
        Path(__file__).resolve().parents[2] / "app/web/frontend/components/status-hero/styles.css"
    ).read_text(encoding="utf-8")
    system_matrix_css = (
        Path(__file__).resolve().parents[2] / "app/web/frontend/components/system-matrix/styles.css"
    ).read_text(encoding="utf-8")

    forbidden = (".dash-hero", ".dash-sys-row", "@keyframes dash-row-in")
    assert all(selector not in dashboard_css for selector in forbidden)

    required_dashboard_layout = (
        ".dash-refresh {",
        ".dash-refresh:hover {",
        ".dash-refresh:disabled {",
        ".dash-refresh__icon {",
        ".dash-htmx-indicator {",
        ".dash-htmx-indicator.htmx-request {",
    )
    assert all(selector in dashboard_css for selector in required_dashboard_layout)

    required_status_hero = (
        ".dash-hero {",
        ".dash-hero__top {",
        ".dash-hero__text {",
        ".dash-hero__title {",
        ".dash-hero__meta {",
        ".dash-hero__aside {",
        ".dash-hero__actions {",
    )
    assert all(selector in status_hero_css for selector in required_status_hero)

    forbidden_status_hero = (
        ".dash-refresh {",
        ".dash-refresh:hover {",
        ".dash-refresh:disabled {",
        ".dash-refresh__icon {",
        ".dash-htmx-indicator {",
        ".dash-htmx-indicator.htmx-request {",
    )
    assert all(selector not in status_hero_css for selector in forbidden_status_hero)

    required_system_matrix = (
        '.dash-sys-row[data-priority="attention"] {',
        '.dash__systems[data-first-paint="true"] .dash-sys-row {',
        "@keyframes dash-row-in {",
        "@media (prefers-reduced-motion: reduce) {",
    )
    assert all(selector in system_matrix_css for selector in required_system_matrix)

    reduced_motion_blocks = re.findall(
        r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{((?:[^{}]|\{[^{}]*\})*)\}",
        system_matrix_css,
        flags=re.DOTALL,
    )
    uncommented_blocks = [
        re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL) for block in reduced_motion_blocks
    ]

    def has_reduced_motion_declaration(selector: str, declaration: str) -> bool:
        rule = re.compile(
            rf"{re.escape(selector)}\s*\{{[^}}]*\b{re.escape(declaration)}\s*;[^}}]*\}}",
            flags=re.DOTALL,
        )
        return any(rule.search(block) for block in uncommented_blocks)

    assert has_reduced_motion_declaration(
        '.dash__systems[data-first-paint="true"] .dash-sys-row', "animation: none"
    )
    assert has_reduced_motion_declaration(".dash-sys-row:hover", "transform: none")


def test_dashboard_density_and_kpi_compression_hooks_are_removed():
    """컨테이너 쿼리 이관 뒤 JS 밀도·KPI 압축 훅은 되살아나면 안 된다."""
    frontend = Path(__file__).resolve().parents[2] / "app/web/frontend"
    dashboard_css = (frontend / "styles/dashboard.css").read_text(encoding="utf-8")
    kpi_card_css = (frontend / "components/kpi-card/styles.css").read_text(encoding="utf-8")

    assert "data-density" not in dashboard_css
    assert "data-kpi-compress" not in kpi_card_css


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
        '<script src="/static/admin-dashboard.js?v=22" defer></script>',
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


def test_fg006_flags_former_allowlisted_template(tmp_path):
    """P3-4 마지막 이관 후에는 예외 없이 같은 구조 위반으로 잡혀야 한다."""
    _write(
        tmp_path,
        "app/web/templates/mobile_trigger.html",
        "{% set status_pill = {'passed': 'a', 'error': 'b'} %}",
    )
    problems = check_fg006_no_template_status_literals(tmp_path)
    assert len(problems) == 1
    assert "mobile_trigger.html" in problems[0]


def test_fg006_has_no_allowlist():
    """allowlist 가 남아 있으면 마지막 템플릿 이관 후에도 규칙이 다시 새기 시작한다."""
    import scripts.check_frontend_gates as gates

    assert not hasattr(gates, "FG006_ALLOWLIST")


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
