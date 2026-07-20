from __future__ import annotations

from typing import Protocol


class SuiteFinishedPayloadLoader(Protocol):
    async def load_suite_finished_payload(self, suite_id: str) -> tuple[object, list[object]]: ...


class SuiteHydrator:
    """EventBus 발행용 SuiteFinished payload 하이드레이터."""

    def __init__(self, suite_service: SuiteFinishedPayloadLoader) -> None:
        self._suite_service = suite_service

    async def hydrate(self, aggregate_id: str) -> object:
        return await self._suite_service.load_suite_finished_payload(aggregate_id)
