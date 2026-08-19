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
        return [f"{self._base_url}/{name}" for name in self._entry(entry).get("css", [])]


# 앱 전체가 공유하는 단일 인스턴스. Jinja2Templates() 호출부가 네 군데로 나뉘어 있어
# (각자 별도의 Environment 를 갖는다) 매번 새로 만들면 파일 stat/캐시 관리가 중복된다.
_default_manifest = AssetManifest(
    Path(__file__).resolve().parent / "static/dist/.vite/manifest.json",
    base_url="/static/dist",
)

asset_js = _default_manifest.js_url
asset_css = _default_manifest.css_urls
