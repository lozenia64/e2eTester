"""Tests for cross-platform artifact path normalization."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.platform.artifact_manager import ArtifactManager


def test_relative_path_uses_web_prefix(tmp_path: Path) -> None:
    manager = ArtifactManager(root_dir=tmp_path / "artifacts")
    module_dir = manager.module_dir("run-1", "login")
    screenshot = module_dir / "final.png"
    screenshot.write_bytes(b"png")

    assert manager.relative_path(screenshot) == "/artifacts/run-1/login/final.png"


@pytest.mark.parametrize(
    "stored",
    [
        "/artifacts/run-1/login/final.png",
        "artifacts/run-1/login/final.png",
        "run-1/login/final.png",
    ],
)
def test_path_from_relative_accepts_legacy_forms(tmp_path: Path, stored: str) -> None:
    root = tmp_path / "artifacts"
    target = root / "run-1" / "login" / "final.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"png")

    manager = ArtifactManager(root_dir=root)
    assert manager.path_from_relative(stored) == target.resolve()


def test_path_from_relative_rejects_escape(tmp_path: Path) -> None:
    manager = ArtifactManager(root_dir=tmp_path / "artifacts")
    with pytest.raises(ValueError, match="escapes root"):
        manager.path_from_relative("/artifacts/../../etc/passwd")
