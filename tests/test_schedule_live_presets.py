"""예약은 실행 시 최신 프리셋을 읽고 실행 중 입력은 고정한다."""

from datetime import UTC, datetime, timedelta

import pytest
from test_schedule_suite_browser_mode import _build_stack

from app.contexts.preset.infrastructure.sqlite_preset_repository import SqlitePresetRepository
from app.contexts.scheduling.infrastructure.sqlite_schedule_repository import (
    SqliteScheduleRepository,
)
from app.contexts.scheduling.scheduler import SchedulerService
from app.core.preset_models import AuthPreset
from app.core.requests import (
    CreateScheduleRequest,
    CreateSuiteScheduleRequest,
    UpdateScheduleRequest,
)


@pytest.fixture
async def live(tmp_path):
    stack = await _build_stack(tmp_path)
    presets = SqlitePresetRepository(str(tmp_path / "presets.db"))
    scheduler = SchedulerService(
        stack["run_commands"],
        stack["suite_service"],
        stack["schedule_repo"],
        stack["scheduler"]._run_queries,
        preset_repository=presets,
    )
    stack.update(scheduler=scheduler, presets=presets)
    return stack


async def save_preset(live, pid="p1", owner="owner", code="fp", **inputs):
    preset = AuthPreset(
        preset_id=pid,
        user_id=owner,
        system_code=code,
        system_name="점검",
        name="연결 프리셋",
        input_data={"name": "테스트", "auth_method": "phone", **inputs},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await live["presets"].save(preset)
    return preset


async def test_single_uses_latest_preset_and_preserves_controls(live):
    await save_preset(live, manager_employee_id="1234567", browser_mode="headed")
    s = await live["scheduler"].create_schedule(
        "fp",
        CreateScheduleRequest(
            cron="0 7 * * *",
            preset_id="p1",
            browser_mode="headless",
            selected_module_ids=["fp.main.access"],
        ),
        user_id="owner",
    )
    await save_preset(live, manager_employee_id="7654321", extra="새 필드")
    await live["scheduler"].run_now(s.schedule_id, user_id="admin")
    first = live["run_commands"].start_run_calls[-1]["input_data"]
    assert first["manager_employee_id"] == "7654321"
    assert first["extra"] == "새 필드"
    assert first["browser_mode"] == "headless"
    await save_preset(live, manager_employee_id="9999999")
    assert first["manager_employee_id"] == "7654321"
    assert s.input_data == {}


@pytest.mark.parametrize("owner,code", [("other", "fp"), ("owner", "hom")])
async def test_binding_validates_owner_and_system(live, owner, code):
    await save_preset(live, owner=owner, code=code)
    with pytest.raises(ValueError, match="프리셋"):
        await live["scheduler"].create_schedule(
            "fp",
            CreateScheduleRequest(
                cron="0 7 * * *",
                preset_id="p1",
            ),
            user_id="owner",
        )


async def test_deleted_preset_never_falls_back_and_error_is_visible(live):
    await save_preset(live)
    s = await live["scheduler"].create_schedule(
        "fp",
        CreateScheduleRequest(
            cron="0 7 * * *",
            preset_id="p1",
        ),
        user_id="owner",
    )
    await live["presets"].delete("p1")
    with pytest.raises(ValueError, match="프리셋"):
        await live["scheduler"].run_now(s.schedule_id)
    assert not live["run_commands"].start_run_calls
    detail = await live["scheduler"].get_detail(s.schedule_id)
    assert detail["preparation_error"]
    assert detail["preset_bindings"]["fp"]["status"] == "missing"
    assert "input_data" not in detail
    await save_preset(live, pid="p2")
    await live["scheduler"].update_schedule(s.schedule_id, UpdateScheduleRequest(preset_id="p2"))
    assert (await live["scheduler"].get_detail(s.schedule_id))["preparation_error"] is None


async def test_suite_resolves_all_references_before_start(live):
    await save_preset(live)
    await save_preset(live, pid="p2", code="hom")
    s = await live["scheduler"].create_suite_schedule(
        CreateSuiteScheduleRequest(
            cron="0 7 * * *",
            preset_ids={"fp": "p1", "hom": "p2"},
            selected_system_codes=["fp", "hom"],
        ),
        user_id="owner",
    )
    await live["presets"].delete("p2")
    with pytest.raises(ValueError, match="프리셋"):
        await live["scheduler"].run_now(s.schedule_id)
    assert not live["run_commands"].start_run_calls
    assert s.last_suite_id is None


async def test_legacy_unique_subset_migrates_and_persists(live, tmp_path):
    s = await live["scheduler"].create_schedule(
        "fp",
        CreateScheduleRequest(
            cron="0 7 * * *",
            input_data={"name": "테스트", "browser_mode": "headless"},
        ),
        user_id="owner",
    )
    await save_preset(live, manager_employee_id="1234567")
    await live["scheduler"]._reconcile_due_schedules_on_start()
    assert s.preset_id == "p1"
    assert s.input_data == {}
    assert s.browser_mode == "headless"
    repo = SqliteScheduleRepository(str(tmp_path / "schedules.db"))
    await repo.save(s)
    restored = await repo.get(s.schedule_id)
    assert restored.preset_id == "p1"
    assert restored.input_data == {}
    await live["scheduler"].run_now(s.schedule_id)
    assert (
        live["run_commands"].start_run_calls[-1]["input_data"]["manager_employee_id"] == "1234567"
    )


@pytest.mark.parametrize("kind", ["ambiguous", "mismatch", "other_owner"])
async def test_legacy_does_not_guess(live, kind):
    s = await live["scheduler"].create_schedule(
        "fp",
        CreateScheduleRequest(
            cron="0 7 * * *",
            input_data={"name": "테스트"},
        ),
        user_id="owner",
    )
    await save_preset(
        live,
        owner="other" if kind == "other_owner" else "owner",
        name="다른 사람" if kind == "mismatch" else "테스트",
    )
    if kind == "ambiguous":
        await save_preset(live, pid="p2")
    await live["scheduler"]._reconcile_due_schedules_on_start()
    assert s.preset_id is None
    if kind != "other_owner":
        updated = await live["scheduler"].update_schedule(
            s.schedule_id, UpdateScheduleRequest(preset_id="p1")
        )
        assert updated.preset_id == "p1"


async def test_cron_failure_does_not_block_other_schedules(live):
    await save_preset(live)
    bad = await live["scheduler"].create_schedule(
        "fp",
        CreateScheduleRequest(
            cron="0 7 * * *",
            preset_id="p1",
        ),
        user_id="owner",
    )
    good = await live["scheduler"].create_schedule(
        "fp",
        CreateScheduleRequest(
            cron="0 7 * * *",
            input_data={"name": "별도"},
        ),
        user_id="owner",
    )
    await live["presets"].delete("p1")
    bad.next_run_at = good.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
    await live["scheduler"]._tick()
    assert bad.preparation_error
    assert bad.next_run_at > datetime.now(UTC)
    assert len(live["run_commands"].start_run_calls) == 1


async def test_mixed_input_and_reference_rejected(live):
    await save_preset(live)
    with pytest.raises(ValueError, match="프리셋"):
        await live["scheduler"].create_schedule(
            "fp",
            CreateScheduleRequest(
                cron="0 7 * * *",
                preset_id="p1",
                input_data={"name": "수정값"},
            ),
            user_id="owner",
        )


async def test_suite_latest_inputs_are_fixed_at_start(live, monkeypatch):
    from types import SimpleNamespace

    from app.core.enums import SuiteStatus

    await save_preset(live, manager_employee_id="1234567")
    s = await live["scheduler"].create_suite_schedule(
        CreateSuiteScheduleRequest(
            cron="0 7 * * *",
            browser_mode="headless",
            preset_ids={"fp": "p1"},
            selected_system_codes=["fp"],
        ),
        user_id="owner",
    )
    await save_preset(live, manager_employee_id="7654321", browser_mode="headed")
    captured = []

    async def start(request, **kwargs):
        captured.append(request)
        return SimpleNamespace(suite_id="suite_capture", status=SuiteStatus.PASSED)

    monkeypatch.setattr(live["suite_service"], "start_suite", start)
    await live["scheduler"].run_now(s.schedule_id)
    await save_preset(live, manager_employee_id="9999999")
    assert captured[0].systems["fp"]["manager_employee_id"] == "7654321"
    assert "browser_mode" not in captured[0].systems["fp"]
    assert captured[0].browser_mode == "headless"
    assert s.suite_systems == {}


async def test_mobile_uses_latest_reference_and_does_not_rebind_active_run(live):
    from app.core.enums import RunStatus

    await save_preset(live, manager_employee_id="1234567")
    s = await live["scheduler"].create_schedule(
        "fp",
        CreateScheduleRequest(
            cron="0 7 * * *",
            preset_id="p1",
        ),
        user_id="owner",
    )
    await save_preset(live, manager_employee_id="7654321")
    result = await live["scheduler"].trigger_now(s.schedule_id)
    assert result["already_running"] is False
    first = live["run_commands"].start_run_calls[0]["input_data"]
    await live["presets"].delete("p1")
    result = await live["scheduler"].trigger_now(s.schedule_id)
    assert result["already_running"] is True
    assert first["manager_employee_id"] == "7654321"
    assert len(live["run_commands"].start_run_calls) == 1
    live["run_commands"]._runs[s.last_run_id].status = RunStatus.PASSED
    with pytest.raises(ValueError, match="프리셋"):
        await live["scheduler"].trigger_now(s.schedule_id)
    assert (await live["scheduler"].trigger_status(s.schedule_id))["preparation_error"]


async def test_duplicate_preserves_owner_binding_and_rejects_other_owner(live):
    await save_preset(live)
    s = await live["scheduler"].create_schedule(
        "fp",
        CreateScheduleRequest(
            cron="0 7 * * *",
            preset_id="p1",
        ),
        user_id="owner",
    )
    duplicate = await live["scheduler"].duplicate_schedule(s.schedule_id, user_id="owner")
    assert duplicate.preset_id == "p1"
    assert duplicate.enabled is False
    with pytest.raises(ValueError, match="다른 사용자"):
        await live["scheduler"].duplicate_schedule(s.schedule_id, user_id="admin")


async def test_invalid_rebinding_is_atomic(live):
    await save_preset(live)
    s = await live["scheduler"].create_schedule(
        "fp",
        CreateScheduleRequest(
            cron="0 7 * * *",
            preset_id="p1",
        ),
        user_id="owner",
    )
    await save_preset(live, pid="other", owner="other")
    with pytest.raises(ValueError):
        await live["scheduler"].update_schedule(
            s.schedule_id, UpdateScheduleRequest(name="변경", preset_id="other")
        )
    restored = await live["schedule_repo"].get(s.schedule_id)
    assert restored.preset_id == "p1"
    assert restored.name == ""


async def test_invalid_browser_mode_rejected(live):
    await save_preset(live)
    with pytest.raises(ValueError, match="브라우저"):
        await live["scheduler"].create_schedule(
            "fp",
            CreateScheduleRequest(
                cron="0 7 * * *",
                preset_id="p1",
                browser_mode="invalid",
            ),
            user_id="owner",
        )


async def test_legacy_browser_mode_update_controls_actual_execution(live):
    s = await live["scheduler"].create_schedule(
        "fp",
        CreateScheduleRequest(
            cron="0 7 * * *",
            input_data={"name": "테스트", "browser_mode": "headed"},
        ),
        user_id="owner",
    )
    await live["scheduler"].update_schedule(
        s.schedule_id, UpdateScheduleRequest(input_data={"browser_mode": "headless"})
    )
    await live["scheduler"].run_now(s.schedule_id)
    assert live["run_commands"].start_run_calls[-1]["input_data"]["browser_mode"] == "headless"


async def test_same_browser_mode_update_records_no_change(live):
    s = await live["scheduler"].create_schedule(
        "fp",
        CreateScheduleRequest(
            cron="0 7 * * *", input_data={"name": "테스트"}, browser_mode="headless"
        ),
        user_id="owner",
    )
    before = len(s.change_log)
    after = await live["scheduler"].update_schedule(
        s.schedule_id, UpdateScheduleRequest(browser_mode="headless")
    )
    assert len(after.change_log) == before


async def test_suite_normalizes_selection_before_resolving_inputs(live):
    s = await live["scheduler"].create_suite_schedule(
        CreateSuiteScheduleRequest(
            cron="0 7 * * *",
            systems={"fp": {"name": "테스트"}},
            selected_system_codes=[" FP "],
        ),
        user_id="owner",
    )
    assert s.selected_system_codes == ["fp"]
    assert s.suite_systems["fp"]["name"] == "테스트"
    await save_preset(live)
    s = await live["scheduler"].create_suite_schedule(
        CreateSuiteScheduleRequest(
            cron="0 7 * * *",
            preset_ids={"fp": "p1"},
            selected_system_codes=["fp"],
        ),
        user_id="owner",
    )
    updated = await live["scheduler"].update_schedule(
        s.schedule_id, UpdateScheduleRequest(selected_system_codes=[" FP "])
    )
    assert updated.preset_ids == {"fp": "p1"}
