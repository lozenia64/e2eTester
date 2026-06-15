from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from app.core.enums import RunStatus, SuiteStatus
from app.core.models import StartSuiteRequest, SuiteEvent, SuiteRun, SuiteStep, SystemDefinition
from app.orchestrator.run_service import RunService
from app.registry.loader import ModuleRegistry
from app.storage.suite_repository import InMemorySuiteRepository

_TERMINAL_RUN_STATUSES = {RunStatus.PASSED, RunStatus.FAILED, RunStatus.CANCELLED}


class SuiteService:
    def __init__(
        self,
        registry: ModuleRegistry,
        run_service: RunService,
        repository: InMemorySuiteRepository,
    ) -> None:
        self._registry = registry
        self._run_service = run_service
        self._repository = repository
        self._cancel_requested: set[str] = set()
        self._active_run_by_suite: dict[str, str] = {}

    async def get_suite(self, suite_id: str) -> SuiteRun:
        return await self._repository.get_suite(suite_id)

    async def list_suite_summaries(self, limit: int = 20) -> list[dict]:
        suites = await self._repository.list_suites()
        suites.sort(key=lambda suite: suite.requested_at, reverse=True)
        return [self._summarize_suite(suite) for suite in suites[:limit]]

    @staticmethod
    def _summarize_suite(suite: SuiteRun) -> dict:
        passed = sum(1 for step in suite.steps if step.status == SuiteStatus.PASSED)
        failed = sum(1 for step in suite.steps if step.status == SuiteStatus.FAILED)
        skipped = sum(1 for step in suite.steps if step.status == SuiteStatus.SKIPPED)
        selected_total = len(suite.steps) - skipped
        return {
            "suite_id": suite.suite_id,
            "status": suite.status,
            "requested_at": suite.requested_at.isoformat(),
            "started_at": suite.started_at.isoformat() if suite.started_at else None,
            "ended_at": suite.ended_at.isoformat() if suite.ended_at else None,
            "step_total": len(suite.steps),
            "step_selected_total": selected_total,
            "step_passed": passed,
            "step_failed": failed,
            "step_skipped": skipped,
            "current_step_index": suite.current_step_index,
            "awaiting_input_run_id": suite.awaiting_input_run_id,
        }

    async def subscribe(self, suite_id: str):
        return await self._repository.subscribe(suite_id)

    async def unsubscribe(self, suite_id: str, queue):
        await self._repository.unsubscribe(suite_id, queue)

    def _merge_input(self, browser_mode: str, system_code: str, systems_input: dict[str, dict[str, str]]) -> dict[str, str]:
        merged = {"browser_mode": browser_mode}
        merged.update(systems_input.get(system_code, {}))
        return merged

    @staticmethod
    def _resolve_selected_system_codes(
        systems: list[SystemDefinition],
        selected_system_codes: list[str] | None,
    ) -> list[str]:
        ordered_codes = [system.system_code for system in systems]
        if selected_system_codes is None:
            return ordered_codes

        selected_values: list[str] = []
        seen_codes: set[str] = set()
        for raw_code in selected_system_codes:
            code = raw_code.strip().lower()
            if not code or code in seen_codes:
                continue
            selected_values.append(code)
            seen_codes.add(code)

        if not selected_values:
            raise ValueError("최소 1개 시스템을 선택해야 합니다.")

        known_codes = set(ordered_codes)
        unknown_codes = [code for code in selected_values if code not in known_codes]
        if unknown_codes:
            joined = ", ".join(unknown_codes)
            raise ValueError(f"알 수 없는 시스템이 선택되었습니다: {joined}")

        selected_set = set(selected_values)
        return [code for code in ordered_codes if code in selected_set]

    def validate_suite_request(
        self,
        browser_mode: str,
        systems: dict[str, dict[str, str]],
        selected_system_codes: list[str] | None = None,
    ) -> tuple[str, dict[str, dict[str, str]], list[str]]:
        registered = self._registry.list_systems()
        if not registered:
            raise ValueError("등록된 시스템이 없습니다.")

        normalized_mode = (browser_mode or "headed").strip()
        if normalized_mode not in {"headed", "headless"}:
            raise ValueError("browser_mode는 headed 또는 headless 여야 합니다.")

        normalized_systems = {key: dict(value) for key, value in (systems or {}).items()}
        resolved_system_codes = self._resolve_selected_system_codes(registered, selected_system_codes)
        selected_set = set(resolved_system_codes)
        for system in registered:
            if system.system_code not in selected_set:
                continue
            merged_input = self._merge_input(normalized_mode, system.system_code, normalized_systems)
            self._run_service.validate_run_request(system.system_code, merged_input, selected_module_ids=None)
        return normalized_mode, normalized_systems, resolved_system_codes

    async def start_suite(self, request: StartSuiteRequest) -> SuiteRun:
        systems = self._registry.list_systems()
        if not systems:
            raise ValueError("등록된 시스템이 없습니다.")

        browser_mode, normalized_systems, resolved_system_codes = self.validate_suite_request(
            request.browser_mode,
            request.systems,
            request.selected_system_codes,
        )
        selected_set = set(resolved_system_codes)

        steps: list[SuiteStep] = []
        for index, system in enumerate(systems):
            is_selected = system.system_code in selected_set
            steps.append(
                SuiteStep(
                    system_code=system.system_code,
                    system_name=system.name,
                    order=index,
                    module_total=len(system.modules),
                    status=SuiteStatus.PENDING if is_selected else SuiteStatus.SKIPPED,
                )
            )

        suite_id = f"suite_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        suite = SuiteRun(
            suite_id=suite_id,
            status=SuiteStatus.PENDING,
            steps=steps,
            requested_at=datetime.now(UTC),
            browser_mode=browser_mode,
            selected_system_codes=resolved_system_codes,
        )
        await self._repository.create_suite(suite)
        await self._publish_event("suite_created", suite)
        asyncio.create_task(self._execute_suite(suite_id, normalized_systems))
        return suite

    async def cancel_suite(self, suite_id: str) -> SuiteRun:
        suite = await self._repository.get_suite(suite_id)
        if suite.status in {SuiteStatus.PASSED, SuiteStatus.FAILED, SuiteStatus.CANCELLED}:
            raise ValueError("이미 종료된 전체 점검은 취소할 수 없습니다.")
        self._cancel_requested.add(suite_id)
        active_run_id = self._active_run_by_suite.get(suite_id)
        if active_run_id:
            try:
                await self._run_service.cancel_run(active_run_id)
            except (KeyError, ValueError):
                pass
        return suite

    async def submit_otp(self, suite_id: str, otp_code: str) -> SuiteRun:
        suite = await self._repository.get_suite(suite_id)
        if suite.awaiting_input_run_id is None:
            raise KeyError(f"Suite is not waiting for OTP: {suite_id}")
        await self._run_service.submit_otp(suite.awaiting_input_run_id, otp_code)
        return await self._repository.get_suite(suite_id)

    async def _execute_suite(self, suite_id: str, systems_input: dict[str, dict[str, str]]) -> None:
        suite = await self._repository.get_suite(suite_id)
        suite.status = SuiteStatus.RUNNING
        suite.started_at = datetime.now(UTC)
        await self._repository.save_suite(suite)
        await self._publish_event("suite_started", suite)

        any_failed = False
        cancelled = False

        for index, step in enumerate(suite.steps):
            if suite_id in self._cancel_requested:
                cancelled = True
                await self._mark_remaining_cancelled(suite, index)
                break

            if step.status == SuiteStatus.SKIPPED:
                continue

            suite.current_step_index = index
            step.status = SuiteStatus.RUNNING
            await self._repository.save_suite(suite)
            await self._publish_event("suite_step_started", suite, {"step_index": index})

            merged_input = self._merge_input(suite.browser_mode, step.system_code, systems_input)
            try:
                run = await self._run_service.start_run(
                    step.system_code,
                    merged_input,
                    selected_module_ids=None,
                    triggered_by="suite",
                    suite_id=suite_id,
                )
            except (KeyError, ValueError) as exc:
                step.status = SuiteStatus.FAILED
                any_failed = True
                await self._repository.save_suite(suite)
                await self._publish_event(
                    "suite_step_finished",
                    suite,
                    {"step_index": index, "error": str(exc)},
                )
                continue

            step.run_id = run.run_id
            self._active_run_by_suite[suite_id] = run.run_id
            await self._repository.save_suite(suite)

            final_status = await self._wait_for_run_terminal(suite, run.run_id)

            if suite_id in self._cancel_requested or final_status == RunStatus.CANCELLED:
                cancelled = True
                step.status = SuiteStatus.CANCELLED
                await self._repository.save_suite(suite)
                await self._publish_event("suite_step_finished", suite, {"step_index": index})
                await self._mark_remaining_cancelled(suite, index + 1)
                break

            if final_status == RunStatus.PASSED:
                step.status = SuiteStatus.PASSED
            else:
                step.status = SuiteStatus.FAILED
                any_failed = True

            suite.awaiting_input_run_id = None
            suite.awaiting_input_prompt = None
            await self._repository.save_suite(suite)
            await self._publish_event("suite_step_finished", suite, {"step_index": index})

        self._active_run_by_suite.pop(suite_id, None)
        self._cancel_requested.discard(suite_id)

        if cancelled:
            final_suite_status = SuiteStatus.CANCELLED
        elif any_failed:
            final_suite_status = SuiteStatus.FAILED
        else:
            final_suite_status = SuiteStatus.PASSED

        suite.status = final_suite_status
        suite.ended_at = datetime.now(UTC)
        suite.awaiting_input_run_id = None
        suite.awaiting_input_prompt = None
        await self._repository.save_suite(suite)
        await self._publish_event("suite_finished", suite)
        if suite.status in {SuiteStatus.PASSED, SuiteStatus.FAILED}:
            await self._run_service.notify_suite_completion(suite.model_copy(deep=True))

    async def _wait_for_run_terminal(self, suite: SuiteRun, run_id: str) -> RunStatus:
        queue = await self._run_service.subscribe(run_id)
        try:
            while True:
                run = await self._run_service.get_run(run_id)
                if run.status in _TERMINAL_RUN_STATUSES:
                    return run.status

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue

                if event.event_type == "run_waiting_input":
                    run = await self._run_service.get_run(run_id)
                    suite.status = SuiteStatus.WAITING_INPUT
                    suite.awaiting_input_run_id = run_id
                    suite.awaiting_input_prompt = run.awaiting_input_prompt
                    await self._repository.save_suite(suite)
                    await self._publish_event("suite_waiting_input", suite, {"run_id": run_id})

                if event.event_type == "run_resumed":
                    suite.status = SuiteStatus.RUNNING
                    suite.awaiting_input_run_id = None
                    suite.awaiting_input_prompt = None
                    await self._repository.save_suite(suite)
                    await self._publish_event("suite_resumed", suite)

                if event.event_type == "run_finished":
                    run = await self._run_service.get_run(run_id)
                    return run.status
        finally:
            await self._run_service.unsubscribe(run_id, queue)

    async def _mark_remaining_cancelled(self, suite: SuiteRun, start_index: int) -> None:
        for step in suite.steps[start_index:]:
            if step.status in {
                SuiteStatus.PASSED,
                SuiteStatus.FAILED,
                SuiteStatus.CANCELLED,
                SuiteStatus.SKIPPED,
            }:
                continue
            step.status = SuiteStatus.CANCELLED
        await self._repository.save_suite(suite)

    async def _publish_event(self, event_type: str, suite: SuiteRun, extra: dict | None = None) -> None:
        payload = suite.model_dump(mode="json")
        if extra:
            payload.update(extra)
        await self._repository.publish(
            SuiteEvent(
                event_type=event_type,
                suite_id=suite.suite_id,
                suite_status=suite.status,
                payload=payload,
            )
        )
