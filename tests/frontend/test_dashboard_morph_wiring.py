"""대시보드 morph 배선 정적 계약.

30초 폴링이 innerHTML 통짜 교체를 하면 스크롤·포커스·진행 중 애니메이션이
매번 소실된다(설계 §1.3). 세 존이 morph 로 교체되는지 파일에서 직접 확인한다.
"""

from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("app/web/templates/dashboard.html")

ZONE_HOSTS = ("dash-host-kpi", "dash-host-matrix", "dash-host-activity")


def test_dashboard_declares_morph_extension():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert 'hx-ext="morph"' in html, "idiomorph 확장이 선언되지 않았다"


def test_all_three_zone_hosts_exist():
    html = DASHBOARD.read_text(encoding="utf-8")
    for host in ZONE_HOSTS:
        assert f'id="{host}"' in html, f"{host} 호스트가 없다"


def test_every_zone_uses_morph_swap():
    html = DASHBOARD.read_text(encoding="utf-8")
    assert html.count('hx-swap="morph:innerHTML"') == len(ZONE_HOSTS)
    assert 'hx-swap="innerHTML"' not in html, "통짜 innerHTML 교체가 남아 있다"
