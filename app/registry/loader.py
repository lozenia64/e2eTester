from __future__ import annotations

from pathlib import Path

import yaml

from app.core.models import ModuleDefinition, RunFormField, SystemDefinition


class ModuleRegistry:
    def __init__(self, manifest_dir: Path | None = None) -> None:
        self._manifest_dir = manifest_dir or Path("app/registry/manifests")
        self._systems = self._load_systems()

    def list_systems(self) -> list[SystemDefinition]:
        return list(self._systems.values())

    def get_system(self, system_code: str) -> SystemDefinition:
        try:
            return self._systems[system_code]
        except KeyError as exc:
            raise KeyError(f"Unknown system code: {system_code}") from exc

    def _load_systems(self) -> dict[str, SystemDefinition]:
        systems: dict[str, SystemDefinition] = {}
        for manifest_path in sorted(self._manifest_dir.glob("*.yaml")):
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            modules = [ModuleDefinition(**module_data) for module_data in raw.get("modules", [])]
            system = SystemDefinition(
                system_code=raw["system_code"],
                name=raw["name"],
                description=raw["description"],
                modules=modules,
                run_form=[RunFormField(**field_data) for field_data in raw.get("run_form", [])],
            )
            systems[system.system_code] = system
        return systems
