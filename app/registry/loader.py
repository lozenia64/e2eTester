from __future__ import annotations

from pathlib import Path

import yaml

from app.core.models import ModuleDefinition, RunFormField, SystemDefinition


class ModuleRegistry:
    def __init__(self, manifest_dir: Path | None = None) -> None:
        self._manifest_dir = manifest_dir or Path(__file__).resolve().parents[1] / "systems"
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
        for manifest_path in sorted(self._manifest_dir.glob("*/manifest.yaml")):
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            modules = [ModuleDefinition(**module_data) for module_data in raw.get("modules", [])]
            system = SystemDefinition(
                system_code=raw["system_code"],
                name=raw["name"],
                description=raw["description"],
                modules=modules,
                run_form=[RunFormField(**field_data) for field_data in raw.get("run_form", [])],
                supported_auth_methods=raw.get("supported_auth_methods", []),
            )
            self._validate_system_definition(system, manifest_path)
            systems[system.system_code] = system
        return systems

    @staticmethod
    def _validate_system_definition(system: SystemDefinition, manifest_path: Path) -> None:
        seen_module_ids: set[str] = set()
        module_index = {module.module_id: module for module in system.modules}

        for module in system.modules:
            if module.module_id in seen_module_ids:
                raise ValueError(f"Duplicate module_id in {manifest_path}: {module.module_id}")
            seen_module_ids.add(module.module_id)
            if module.system_code != system.system_code:
                raise ValueError(
                    f"Module system_code mismatch in {manifest_path}: "
                    f"{module.module_id} belongs to {module.system_code}, expected {system.system_code}"
                )
            for dependency in module.depends_on:
                dependency_module = module_index.get(dependency)
                if dependency_module is None:
                    raise ValueError(
                        f"Unknown dependency in {manifest_path}: {module.module_id} -> {dependency}"
                    )
                if dependency_module.order >= module.order:
                    raise ValueError(
                        f"Dependency order must precede dependent in {manifest_path}: "
                        f"{module.module_id} depends on {dependency}"
                    )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(module_id: str) -> None:
            if module_id in visited:
                return
            if module_id in visiting:
                raise ValueError(f"Dependency cycle detected in {manifest_path}: {module_id}")
            visiting.add(module_id)
            for dependency in module_index[module_id].depends_on:
                visit(dependency)
            visiting.remove(module_id)
            visited.add(module_id)

        for module_id in module_index:
            visit(module_id)
