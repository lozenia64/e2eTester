import json

import pytest

from app.web.asset_manifest import AssetManifest, ManifestMissingError

SAMPLE = {
    "entries/main.ts": {
        "file": "assets/main-a1b2c3d4.js",
        "src": "entries/main.ts",
        "isEntry": True,
        "css": ["assets/main-e5f6a7b8.css"],
    }
}


@pytest.fixture()
def manifest_path(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return path


def test_js_url_resolves_hashed_filename(manifest_path):
    manifest = AssetManifest(manifest_path, base_url="/static/dist")
    assert manifest.js_url("entries/main.ts") == "/static/dist/assets/main-a1b2c3d4.js"


def test_css_urls_resolves_hashed_filenames(manifest_path):
    manifest = AssetManifest(manifest_path, base_url="/static/dist")
    assert manifest.css_urls("entries/main.ts") == ["/static/dist/assets/main-e5f6a7b8.css"]


def test_unknown_entry_raises_with_actionable_message(manifest_path):
    manifest = AssetManifest(manifest_path, base_url="/static/dist")
    with pytest.raises(ManifestMissingError) as excinfo:
        manifest.js_url("entries/nope.ts")
    assert "npm run build" in str(excinfo.value)


def test_missing_manifest_file_raises_with_actionable_message(tmp_path):
    manifest = AssetManifest(tmp_path / "absent.json", base_url="/static/dist")
    with pytest.raises(ManifestMissingError) as excinfo:
        manifest.js_url("entries/main.ts")
    assert "npm run build" in str(excinfo.value)


def test_manifest_is_reloaded_when_file_changes(manifest_path):
    """개발 중 재빌드가 서버 재시작 없이 반영되어야 한다."""
    manifest = AssetManifest(manifest_path, base_url="/static/dist")
    assert manifest.js_url("entries/main.ts").endswith("main-a1b2c3d4.js")
    changed = {"entries/main.ts": {"file": "assets/main-99999999.js", "isEntry": True}}
    manifest_path.write_text(json.dumps(changed), encoding="utf-8")
    assert manifest.js_url("entries/main.ts").endswith("main-99999999.js")
