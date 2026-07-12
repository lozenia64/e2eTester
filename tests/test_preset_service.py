"""인증 프리셋 서비스 단위 테스트 — 검증·소유권 격리·CRUD."""

from __future__ import annotations

import pytest

from app.contexts.run.application.planner import RunPlanner
from app.core.requests import CreatePresetRequest, UpdatePresetRequest
from app.orchestrator.preset_service import PresetService
from app.registry.loader import ModuleRegistry
from app.storage.sqlite_preset_repository import SqlitePresetRepository


class _FakeRunService:
    """PresetService 가 쓰는 두 메서드만 노출하는 경량 대역(실 RunService 와 동일 규칙)."""

    def __init__(self, registry: ModuleRegistry) -> None:
        self._registry = registry
        self._planner = RunPlanner()

    def get_system(self, system_code: str):
        return self._registry.get_system(system_code)

    def validate_run_request(self, system_code, input_data=None, selected_module_ids=None):
        system = self._registry.get_system(system_code)
        return self._planner.prepare(system, input_data, selected_module_ids)


def _service(tmp_path) -> PresetService:
    registry = ModuleRegistry()
    repository = SqlitePresetRepository(str(tmp_path / "presets.db"))
    return PresetService(repository=repository, run_service=_FakeRunService(registry))


def _hom_phone_input() -> dict[str, str]:
    return {
        "browser_mode": "headed",
        "auth_method": "phone",
        "name": "홍길동",
        "birthdate": "19900101",
        "gender": "male",
        "residency": "domestic",
        "carrier": "skt",
        "phone_number": "01012345678",
    }


async def test_create_and_list_preset(tmp_path):
    service = _service(tmp_path)
    preset = await service.create_preset(
        "user_1",
        CreatePresetRequest(system_code="hom", name="홍길동 휴대폰", input_data=_hom_phone_input()),
    )
    assert preset.system_code == "hom"
    assert preset.auth_method == "phone"
    assert preset.input_data["phone_number"] == "01012345678"

    presets = await service.list_presets("user_1")
    assert [item.preset_id for item in presets] == [preset.preset_id]
    # 다른 시스템 필터는 비어 있다.
    assert await service.list_presets("user_1", system_code="mhm") == []


async def test_create_rejects_unsupported_auth(tmp_path):
    service = _service(tmp_path)
    bad_input = _hom_phone_input() | {"auth_method": "finance_certificate"}
    with pytest.raises(ValueError):
        await service.create_preset(
            "user_1",
            CreatePresetRequest(system_code="hom", name="잘못된 인증", input_data=bad_input),
        )


async def test_create_rejects_blank_name(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(ValueError):
        await service.create_preset(
            "user_1",
            CreatePresetRequest(system_code="hom", name="   ", input_data=_hom_phone_input()),
        )


async def test_presets_are_user_isolated(tmp_path):
    service = _service(tmp_path)
    mine = await service.create_preset(
        "user_1",
        CreatePresetRequest(system_code="hom", name="내 것", input_data=_hom_phone_input()),
    )
    await service.create_preset(
        "user_2",
        CreatePresetRequest(system_code="hom", name="남의 것", input_data=_hom_phone_input()),
    )

    mine_list = await service.list_presets("user_1")
    assert [item.preset_id for item in mine_list] == [mine.preset_id]

    # 다른 사용자의 프리셋은 조회/삭제에서 존재 자체가 숨겨진다(KeyError).
    with pytest.raises(KeyError):
        await service.get_owned(mine.preset_id, "user_2")
    with pytest.raises(KeyError):
        await service.delete_preset(mine.preset_id, "user_2")


async def test_update_and_delete_preset(tmp_path):
    service = _service(tmp_path)
    preset = await service.create_preset(
        "user_1",
        CreatePresetRequest(system_code="hom", name="원래 이름", input_data=_hom_phone_input()),
    )
    updated = await service.update_preset(
        preset.preset_id, "user_1", UpdatePresetRequest(name="새 이름")
    )
    assert updated.name == "새 이름"
    assert updated.input_data == preset.input_data

    await service.delete_preset(preset.preset_id, "user_1")
    assert await service.list_presets("user_1") == []
