"""Contract tests — manifest workflow_step ↔ automation Flow registry alignment."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.automation.wiring import _ENGINE_BUILDERS

_REPO = Path(__file__).resolve().parents[2]
_MANIFEST_GLOB = "app/systems/*/manifest.yaml"


def _manifest_paths() -> list[Path]:
    return sorted(_REPO.glob(_MANIFEST_GLOB))


def _workflow_steps(manifest_path: Path) -> set[str]:
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    return {m["workflow_step"] for m in data.get("modules", [])}


@pytest.mark.parametrize("manifest_path", _manifest_paths(), ids=lambda p: p.parent.name)
def test_manifest_workflow_steps_have_automation_flows(manifest_path: Path):
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    modules = data.get("modules", [])
    if not modules:
        pytest.skip("no modules")
    execution_mode = modules[0]["execution_mode"]
    builder = _ENGINE_BUILDERS.get(execution_mode)
    assert builder is not None, f"No automation engine for {execution_mode}"
    engine = builder()
    steps = _workflow_steps(manifest_path)
    missing = [step for step in sorted(steps) if not engine.has_flow(step)]
    assert not missing, f"{manifest_path.parent.name}: missing flows for {missing}"
