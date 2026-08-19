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
