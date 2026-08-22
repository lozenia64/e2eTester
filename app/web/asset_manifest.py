"""Vite manifest 로더 — 템플릿이 해시 파일명을 해석한다.

수동 `?v=` 캐시버스팅을 대체한다. 파일 mtime 이 바뀌면 다시 읽으므로
개발 중 재빌드가 서버 재시작 없이 반영된다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ManifestMissingError(RuntimeError):
    """manifest 또는 엔트리를 찾지 못했을 때. 메시지에 해결책을 담는다."""


class AssetManifest:
    def __init__(self, path: Path, *, base_url: str) -> None:
        self._path = Path(path)
        self._base_url = base_url.rstrip("/")
        self._cache: dict[str, Any] = {}
        self._mtime: float | None = None

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            msg = f"Vite manifest 가 없습니다: {self._path}. `npm run build` 를 먼저 실행하세요."
            raise ManifestMissingError(msg)
        mtime = self._path.stat().st_mtime
        if self._mtime != mtime:
            self._cache = json.loads(self._path.read_text(encoding="utf-8"))
            self._mtime = mtime
        return self._cache

    def _entry(self, entry: str) -> dict[str, Any]:
        manifest = self._load()
        record = manifest.get(entry)
        if record is None:
            known = ", ".join(sorted(manifest)) or "(비어 있음)"
            msg = (
                f"manifest 에 엔트리가 없습니다: {entry}. 등록된 엔트리: {known}. "
                "vite.config.ts 의 rollupOptions.input 을 확인하고 `npm run build` 를 실행하세요."
            )
            raise ManifestMissingError(msg)
        return record

    def js_url(self, entry: str) -> str:
        return f"{self._base_url}/{self._entry(entry)['file']}"

    def css_urls(self, entry: str) -> list[str]:
        """엔트리가 실제로 싣는 전체 CSS — 임포트한 공유 청크의 CSS까지 따라간다.

        Vite 는 두 엔트리가 같은 모듈을 임포트하면 그 모듈을 공유 청크로 끌어올리고
        CSS 도 그 청크로 옮긴다. 엔트리 자신의 css 배열만 읽으면 그 CSS 가 어느
        페이지에도 실리지 않는다 — 엔트리가 하나였을 때는 공유 청크가 없어 이 결함이
        드러나지 않았다(P3-2 가 두 번째 엔트리를 추가하며 노출).
        """
        self._entry(entry)
        manifest = self._load()
        seen: set[str] = set()
        urls: list[str] = []

        def walk(key: str) -> None:
            if key in seen:
                return
            seen.add(key)
            record = manifest.get(key)
            if record is None:
                return
            for imported in record.get("imports", []):
                walk(imported)
            for name in record.get("css", []):
                url = f"{self._base_url}/{name}"
                if url not in urls:
                    urls.append(url)

        walk(entry)
        return urls


# 앱 전체가 공유하는 단일 인스턴스. Jinja2Templates() 호출부가 네 군데로 나뉘어 있어
# (각자 별도의 Environment 를 갖는다) 매번 새로 만들면 파일 stat/캐시 관리가 중복된다.
_default_manifest = AssetManifest(
    Path(__file__).resolve().parent / "static/dist/.vite/manifest.json",
    base_url="/static/dist",
)

asset_js = _default_manifest.js_url
asset_css = _default_manifest.css_urls

# Jinja 검색 경로 SSOT. `app/web/frontend` 가 함께 있어야 컴포넌트가 마크업을
# 자기 폴더에 둘 수 있다 — {% import "components/status-badge/macro.jinja" %} 는
# templates/ 하나만 검색하면 TemplateNotFound 로 죽는다.
# 네 군데 Jinja2Templates() 호출부가 전부 이 상수를 쓴다(한 곳만 고쳐 어긋나는 걸 막는다).
TEMPLATE_SEARCH_DIRS: list[str] = ["app/web/templates", "app/web/frontend"]
