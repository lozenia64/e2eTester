from __future__ import annotations

from pathlib import Path


class ArtifactManager:
    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir or Path("artifacts")

    def module_dir(self, run_id: str, module_id: str) -> Path:
        path = self._root_dir / run_id / module_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def screenshot_path(self, run_id: str, module_id: str) -> Path:
        return self.module_dir(run_id, module_id) / "final.png"

    def log_path(self, run_id: str, module_id: str) -> Path:
        return self.module_dir(run_id, module_id) / "execution.log"

    def relative_path(self, path: Path) -> str:
        return "/" + path.as_posix()
