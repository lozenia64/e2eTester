"""프리셋 참조 예약의 HTTP 계약과 인증정보 비노출."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_schedule_live_presets import live, save_preset
from test_schedule_suite_browser_mode import ADMIN

from app.api.dependencies import get_registry, get_schedule_repository, get_schedule_service
from app.api.routes_schedules import router
from app.contexts.identity.dependencies import get_current_user


async def test_http_references_editing_and_owner_isolation(live):
    await save_preset(live, manager_employee_id="1234567")
    await save_preset(live, pid="private", owner="other", secret="비공개")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: ADMIN.model_copy(
        update={"user_id": "owner"}
    )
    app.dependency_overrides[get_schedule_service] = lambda: live["scheduler"]
    app.dependency_overrides[get_schedule_repository] = lambda: live["schedule_repo"]
    app.dependency_overrides[get_registry] = lambda: live["registry"]
    with TestClient(app) as client:
        response = client.post(
            "/api/schedules/suites",
            json={
                "cron": "0 7 * * *",
                "preset_ids": {"fp": "p1"},
                "selected_system_codes": ["fp"],
            },
        )
        assert response.status_code == 200
        sid = response.json()["schedule_id"]
        detail = client.get(f"/api/schedules/{sid}").json()
        assert detail["preset_bindings"]["fp"]["status"] == "live"
        assert [p["preset_id"] for p in detail["preset_options"]] == ["p1"]
        assert "manager_employee_id" not in str(detail)
        assert "1234567" not in str(detail)
        bad = client.put(f"/api/schedules/{sid}", json={"preset_ids": {"fp": "private"}})
        assert bad.status_code == 400
        assert "비공개" not in bad.text
        await save_preset(live, pid="p2")
        updated = client.put(f"/api/schedules/{sid}", json={"preset_ids": {"fp": "p2"}})
        assert updated.status_code == 200
        assert updated.json()["preset_ids"] == {"fp": "p2"}
