from __future__ import annotations

from typing import Protocol


class AggregateHydratorPort(Protocol):
    """EventBus 발행용 payload를 애그리게잇 id로부터 만들어내는 포트.

    반환 타입은 애그리게잇마다 다르다(Run 이벤트는 Run 엔티티, SuiteFinished는
    (SuiteRun, list[Run]) 튜플) — 호출부가 이미 event_type별로 알고 있는 bus 이벤트
    팩토리에 그대로 넘기므로 여기서 통일할 필요가 없다.
    """

    async def hydrate(self, aggregate_id: str) -> object: ...
