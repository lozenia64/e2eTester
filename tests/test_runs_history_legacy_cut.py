"""Cycle 4 레거시 절단 계약 — 지운 것과 남긴 것(설계 §3.4·D10)."""

from __future__ import annotations

from pathlib import Path

APP_JS = Path("app/web/static/app.js")

# execute.html:385 의 "진행 중 / 최근 Run" 이 쓰는 코드 — 지우면 그 화면이 깨진다.
SHARED_WITH_EXECUTE = (
    "function formatRunTimestamp",
    "function createRunListItem",
    "function buildExecutionGroups",
    "function createSuiteStripRow",
    "function renderExecutionGroups",
    "function renderRunList",
    "async function refreshRunList",
    "function bindRunsOverview",
)


def test_runs_history_binding_is_gone():
    source = APP_JS.read_text(encoding="utf-8")
    assert "bindRunsHistory" not in source
    assert "runs-history-list" not in source
    assert "RUN_HISTORY_LIMIT" not in source


def test_execute_screen_code_survives():
    source = APP_JS.read_text(encoding="utf-8")
    for marker in SHARED_WITH_EXECUTE:
        assert marker in source, f"{marker} 는 execute.html 이 쓴다 — 지우면 안 된다"


def test_execute_template_still_declares_runs_list():
    markup = Path("app/web/templates/execute.html").read_text(encoding="utf-8")
    assert 'id="runs-list"' in markup
