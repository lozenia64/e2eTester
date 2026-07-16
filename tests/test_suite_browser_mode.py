"""Suite browser_mode 병합 — 프리셋/레거시 per-system 값이 Suite 선택을 덮지 않는지 검증."""

from __future__ import annotations

from app.contexts.suite.application.service import SuiteService


def _service() -> SuiteService:
    return SuiteService.__new__(SuiteService)


def test_merge_input_suite_browser_mode_wins_over_preset() -> None:
    service = _service()
    merged = service._merge_input(
        "headless",
        "hom",
        {
            "hom": {
                "browser_mode": "headed",
                "auth_method": "phone",
                "name": "홍길동",
            }
        },
    )
    assert merged["browser_mode"] == "headless"
    assert merged["auth_method"] == "phone"
    assert merged["name"] == "홍길동"


def test_merge_input_preserves_headed_when_suite_requests_headed() -> None:
    service = _service()
    merged = service._merge_input(
        "headed",
        "mhm",
        {"mhm": {"browser_mode": "headless", "auth_method": "kakao"}},
    )
    assert merged["browser_mode"] == "headed"
    assert merged["auth_method"] == "kakao"


def test_normalize_systems_input_strips_browser_mode() -> None:
    service = _service()
    normalized = service._normalize_systems_input(
        {
            "hom": {"browser_mode": "headed", "name": "테스트"},
            "fp": {"browser_mode": "headless", "user_id": "u1"},
        }
    )
    assert "browser_mode" not in normalized["hom"]
    assert "browser_mode" not in normalized["fp"]
    assert normalized["hom"]["name"] == "테스트"
    assert normalized["fp"]["user_id"] == "u1"


def test_validate_suite_request_strips_browser_mode_from_normalized_systems() -> None:
    from app.contexts.run.application.planner import RunPlanner
    from app.registry.loader import ModuleRegistry

    class _FakeRunCommands:
        def __init__(self, registry: ModuleRegistry) -> None:
            self._registry = registry
            self._planner = RunPlanner()

        def validate_run_request(self, system_code, input_data=None, selected_module_ids=None):
            system = self._registry.get_system(system_code)
            return self._planner.prepare(system, input_data, selected_module_ids)

    registry = ModuleRegistry()
    service = _service()
    service._registry = registry
    service._run_commands = _FakeRunCommands(registry)

    _mode, normalized, _codes = service.validate_suite_request(
        "headless",
        {"hom": _hom_phone_input_for_test(browser_mode="headed")},
        selected_system_codes=["hom"],
    )

    assert _mode == "headless"
    assert "browser_mode" not in normalized["hom"]


def _hom_phone_input_for_test(*, browser_mode: str = "headed") -> dict[str, str]:
    return {
        "browser_mode": browser_mode,
        "auth_method": "phone",
        "name": "홍길동",
        "birthdate": "19900101",
        "gender": "male",
        "residency": "domestic",
        "carrier": "skt",
        "phone_number": "01012345678",
    }
