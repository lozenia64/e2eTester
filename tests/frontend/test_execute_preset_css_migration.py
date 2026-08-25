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
    return css[start:]


def test_preset_css_is_owned_by_execute_stylesheet():
    app_css = APP_CSS.read_text(encoding="utf-8")
    execute_css = EXECUTE_PRESETS_CSS.read_text(encoding="utf-8")

    assert START not in app_css
    assert END in app_css
    preset = _bounded_section(execute_css)
    assert preset.startswith(START)
    for selector in PRESET_SELECTORS:
        assert selector not in app_css
        assert selector in preset
    assert ".preset-panel {" in preset
    assert "border: 1px solid var(--c-violet-125);" in preset
    assert ".preset-chip--radio.is-active .preset-chip__check" in preset
    assert "background: var(--c-violet-600);" in preset
    assert ".suite-preset-status--warn" in preset


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
    assert "border: 1px solid var(--c-slate-300);" in graph_css
    assert "stroke: var(--c-indigo-500);" in graph_css
    assert "min-height: 40cqh;" in graph_css
