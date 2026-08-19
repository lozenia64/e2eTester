from pathlib import Path

from scripts.check_frontend_gates import (
    check_fg001_no_cdn,
    check_fg002_no_hex,
    check_fg003_status_source,
    check_fg004_file_size,
    check_fg005_no_static_ref,
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


def test_fg001_allows_exact_allow_listed_chart_cdn(tmp_path):
    """FG001_EXCEPTIONS 에 등록된 파일+URL 쌍은 차트 라이브러리 예외로 통과한다."""
    _write(
        tmp_path,
        "app/web/templates/insights.html",
        '<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js" '
        'crossorigin="anonymous"></script>',
    )
    assert check_fg001_no_cdn(tmp_path) == []


def test_fg001_flags_different_url_in_exception_file(tmp_path):
    """예외 대상 파일이라도 등록되지 않은 다른 URL 은 여전히 걸린다."""
    _write(
        tmp_path,
        "app/web/templates/insights.html",
        '<script src="https://unpkg.com/some-other-lib@1"></script>',
    )
    problems = check_fg001_no_cdn(tmp_path)
    assert len(problems) == 1
    assert "unpkg.com" in problems[0]


def test_fg001_flags_exception_url_in_different_file(tmp_path):
    """예외 등록된 URL 이라도 다른 파일에서 쓰이면 여전히 걸린다(파일 단위 allowlist 아님)."""
    _write(
        tmp_path,
        "app/web/templates/dashboard.html",
        '<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js" '
        'crossorigin="anonymous"></script>',
    )
    problems = check_fg001_no_cdn(tmp_path)
    assert len(problems) == 1
    assert "plotly" in problems[0]


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
