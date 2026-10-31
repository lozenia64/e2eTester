"""차트 라이브러리 self-host — 번들이 실제로 만들어지고 격리되는가.

CDN 을 npm 으로 바꾸는 변경의 실패 양상은 둘이다.
1) rollup 이 사전 번들된 거대 UMD 를 처리하지 못해 빌드가 깨진다 — 빌드가 잡는다
2) 빌드는 되는데 import 가 트리셰이킹돼 빈 번들이 나온다 — 화면이 조용히 차트를 잃는다

2)는 빌드가 잡지 못한다. 크기 하한 단언이 유일한 방어선이다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.web.asset_manifest import AssetManifest

DIST = Path("app/web/static/dist")
MANIFEST = DIST / ".vite/manifest.json"
ASSET_MANIFEST = AssetManifest(MANIFEST, base_url="/static/dist")
TEMPLATES = Path("app/web/templates")

PLOTLY = "vendor/plotly.min.js"

VENDOR_ENTRIES = (
    "entries/vendor-echarts.ts",
    PLOTLY,
)

VENDOR_TEMPLATE_REFS = {
    "admin/runs.html": ("entries/vendor-echarts.ts",),
    "admin/stats.html": (PLOTLY,),
    "insights.html": (PLOTLY,),
}

PLOTLY_CONSUMERS = {
    "admin/stats.html": "/static/admin-stats.js",
    "insights.html": "/static/insights.js",
}


@pytest.fixture(scope="module")
def manifest() -> dict:
    assert MANIFEST.exists(), f"{MANIFEST} 가 없습니다. `npm run build` 를 먼저 실행하세요."
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _js_closure(manifest: dict, entry: str) -> set[str]:
    """엔트리가 실제로 끌어오는 JS 파일 집합(정적 import 폐포)."""
    seen: set[str] = set()

    def walk(key: str) -> None:
        if key in seen or key not in manifest:
            return
        seen.add(key)
        for imported in manifest[key].get("imports", []):
            walk(imported)

    walk(entry)
    return {manifest[key]["file"] for key in seen}


@pytest.mark.parametrize("entry", VENDOR_ENTRIES)
def test_vendor_entry_resolves_in_manifest(entry: str) -> None:
    assert ASSET_MANIFEST.js_url(entry).startswith("/static/dist/assets/")


@pytest.mark.parametrize(
    ("entry", "min_bytes"),
    [
        ("entries/vendor-echarts.ts", 300_000),
        (PLOTLY, 500_000),
    ],
)
def test_vendor_bundle_actually_contains_the_library(
    manifest: dict, entry: str, min_bytes: int
) -> None:
    """공유 청크를 포함한 정적 import 전체가 라이브러리를 담아야 한다.

    대시보드의 ECharts 지연 로딩과 기존 전역 브리지는 같은 청크를 공유한다.
    엔트리 한 파일만 재면 정상적인 코드 분할을 라이브러리 누락으로 오판한다.
    """
    size = sum((DIST / file).stat().st_size for file in _js_closure(manifest, entry))
    assert size > min_bytes, (
        f"{entry} 번들이 {size}B 로 너무 작습니다 — 라이브러리가 안 실렸습니다."
    )


@pytest.mark.parametrize("entry", VENDOR_ENTRIES)
def test_main_bundle_does_not_include_vendor_entry(manifest: dict, entry: str) -> None:
    """일간 현황·로그인 등 일반 페이지가 차트 무게를 받지 않는다(설계 §3.1)."""
    assert manifest[entry]["file"] not in _js_closure(manifest, "entries/main.ts")


@pytest.mark.parametrize("entry", VENDOR_ENTRIES)
def test_wall_bundle_does_not_include_vendor_entry(manifest: dict, entry: str) -> None:
    """상황판은 3~5m 거리용 표시 화면이다 — 차트 라이브러리를 받을 이유가 없다."""
    assert manifest[entry]["file"] not in _js_closure(manifest, "entries/wall.ts")


@pytest.mark.parametrize(("template", "entries"), sorted(VENDOR_TEMPLATE_REFS.items()))
def test_template_loads_its_vendor_entries(template: str, entries: tuple[str, ...]) -> None:
    """빌드만 되고 템플릿이 안 부르면 화면에서 차트가 사라진다.

    P3-2 에서 wall.ts 가 kpi-card CSS 를 import 하지 않아 상황판이 무스타일로
    나갔던 것과 같은 종류의 누락이다.
    """
    source = (TEMPLATES / template).read_text(encoding="utf-8")
    for entry in entries:
        assert entry in source, f"{template} 이 {entry} 를 로드하지 않습니다."


@pytest.mark.parametrize(("template", "consumer"), sorted(PLOTLY_CONSUMERS.items()))
def test_plotly_loads_before_its_consumer(template: str, consumer: str) -> None:
    """소비 스크립트는 전역 `Plotly` 가 없으면 조용히 return 해 차트만 사라진다.

    순서가 뒤집히거나 소비 스크립트가 defer 를 잃으면 문서 순서 보장이 깨진다.
    """
    source = (TEMPLATES / template).read_text(encoding="utf-8")
    tag = f'assets.asset_classic_script("{PLOTLY}")'
    assert tag in source
    match = re.search(rf'<script src="{re.escape(consumer)}[^"]*" defer></script>', source)
    assert match, f"{template} 의 {consumer} 가 defer 스크립트가 아닙니다."
    assert source.index(tag) < match.start()


@pytest.mark.parametrize("template", sorted(VENDOR_TEMPLATE_REFS))
def test_template_has_no_cdn_script(template: str) -> None:
    source = (TEMPLATES / template).read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net" not in source
