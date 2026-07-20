"""Healing BC persistence ports."""

from __future__ import annotations

from typing import Protocol

from app.contexts.healing.models import HealingEvent, HealingPatch, HealingPolicy


class HealingEventStorePort(Protocol):
    """자가 치유 이벤트(감사 로그)의 저장 경계 — append-only.

    무인 실행 중 셀렉터가 깨졌을 때의 치유 시도 1건(무엇이 깨졌나/어떻게 복구했나/신뢰도)을
    기록한다. 이벤트는 수정되지 않고 쌓이기만 하며, 만성(chronic) 판정·MTTR·복구율 집계의
    입력이 된다.
    """

    async def append(self, event: HealingEvent) -> HealingEvent: ...
    async def list(self, limit: int | None = None) -> list[HealingEvent]: ...


class HealingPolicyStorePort(Protocol):
    """자동 복구 정책(시스템별 auto-heal on/off + 신뢰도 임계치)의 저장 경계.

    ``system_code="*"`` 행이 전역 기본값이다. 실행 스레드는 이 포트가 아니라 같은 테이블을
    읽는 동기 리더(``SqliteHealingPolicyReader``)로 정책 스냅샷을 조회한다(스레드 경계 분리).
    """

    async def list(self) -> list[HealingPolicy]: ...
    async def upsert(self, policy: HealingPolicy) -> HealingPolicy: ...


class HealingPatchStorePort(Protocol):
    """셀렉터 오토픽스 패치(승인 대기 diff 제안)의 저장 경계.

    치유된 셀렉터를 실제 steps 소스에 반영하는 제안(PROPOSED)과 그 승인/거절 감사 이력
    (누가 언제 어떤 셀렉터를 바꿨나)을 보관한다. 소스 파일 적용 자체는 ``HealingService``
    가 승인 시점에 수행한다.
    """

    async def add(self, patch: HealingPatch) -> HealingPatch: ...
    async def get(self, patch_id: str) -> HealingPatch: ...
    async def list(self) -> list[HealingPatch]: ...
    async def update(self, patch: HealingPatch) -> HealingPatch: ...
