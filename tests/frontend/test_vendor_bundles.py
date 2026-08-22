"""차트 라이브러리 self-host — 번들이 실제로 만들어지고 격리되는가.

CDN 을 npm 으로 바꾸는 변경의 실패 양상은 둘이다.
1) rollup 이 사전 번들된 거대 UMD 를 처리하지 못해 빌드가 깨진다 — 빌드가 잡는다
2) 빌드는 되는데 import 가 트리셰이킹돼 빈 번들이 나온다 — 화면이 조용히 차트를 잃는다

2)는 빌드가 잡지 못한다. 크기 하한 단언이 유일한 방어선이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.web.asset_manifest import AssetManifest

DIST = Path("app/web/static/dist")
MANIFEST = DIST / ".vite/manifest.json"
ASSET_MANIFEST = AssetManifest(MANIFEST, base_url="/static/dist")

VENDOR_ENTRIES = (
    "entries/vendor-chart.ts",
    "entries/vendor-echarts.ts",
    "entries/vendor-plotly.ts",
)


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
        ("entries/vendor-chart.ts", 100_000),
        ("entries/vendor-echarts.ts", 300_000),
        ("entries/vendor-plotly.ts", 500_000),
    ],
)
def test_vendor_bundle_actually_contains_the_library(
    manifest: dict, entry: str, min_bytes: int
) -> None:
    """import 가 트리셰이킹으로 사라지면 빈 번들이 나온다 — 크기로 잡는다."""
    size = (DIST / manifest[entry]["file"]).stat().st_size
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
