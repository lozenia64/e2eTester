"""대시보드 엔트리 CSS의 head 로딩 정적 계약."""

from __future__ import annotations

from pathlib import Path


BASE = Path("app/web/templates/base.html")
DASHBOARD = Path("app/web/templates/dashboard.html")


def _block(template: str, name: str) -> str:
    start = template.index(f"{{% block {name} %}}")
    end = template.index("{% endblock %}", start)
    return template[start:end]


def test_dashboard_entry_css_is_rendered_in_head_extra_not_scripts() -> None:
    base = BASE.read_text(encoding="utf-8")
    dashboard = DASHBOARD.read_text(encoding="utf-8")

    assert "{% block head_extra %}{% endblock %}" in base
    assert base.index("{% block head_extra %}{% endblock %}") < base.index("</head>")

    head_extra = _block(dashboard, "head_extra")
    assert '{% import "_assets.html" as dash_assets %}' in head_extra
    assert 'dash_assets.asset_styles("entries/dashboard.ts")' in head_extra
    assert 'asset_styles("entries/dashboard.ts")' not in _block(dashboard, "scripts")
