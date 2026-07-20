from __future__ import annotations

from app.contexts.run.contracts.ports import RunLogStorePort, RunWriteRepositoryPort
from app.contexts.run.domain.aggregate import RunAggregate


class RunHydrator:
    """EventBus 발행용 Run 하이드레이터 — 로그 포함."""

    def __init__(
        self,
        write_repo: RunWriteRepositoryPort,
        log_store: RunLogStorePort | None = None,
    ) -> None:
        self._write_repo = write_repo
        self._log_store = log_store

    async def hydrate(self, aggregate_id: str) -> object:
        run = await self._write_repo.get_run(aggregate_id)
        if self._log_store is not None:
            logs_by_module = await self._log_store.get_all(aggregate_id)
            RunAggregate(run).hydrate_logs(logs_by_module)
        return run


class RunProjectionLoader:
    """프로젝션 핸들러용 Run 로더 — 로그 하이드레이션 없음."""

    def __init__(self, write_repo: RunWriteRepositoryPort) -> None:
        self._write_repo = write_repo

    async def hydrate(self, aggregate_id: str) -> object:
        return await self._write_repo.get_run(aggregate_id)
