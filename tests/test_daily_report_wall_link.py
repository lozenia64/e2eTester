"""일간 리포트의 상황판 딥링크 — 기본은 링크 없는 자족적 메일.

P3-3 D6 은 링크를 뺐다. 이유가 둘이었는데 "대시보드는 로그인이 필요하다" 쪽은
P3-2 가 /wall 을 비인증으로 열며 해소됐고, "공개 URL env 가 없다" 만 남았다.
이 테스트가 고정하는 것: env 를 켠 사람만 링크를 얻는다.
"""

from __future__ import annotations

import pytest

from app.notifications.report_renderer import render_daily_report_html

CONTEXT = {
    "headline": "정상",
    "tone": "passed",
    "status_value": "PASSED",
    "date_label": "2026-08-21",
    "kpis": [("통과율", 100, "%")],
    "systems": [],
    "issues": [],
}


def test_no_link_when_wall_url_is_absent() -> None:
    """기본값이 자족적 메일이다 — 기존 동작이 바뀌지 않는다."""
    html = render_daily_report_html(CONTEXT)
    assert "http://" not in html
    assert "https://" not in html


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_no_link_for_blank_wall_url(blank) -> None:
    """빈 문자열 env 가 'http:///wall' 같은 깨진 링크가 되지 않아야 한다."""
    html = render_daily_report_html(CONTEXT, wall_url=blank)
    assert "http" not in html


def test_link_is_rendered_when_wall_url_is_given() -> None:
    html = render_daily_report_html(CONTEXT, wall_url="https://e2e.example.com/wall")
    assert 'href="https://e2e.example.com/wall"' in html


def test_link_text_is_korean() -> None:
    html = render_daily_report_html(CONTEXT, wall_url="https://e2e.example.com/wall")
    assert "상황판" in html
