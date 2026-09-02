"""Run 이력 격자 레이아웃 계약 — 승격 규격(설계 §3.1·D1)."""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE = Path("app/web/templates/runs_history.html")

COLOR_UTILITY = re.compile(
    r"\b(?:bg|text|border)-(?:gray|slate|zinc|indigo|emerald|green|amber|yellow|red|blue)-\d{2,3}\b"
)


def test_uses_promotion_shell_root():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert 'class="rhist"' in markup


def test_declares_grid_and_drilldown_hooks():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert 'id="rhist-grid"' in markup
    assert 'id="rhist-drill"' in markup


def test_legacy_hooks_are_gone():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert "runs-history-list" not in markup
    assert "runs-history-status" not in markup


def test_no_color_utilities():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert COLOR_UTILITY.findall(markup) == []


def test_loads_own_entry_without_static_reference():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert "entries/runs-history.ts" in markup
    assert "/static/" not in markup
