"""예약 인증 프리셋 참조·레거시 전환. 인증값은 설명 응답에 포함하지 않는다."""

from app.contexts.preset.infrastructure.ports import PresetRepositoryPort
from app.core.preset_models import AuthPreset
from app.core.schedule_models import Schedule

# 예전 단일 폼의 FormData에 들어 있던 실행 제어값은 인증정보가 아니다.
CONTROL_KEYS = {"browser_mode", "cron", "name_schedule", "selected_module_ids"}


def auth_input(values: dict[str, str]) -> dict[str, str]:
    return {key: value.strip() for key, value in values.items() if key not in CONTROL_KEYS}


def normalize_codes(codes: list[str]) -> list[str]:
    return list(dict.fromkeys(code.strip().lower() for code in codes if code.strip()))


class SchedulePresetBindings:
    def __init__(self, repository: PresetRepositoryPort | None) -> None:
        self._repository = repository

    @staticmethod
    def codes(schedule: Schedule) -> list[str]:
        if schedule.schedule_kind != "suite":
            return [schedule.system_code]
        return normalize_codes(
            schedule.selected_system_codes
            if schedule.selected_system_codes is not None
            else list(schedule.suite_systems or {})
        )

    @staticmethod
    def bindings(schedule: Schedule) -> dict[str, str]:
        if schedule.schedule_kind == "suite":
            return dict(schedule.preset_ids)
        return {schedule.system_code: schedule.preset_id} if schedule.preset_id else {}

    async def _get(self, schedule: Schedule, code: str, preset_id: str) -> AuthPreset:
        message = f"{code.upper()} 프리셋을 사용할 수 없습니다. 예약 편집에서 프리셋을 다시 연결해 주세요."
        if self._repository is None or not schedule.created_by_user_id:
            raise ValueError(message)
        try:
            preset = await self._repository.get(preset_id)
        except KeyError:
            raise ValueError(message) from None
        if preset.user_id != schedule.created_by_user_id or preset.system_code != code:
            raise ValueError(message)
        return preset

    async def resolve(self, schedule: Schedule) -> dict[str, dict[str, str]]:
        """모든 선택 시스템 참조를 먼저 검증하고 독립된 실행 입력을 반환한다."""
        codes = self.codes(schedule)
        bindings = self.bindings(schedule)
        if set(bindings) - set(codes):
            raise ValueError("선택하지 않은 시스템의 프리셋은 연결할 수 없습니다.")
        result = {}
        for code in codes:
            if code in bindings:
                preset = await self._get(schedule, code, bindings[code])
                result[code] = auth_input(preset.input_data)
            elif schedule.schedule_kind == "suite":
                result[code] = auth_input((schedule.suite_systems or {}).get(code, {}))
            else:
                result[code] = auth_input(schedule.input_data)
        return result

    async def migrate(self, schedule: Schedule) -> bool:
        if self._repository is None or not schedule.created_by_user_id:
            return False
        presets = await self._repository.list_by_user(schedule.created_by_user_id)
        bindings = self.bindings(schedule)
        changed = False
        for code in self.codes(schedule):
            if code in bindings:
                continue
            stored = (
                (schedule.suite_systems or {}).get(code, {})
                if schedule.schedule_kind == "suite"
                else schedule.input_data
            )
            expected = {k: v for k, v in auth_input(stored).items() if v}
            if not expected:
                continue
            candidates = [
                p
                for p in presets
                if p.system_code == code
                and all(auth_input(p.input_data).get(k) == v for k, v in expected.items())
            ]
            if len(candidates) != 1:
                continue
            if schedule.schedule_kind == "suite":
                schedule.preset_ids[code] = candidates[0].preset_id
                schedule.suite_systems = {
                    k: dict(v) for k, v in (schedule.suite_systems or {}).items()
                }
                schedule.suite_systems.pop(code, None)
            else:
                schedule.preset_id = candidates[0].preset_id
                schedule.browser_mode = schedule.browser_mode or stored.get("browser_mode")
                schedule.input_data = {}
            schedule.record_change(
                "preset_linked", f"{code.upper()} 예약을 최신 프리셋 참조로 전환"
            )
            changed = True
        return changed

    async def describe(self, schedule: Schedule) -> dict:
        owned = (
            await self._repository.list_by_user(schedule.created_by_user_id)
            if self._repository and schedule.created_by_user_id
            else []
        )
        options = [
            {"preset_id": p.preset_id, "system_code": p.system_code, "name": p.name} for p in owned
        ]
        bindings = self.bindings(schedule)
        descriptions = {}
        for code in self.codes(schedule):
            pid = bindings.get(code)
            found = next((p for p in owned if p.preset_id == pid and p.system_code == code), None)
            descriptions[code] = {
                "preset_id": pid,
                "name": found.name if found else None,
                "status": "live" if found else "missing" if pid else "legacy",
            }
        return {"preset_bindings": descriptions, "preset_options": options}
