"""HealingService 통합 테스트 — 임시 SQLite/소스 파일로 기록→제안→승인 흐름을 검증한다."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.enums import ModuleStatus, RunStatus
from app.core.models import ModuleDefinition, Run, RunModule
from app.healing.models import HealingAction, HealingAttempt, PatchStatus
from app.orchestrator.healing_service import HealingService
from app.storage.sqlite_healing_stores import (
    SqliteHealingEventStore,
    SqliteHealingPatchStore,
    SqliteHealingPolicyReader,
    SqliteHealingPolicyStore,
)


class FakeRegistry:
    def list_systems(self):
        return []

    def get_system(self, system_code: str):
        raise KeyError(system_code)


def _service(tmp_path) -> HealingService:
    db = tmp_path / "healing.db"
    steps_dir = tmp_path / "app" / "systems" / "hrp" / "steps"
    steps_dir.mkdir(parents=True)
    (steps_dir / "login.py").write_text(
        'LOGIN_BUTTON_SELECTOR = "#btnRA"\n\n\ndef run(page):\n    page.locator("#btnRA").click()\n',
        encoding="utf-8",
    )
    return HealingService(
        event_store=SqliteHealingEventStore(db),
        policy_store=SqliteHealingPolicyStore(db),
        patch_store=SqliteHealingPatchStore(db),
        registry=FakeRegistry(),
        repo_root=tmp_path,
    )


def _run() -> Run:
    return Run(
        run_id="run-1",
        system_code="hrp",
        system_name="현장출동 홈페이지(PC)",
        status=RunStatus.RUNNING,
        requested_at=datetime.now(UTC),
        modules=[_module_run()],
    )


def _module_run() -> RunModule:
    return RunModule(
        module_id="login", name="로그인", group="인증", order=2, status=ModuleStatus.RUNNING
    )


def _definition() -> ModuleDefinition:
    return ModuleDefinition(
        module_id="login",
        system_code="hrp",
        name="로그인",
        description="",
        group="인증",
        order=2,
        workflow_step="login",
    )


def _attempt() -> HealingAttempt:
    return HealingAttempt(
        broken_selector="#btnRA",
        action=HealingAction.AUTO_HEALED,
        healed_selector="#btnRA2",
        confidence=0.88,
        retry_succeeded=True,
        duration_ms=900,
    )


@pytest.mark.asyncio
async def test_record_creates_event_and_patch_proposal(tmp_path):
    service = _service(tmp_path)
    await service.record_step_healing(_run(), _module_run(), _definition(), [_attempt()])

    events = await service.list_events()
    assert len(events["items"]) == 1
    assert events["items"][0]["action"] == "AUTO_HEALED"

    patches = await service.list_patches()
    assert patches["counts"]["proposed"] == 1
    patch = patches["items"][0]
    assert patch["file_path"].endswith("app/systems/hrp/steps/login.py")
    assert "-LOGIN_BUTTON_SELECTOR" in patch["diff"]

    # 같은 (시스템, 깨진→대체) 제안이 이미 열려 있으면 중복 생성하지 않는다.
    await service.record_step_healing(_run(), _module_run(), _definition(), [_attempt()])
    assert (await service.list_patches())["counts"]["proposed"] == 1


@pytest.mark.asyncio
async def test_approve_applies_replacement_to_source(tmp_path):
    service = _service(tmp_path)
    await service.record_step_healing(_run(), _module_run(), _definition(), [_attempt()])
    patch_id = (await service.list_patches())["items"][0]["patch_id"]

    approved = await service.approve_patch(patch_id, actor_name="관리자")

    assert approved.status is PatchStatus.APPROVED
    assert approved.applied is True
    source = (tmp_path / "app/systems/hrp/steps/login.py").read_text(encoding="utf-8")
    assert '"#btnRA2"' in source
    assert '"#btnRA"' not in source

    # 이미 처리된 패치는 재승인 불가(감사 이력 보호).
    with pytest.raises(ValueError):
        await service.approve_patch(patch_id, actor_name="관리자")


@pytest.mark.asyncio
async def test_reject_keeps_source_untouched(tmp_path):
    service = _service(tmp_path)
    await service.record_step_healing(_run(), _module_run(), _definition(), [_attempt()])
    patch_id = (await service.list_patches())["items"][0]["patch_id"]

    rejected = await service.reject_patch(patch_id, actor_name="관리자", note="role 기반으로 재작성 예정")

    assert rejected.status is PatchStatus.REJECTED
    assert rejected.note == "role 기반으로 재작성 예정"
    source = (tmp_path / "app/systems/hrp/steps/login.py").read_text(encoding="utf-8")
    assert '"#btnRA"' in source


def test_policy_reader_resolves_system_then_global(tmp_path):
    db = tmp_path / "healing.db"
    reader = SqliteHealingPolicyReader(db)
    # 행이 없으면 코드 기본값.
    assert reader.resolve("hrp").threshold == 0.75

    import asyncio

    from app.healing.models import HealingPolicy

    store = SqliteHealingPolicyStore(db)
    asyncio.run(store.upsert(HealingPolicy(system_code="*", confidence_threshold=0.9)))
    asyncio.run(
        store.upsert(
            HealingPolicy(system_code="hrp", auto_heal_enabled=False, confidence_threshold=0.6)
        )
    )
    reader._cache_at = 0.0  # TTL 캐시 무효화(테스트 전용)
    assert reader.resolve("hrp").enabled is False
    assert reader.resolve("hrp").threshold == 0.6
    assert reader.resolve("fp").threshold == 0.9
