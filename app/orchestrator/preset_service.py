from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.core.logging import get_logger
from app.core.preset_models import AuthPreset
from app.core.requests import CreatePresetRequest, UpdatePresetRequest

if TYPE_CHECKING:
    from app.orchestrator.run_service import RunService
    from app.storage.ports import PresetRepositoryPort

logger = get_logger(__name__)


class PresetService:
    """인증 프리셋(``AuthPreset``)의 생명주기를 관장하는 애플리케이션 서비스.

    프리셋은 사용자별로 격리되며, 저장 시 ``RunService.validate_run_request`` 로 입력값·모듈
    선택·인증 수단을 검증한다(저장하는 프리셋은 항상 실제로 실행 가능한 조합이어야 한다).
    소유권 강제는 이 서비스가 책임진다 — 조회/수정/삭제는 반드시 ``user_id`` 를 함께 받아
    다른 사용자의 프리셋에 접근하지 못하게 한다.
    """

    def __init__(
        self,
        repository: PresetRepositoryPort,
        run_service: RunService,
    ) -> None:
        self._repository = repository
        self._run_service = run_service

    async def list_presets(self, user_id: str, system_code: str | None = None) -> list[AuthPreset]:
        presets = await self._repository.list_by_user(user_id)
        if system_code is not None:
            presets = [preset for preset in presets if preset.system_code == system_code]
        return presets

    async def get_owned(self, preset_id: str, user_id: str) -> AuthPreset:
        preset = await self._repository.get(preset_id)
        if preset.user_id != user_id:
            # 소유자가 아니면 존재 자체를 숨긴다(열거 방지).
            raise KeyError(preset_id)
        return preset

    async def create_preset(self, user_id: str, request: CreatePresetRequest) -> AuthPreset:
        system = self._run_service.get_system(request.system_code)  # KeyError → 404
        name = request.name.strip()
        if not name:
            raise ValueError("프리셋 이름을 입력해야 합니다.")
        # 실제 실행 가능한 조합인지 검증하고 입력값을 정규화한다(Run 시작과 동일 규칙).
        sanitized_input, _resolved_modules = self._run_service.validate_run_request(
            request.system_code, request.input_data, request.selected_module_ids
        )
        now = datetime.now(UTC)
        preset = AuthPreset(
            preset_id=f"preset_{now.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}",
            user_id=user_id,
            system_code=system.system_code,
            system_name=system.name,
            name=name,
            auth_method=sanitized_input.get("auth_method", ""),
            input_data=sanitized_input,
            selected_module_ids=request.selected_module_ids,
            created_at=now,
            updated_at=now,
        )
        await self._repository.save(preset)
        logger.info(
            "인증 프리셋 생성",
            log_event="preset.created",
            preset_id=preset.preset_id,
            system_code=preset.system_code,
            user_id=user_id,
        )
        return preset

    async def update_preset(
        self, preset_id: str, user_id: str, request: UpdatePresetRequest
    ) -> AuthPreset:
        preset = await self.get_owned(preset_id, user_id)
        name = preset.name
        if request.name is not None:
            name = request.name.strip()
            if not name:
                raise ValueError("프리셋 이름을 입력해야 합니다.")
        input_data = preset.input_data
        selected_module_ids = preset.selected_module_ids
        auth_method = preset.auth_method
        if request.input_data is not None or request.selected_module_ids is not None:
            new_input = request.input_data if request.input_data is not None else preset.input_data
            new_modules = (
                request.selected_module_ids
                if request.selected_module_ids is not None
                else preset.selected_module_ids
            )
            sanitized_input, _resolved = self._run_service.validate_run_request(
                preset.system_code, new_input, new_modules
            )
            input_data = sanitized_input
            selected_module_ids = new_modules
            auth_method = sanitized_input.get("auth_method", "")
        updated = preset.model_copy(
            update={
                "name": name,
                "input_data": input_data,
                "selected_module_ids": selected_module_ids,
                "auth_method": auth_method,
                "updated_at": datetime.now(UTC),
            }
        )
        await self._repository.save(updated)
        logger.info(
            "인증 프리셋 수정",
            log_event="preset.updated",
            preset_id=preset_id,
            user_id=user_id,
        )
        return updated

    async def delete_preset(self, preset_id: str, user_id: str) -> None:
        # 소유권 확인 후 삭제(다른 사용자 프리셋 삭제 차단).
        await self.get_owned(preset_id, user_id)
        await self._repository.delete(preset_id)
        logger.info(
            "인증 프리셋 삭제",
            log_event="preset.deleted",
            preset_id=preset_id,
            user_id=user_id,
        )
