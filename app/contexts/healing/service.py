"""자가 치유 센터 애플리케이션 서비스 — 얇은 I/O 인터프리터.

집계·스캔·패치 규칙은 순수 빌더(``app/healing/metrics.py``/``durability.py``/
``patch_builder.py``)가 담당하고, 이 서비스는 I/O 만 한다: 스토어 조회/영속, steps 소스
파일 읽기, 승인된 패치의 파일 적용. ``InsightsService``/``StatsService`` 와 같은 패턴.

``RunService`` 가 의존하는 ``HealingRecorderPort`` 를 구조적으로 만족한다
(``record_step_healing``) — 실행 어댑터가 보고한 치유 '사실'을 감사 이벤트로 영속하고,
성공/제안된 치유는 소스 반영용 승인 대기 패치로 변환한다.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.contexts.healing.durability import build_durability_map
from app.contexts.healing.metrics import build_healing_metrics
from app.contexts.healing.models import (
    GLOBAL_POLICY_CODE,
    HealingAction,
    HealingAttempt,
    HealingEvent,
    HealingPatch,
    HealingPolicy,
    PatchStatus,
)
from app.contexts.healing.patch_builder import apply_replacement, build_patch_drafts
from app.contexts.scheduling.scheduler import schedule_month_start_utc
from app.core.logging import get_logger
from app.core.run_models import Run, RunModule
from app.core.schedule_time import schedule_day_label
from app.core.system_models import ModuleDefinition

if TYPE_CHECKING:
    from app.contexts.healing.infrastructure.ports import (
        HealingEventStorePort,
        HealingPatchStorePort,
        HealingPolicyStorePort,
    )
    from app.registry.loader import ModuleRegistry

logger = get_logger(__name__)

# 셀렉터가 실제로 사는 소스 위치(내구성 스캔 + 패치 제안의 탐색 범위).
_SOURCE_GLOBS = (
    "app/automation/page_objects/*/*.py",
    "app/systems/access_common/*.py",
    "app/scenarios/*/*.py",
)

_HEALING_PATCHES_DIR = Path("artifacts/healing_patches")

_EVENT_LIST_LIMIT = 300


class HealingService:
    def __init__(
        self,
        event_store: HealingEventStorePort,
        policy_store: HealingPolicyStorePort,
        patch_store: HealingPatchStorePort,
        registry: ModuleRegistry,
        *,
        repo_root: str | Path = ".",
    ) -> None:
        self._event_store = event_store
        self._policy_store = policy_store
        self._patch_store = patch_store
        self._registry = registry
        self._repo_root = Path(repo_root).resolve()

    # ── 소스 읽기(I/O) ──────────────────────────────────────────────────────
    def _relative_source_key(self, path: Path) -> str:
        return path.resolve().relative_to(self._repo_root).as_posix()

    def _resolve_source_path(self, file_path: str) -> Path:
        if not file_path or Path(file_path).is_absolute():
            raise ValueError(f"허용되지 않는 파일 경로입니다: {file_path}")
        resolved = (self._repo_root / file_path).resolve()
        try:
            resolved.relative_to(self._repo_root)
        except ValueError:
            raise ValueError(f"허용되지 않는 파일 경로입니다: {file_path}") from None
        return resolved

    def _read_sources_sync(self) -> dict[str, str]:
        sources: dict[str, str] = {}
        for pattern in _SOURCE_GLOBS:
            for path in sorted(self._repo_root.glob(pattern)):
                try:
                    sources[self._relative_source_key(path)] = path.read_text(encoding="utf-8")
                except (OSError, ValueError):
                    continue
        return sources

    async def _read_sources(self) -> dict[str, str]:
        return await asyncio.to_thread(self._read_sources_sync)

    @staticmethod
    def _scoped(items: list, allowed: list[str] | None) -> list:
        if allowed is None:
            return items
        allowed_set = set(allowed)
        return [item for item in items if item.system_code in allowed_set]

    def _system_name(self, system_code: str) -> str:
        try:
            return self._registry.get_system(system_code).name
        except KeyError:
            return system_code

    # ── 치유 이벤트 기록(HealingRecorderPort) ───────────────────────────────
    async def record_step_healing(
        self,
        run: Run,
        module: RunModule,
        definition: ModuleDefinition,
        attempts: list[HealingAttempt],
    ) -> None:
        """실행 어댑터가 보고한 치유 시도를 감사 이벤트로 영속하고 패치를 제안한다."""
        for attempt in attempts:
            event = HealingEvent(
                event_id=uuid4().hex,
                run_id=run.run_id,
                module_id=module.module_id,
                system_code=run.system_code,
                module_name=module.name,
                workflow_step=definition.workflow_step,
                broken_selector=attempt.broken_selector,
                healed_selector=attempt.healed_selector,
                strategy=attempt.strategy,
                confidence=attempt.confidence,
                action=attempt.action,
                retry_succeeded=attempt.retry_succeeded,
                candidates_considered=attempt.candidates_considered,
                error_excerpt=attempt.error_excerpt,
                page_url=attempt.page_url,
                duration_ms=attempt.duration_ms,
                created_at=datetime.now(UTC),
            )
            await self._event_store.append(event)
            logger.info(
                "자가 치유 이벤트 기록",
                log_event="healing.event_recorded",
                run_id=run.run_id,
                module_id=module.module_id,
                action=str(event.action.value),
                confidence=event.confidence,
            )
            if event.healed_selector and event.action in (
                HealingAction.AUTO_HEALED,
                HealingAction.SUGGESTED,
            ):
                await self._propose_patches(event)

    async def _propose_patches(self, event: HealingEvent) -> None:
        """치유된 셀렉터의 소스 반영 diff 를 제안한다(같은 제안이 이미 열려 있으면 생략)."""
        existing = await self._patch_store.list()
        for patch in existing:
            if (
                patch.system_code == event.system_code
                and patch.broken_selector == event.broken_selector
                and patch.healed_selector == event.healed_selector
                and patch.status is PatchStatus.PROPOSED
            ):
                return
        sources = await self._read_sources()
        drafts = build_patch_drafts(
            sources,
            broken_selector=event.broken_selector,
            healed_selector=event.healed_selector or "",
        )
        for draft in drafts:
            await self._patch_store.add(
                HealingPatch(
                    patch_id=uuid4().hex,
                    event_id=event.event_id,
                    run_id=event.run_id,
                    system_code=event.system_code,
                    broken_selector=event.broken_selector,
                    healed_selector=event.healed_selector or "",
                    file_path=draft.file_path,
                    occurrences=draft.occurrences,
                    diff=draft.diff,
                    warnings=draft.warnings,
                    created_at=datetime.now(UTC),
                )
            )

    # ── 조회(치유 이벤트 / 지표 / 내구성) ───────────────────────────────────
    async def list_events(
        self,
        *,
        allowed_system_codes: list[str] | None = None,
        system_code: str | None = None,
        run_id: str | None = None,
        limit: int = _EVENT_LIST_LIMIT,
    ) -> dict[str, Any]:
        events = self._scoped(await self._event_store.list(limit=limit), allowed_system_codes)
        if system_code:
            events = [e for e in events if e.system_code == system_code]
        if run_id:
            events = [e for e in events if e.run_id == run_id]
        heal_counts: dict[tuple[str, str], int] = {}
        for event in events:
            key = (event.system_code, event.broken_selector)
            heal_counts[key] = heal_counts.get(key, 0) + 1
        items = []
        for event in events:
            body = event.model_dump(mode="json")
            body["system_name"] = self._system_name(event.system_code)
            body["heal_count"] = heal_counts[(event.system_code, event.broken_selector)]
            items.append(body)
        return {"items": items, "systems": self._systems_payload(allowed_system_codes)}

    async def metrics(self, *, allowed_system_codes: list[str] | None = None) -> dict[str, Any]:
        events = self._scoped(await self._event_store.list(), allowed_system_codes)
        patches = self._scoped(await self._patch_store.list(), allowed_system_codes)
        payload = build_healing_metrics(
            events,
            patches,
            now=datetime.now(UTC),
            day_label=schedule_day_label,
            month_start=schedule_month_start_utc(),
        )
        payload["by_system"] = {
            code: {**row, "system_name": self._system_name(code)}
            for code, row in payload["by_system"].items()
        }
        return payload

    async def durability(self, *, allowed_system_codes: list[str] | None = None) -> dict[str, Any]:
        sources = await self._read_sources()
        events = self._scoped(await self._event_store.list(), allowed_system_codes)
        return build_durability_map(sources, events)

    def _systems_payload(self, allowed: list[str] | None) -> list[dict[str, str]]:
        systems = self._registry.list_systems()
        if allowed is not None:
            allowed_set = set(allowed)
            systems = [s for s in systems if s.system_code in allowed_set]
        systems = sorted(systems, key=lambda s: (s.display_order, s.name))
        return [{"system_code": s.system_code, "system_name": s.name} for s in systems]

    # ── 정책 ────────────────────────────────────────────────────────────────
    async def get_policies(
        self, *, allowed_system_codes: list[str] | None = None
    ) -> dict[str, Any]:
        stored = {policy.system_code: policy for policy in await self._policy_store.list()}
        default = stored.get(GLOBAL_POLICY_CODE) or HealingPolicy(system_code=GLOBAL_POLICY_CODE)
        rows = [default.model_dump(mode="json") | {"system_name": "전역 기본값"}]
        for system in self._systems_payload(allowed_system_codes):
            code = system["system_code"]
            policy = stored.get(code) or HealingPolicy(
                system_code=code,
                auto_heal_enabled=default.auto_heal_enabled,
                confidence_threshold=default.confidence_threshold,
            )
            rows.append(
                policy.model_dump(mode="json")
                | {"system_name": system["system_name"], "inherited": code not in stored}
            )
        return {"policies": rows}

    async def put_policies(
        self,
        items: list[dict[str, Any]],
        *,
        actor_name: str | None = None,
        allowed_system_codes: list[str] | None = None,
        is_admin: bool = False,
    ) -> dict[str, Any]:
        """정책 upsert. 전역(``*``) 행은 관리자만, 시스템 행은 접근 범위 안에서만 바꾼다."""
        known = {s.system_code for s in self._registry.list_systems()}
        for item in items:
            code = str(item.get("system_code") or "").strip()
            if not code:
                raise ValueError("system_code 가 비어 있습니다.")
            if code == GLOBAL_POLICY_CODE:
                if not is_admin:
                    raise PermissionError("전역 기본 정책은 관리자만 변경할 수 있습니다.")
            elif code not in known:
                raise ValueError(f"알 수 없는 시스템: {code}")
            elif allowed_system_codes is not None and code not in allowed_system_codes:
                raise PermissionError(f"권한이 없는 시스템입니다: {code}")
            threshold = float(item.get("confidence_threshold", 0.75))
            if not 0.05 <= threshold <= 0.99:
                raise ValueError("confidence_threshold 는 0.05~0.99 사이여야 합니다.")
            await self._policy_store.upsert(
                HealingPolicy(
                    system_code=code,
                    auto_heal_enabled=bool(item.get("auto_heal_enabled", True)),
                    confidence_threshold=threshold,
                    updated_at=datetime.now(UTC),
                    updated_by=actor_name,
                )
            )
        return await self.get_policies(allowed_system_codes=allowed_system_codes)

    # ── 패치(승인 게이트) ────────────────────────────────────────────────────
    async def list_patches(
        self,
        *,
        allowed_system_codes: list[str] | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        patches = self._scoped(await self._patch_store.list(), allowed_system_codes)
        counts = {"proposed": 0, "approved": 0, "rejected": 0}
        for patch in patches:
            counts[patch.status.value.lower()] += 1
        if status:
            wanted = PatchStatus(status.upper())
            patches = [p for p in patches if p.status is wanted]
        items = [
            p.model_dump(mode="json") | {"system_name": self._system_name(p.system_code)}
            for p in patches
        ]
        return {"items": items, "counts": counts}

    async def _get_scoped_patch(
        self, patch_id: str, allowed_system_codes: list[str] | None
    ) -> HealingPatch:
        patch = await self._patch_store.get(patch_id)  # KeyError → 404
        if allowed_system_codes is not None and patch.system_code not in allowed_system_codes:
            raise KeyError(patch_id)  # 권한 밖은 존재를 노출하지 않는다
        return patch

    async def approve_patch(
        self,
        patch_id: str,
        *,
        actor_name: str | None = None,
        apply_to_source: bool = False,
        allowed_system_codes: list[str] | None = None,
    ) -> HealingPatch:
        """패치 승인 — 소스 직접 수정 대신 artifacts/healing_patches/ 에 .patch 파일을 남긴다."""
        patch = await self._get_scoped_patch(patch_id, allowed_system_codes)
        if patch.status is not PatchStatus.PROPOSED:
            raise ValueError("이미 처리된 패치입니다.")
        applied = await asyncio.to_thread(self._write_patch_artifact_sync, patch)
        patch.status = PatchStatus.APPROVED
        patch.applied = applied
        patch.decided_at = datetime.now(UTC)
        patch.decided_by = actor_name
        await self._patch_store.update(patch)
        logger.info(
            "치유 패치 승인",
            log_event="healing.patch_approved",
            patch_id=patch.patch_id,
            file_path=patch.file_path,
            applied=applied,
            actor=actor_name,
        )
        return patch

    def _write_patch_artifact_sync(self, patch: HealingPatch) -> bool:
        """승인된 패치 diff 를 artifacts/healing_patches/ 에 기록한다(소스 직접 수정 없음)."""
        out_dir = (self._repo_root / _HEALING_PATCHES_DIR).resolve()
        try:
            out_dir.relative_to(self._repo_root)
        except ValueError:
            raise ValueError("허용되지 않는 패치 출력 경로입니다.") from None
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{patch.patch_id}.patch"
        out_path.write_text(patch.diff, encoding="utf-8")
        return True

    def _apply_patch_sync(self, patch: HealingPatch) -> bool:
        """레거시 직접 적용(테스트·수동 복구용). approve_patch 는 더 이상 호출하지 않는다."""
        path = self._resolve_source_path(patch.file_path)
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"소스 파일을 읽을 수 없습니다: {patch.file_path}") from exc
        new_source, count = apply_replacement(source, patch.broken_selector, patch.healed_selector)
        if not count:
            raise ValueError(
                "소스가 제안 시점 이후 변경되어 대상 셀렉터를 찾지 못했습니다. "
                "패치를 거절하고 새 치유 이벤트를 기다리세요."
            )
        path.write_text(new_source, encoding="utf-8")
        return True

    async def reject_patch(
        self,
        patch_id: str,
        *,
        actor_name: str | None = None,
        note: str = "",
        allowed_system_codes: list[str] | None = None,
    ) -> HealingPatch:
        patch = await self._get_scoped_patch(patch_id, allowed_system_codes)
        if patch.status is not PatchStatus.PROPOSED:
            raise ValueError("이미 처리된 패치입니다.")
        patch.status = PatchStatus.REJECTED
        patch.decided_at = datetime.now(UTC)
        patch.decided_by = actor_name
        patch.note = note[:500]
        await self._patch_store.update(patch)
        return patch

    async def patch_diff(
        self, patch_id: str, *, allowed_system_codes: list[str] | None = None
    ) -> tuple[str, str]:
        """(파일명, diff 본문) — 승인 대신 패치 파일 다운로드를 원할 때."""
        patch = await self._get_scoped_patch(patch_id, allowed_system_codes)
        filename = f"healing-{patch.system_code}-{patch.patch_id[:8]}.patch"
        return filename, patch.diff
