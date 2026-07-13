from __future__ import annotations

import shutil
from pathlib import Path


class ArtifactManager:
    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir or Path("artifacts")

    def run_dir(self, run_id: str) -> Path:
        return self._root_dir / run_id

    def module_dir(self, run_id: str, module_id: str) -> Path:
        path = self._root_dir / run_id / module_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def screenshot_path(self, run_id: str, module_id: str) -> Path:
        return self.module_dir(run_id, module_id) / "final.png"

    def log_path(self, run_id: str, module_id: str) -> Path:
        return self.module_dir(run_id, module_id) / "execution.log"

    def relative_path(self, path: Path) -> str:
        """Return a web-style artifact path (POSIX slashes, optional /artifacts prefix)."""
        try:
            rel = path.resolve().relative_to(self._root_dir.resolve())
        except ValueError as exc:
            msg = f"artifact path escapes root: {path!r}"
            raise ValueError(msg) from exc
        return "/artifacts/" + rel.as_posix()

    def delete_run_artifacts(self, run_id: str) -> None:
        run_dir = self.run_dir(run_id)
        if run_dir.exists():
            shutil.rmtree(run_dir)

    def path_from_relative(self, relative_path: str) -> Path:
        """Resolve a stored artifact path back to a filesystem path under the artifact root."""
        normalized = relative_path.replace("\\", "/").lstrip("/")
        if normalized.startswith("artifacts/"):
            normalized = normalized.removeprefix("artifacts/")
        target = (self._root_dir / normalized).resolve()
        root = self._root_dir.resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            msg = f"artifact path escapes root: {relative_path!r}"
            raise ValueError(msg) from exc
        return target
