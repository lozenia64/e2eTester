import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_CSS = ROOT / "app/web/frontend/styles/app.css"
EXECUTE_CSS = ROOT / "app/web/frontend/styles/execute.css"
EXECUTE_GRAPH_CSS = ROOT / "app/web/frontend/styles/execute-graph.css"
EXECUTE_PRESETS_CSS = ROOT / "app/web/frontend/styles/execute-presets.css"

START = "/* ===== 인증 프리셋 (내 점검 세트) ===================================== */"
END = '/* ─────────────────────────────────────────────────────────────────────────\n   진행 중 / 최근 Run: "실행 단위" 가로 스트립'

PRESET_SELECTORS = (
    ".preset-panel",
    ".preset-panel__head",
    ".preset-panel__star",
    ".preset-btn-primary",
    ".preset-btn-ghost",
    ".preset-btn-ghost:hover",
    ".preset-btn-primary",
    ".preset-btn-primary:hover",
    ".preset-btn-primary:disabled",
    ".preset-chip-row",
    ".preset-empty",
    ".preset-empty--warn",
    ".preset-chip",
    ".preset-chip:hover",
    ".preset-chip--just-applied",
    ".preset-chip__apply",
    ".preset-chip__name",
    ".preset-chip__meta",
    ".preset-chip__delete",
    ".preset-chip__delete:hover",
    ".preset-chip--radio",
    ".preset-chip__check",
    ".preset-chip__body",
    ".preset-chip--radio.is-active",
    ".preset-chip--radio.is-active .preset-chip__check",
    ".preset-save-form",
    ".preset-name-input",
    ".suite-preset-panel",
    ".suite-preset-panel__head",
    ".suite-preset-status",
    ".suite-preset-status--ok",
    ".suite-preset-status--pending",
    ".suite-preset-status--warn",
)


def _bounded_section(css: str) -> str:
    start = css.index(START)
    destination = css[start:]
    assert destination.rstrip().endswith("}"), "프리셋 stylesheet는 CSS rule로 끝나야 한다"
    return destination[: len(destination.rstrip())]


def _rule_blocks(css: str) -> list[tuple[list[str], str]]:
    blocks = []
    for match in re.finditer(r"(?ms)([^{}]+)\{([^{}]*)\}", css):
        header = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.DOTALL)
        selectors = [part.strip() for part in header.split(",") if part.strip()]
        blocks.append((selectors, match.group(2)))
    return blocks


def _assert_rule_declaration(css: str, selector: str, declaration: str) -> None:
    assert any(
        selector in selectors and declaration in body
        for selectors, body in _rule_blocks(css)
    ), f"{selector} 규칙에 {declaration} 선언이 없다"


def test_preset_css_is_owned_by_execute_stylesheet():
    app_css = APP_CSS.read_text(encoding="utf-8")
    execute_css = EXECUTE_PRESETS_CSS.read_text(encoding="utf-8")

    assert START not in app_css
    assert END in app_css
    preset = _bounded_section(execute_css)
    assert preset.startswith(START)
    assert len(PRESET_SELECTORS) == 33
    assert len(set(PRESET_SELECTORS)) == 32
    for selector in PRESET_SELECTORS:
        assert selector not in app_css
        assert selector in preset
    _assert_rule_declaration(
        preset, ".preset-panel", "border: 1px solid var(--c-violet-125);"
    )
    _assert_rule_declaration(
        preset,
        ".preset-chip--radio.is-active .preset-chip__check",
        "background: var(--c-violet-600);",
    )
    _assert_rule_declaration(
        preset, ".suite-preset-status--warn", "color: var(--st-anomaly-text);"
    )


GRAPH_SELECTORS = (
    ".module-graph-viewport",
    ".module-graph-canvas",
    ".module-graph-edges",
    ".module-graph-grid",
    ".module-graph-node",
    '.module-graph-viewport[data-graph-compact="compact"] .module-graph-node',
    '.module-graph-viewport[data-graph-compact="dense"] .module-graph-node',
    ".module-graph-node__header",
    '.module-graph-viewport[data-graph-compact="dense"] .module-graph-node__header',
    ".module-graph-node:hover",
    ".module-graph-node.is-unselected",
    ".module-graph-node.is-unselected:hover",
    ".module-graph-node.is-locked",
    ".module-graph-node.is-locked:hover",
    ".module-graph-node:focus-visible",
    ".module-graph-order",
    '.module-graph-viewport[data-graph-compact="dense"] .module-graph-order',
    ".module-graph-title",
    ".module-graph-node.is-unselected .module-graph-order",
    ".module-graph-node.is-locked .module-graph-order",
    ".module-graph-node.is-unselected .module-graph-title",
    ".module-graph-node.is-locked .module-graph-title",
    ".module-graph-edge",
    ".module-graph-edge.is-active",
    ".module-graph-edge.is-muted",
    ".exec-graph",
    ".exec-graph .module-graph-viewport",
)


def test_module_graph_css_is_owned_by_graph_stylesheet():
    app_css = APP_CSS.read_text(encoding="utf-8")
    execute_css = EXECUTE_CSS.read_text(encoding="utf-8")
    graph_css = EXECUTE_GRAPH_CSS.read_text(encoding="utf-8")

    for selector in GRAPH_SELECTORS:
        assert selector not in app_css
        assert selector not in execute_css
        assert selector in graph_css
    _assert_rule_declaration(
        graph_css, ".module-graph-node", "border: 1px solid var(--c-slate-300);"
    )
    _assert_rule_declaration(
        graph_css, ".module-graph-edge.is-active", "stroke: var(--c-indigo-500);"
    )
    _assert_rule_declaration(
        graph_css, ".exec-graph .module-graph-viewport", "min-height: 40cqh;"
    )
