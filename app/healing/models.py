from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# 전역 기본 정책의 system_code 키(모든 시스템 공통 기본값 행).
GLOBAL_POLICY_CODE = "*"
# 자동 적용 신뢰도 임계치 기본값 — 이 값 미만이면 자동 병합 없이 '승인 대기 제안'만 남긴다.
DEFAULT_CONFIDENCE_THRESHOLD = 0.75
# 같은 셀렉터가 이 횟수 이상 치유되면 '만성(chronic)'으로 승격한다(정비 필요 신호).
CHRONIC_HEAL_THRESHOLD = 3


class HealingAction(str, Enum):
    """치유 시도 1건의 결과 분류.

    - AUTO_HEALED   : 신뢰도 ≥ 임계치 → 런타임 한정 대체 셀렉터 적용 + 스텝 재시도.
    - SUGGESTED     : 후보는 찾았으나 신뢰도 < 임계치 → 자동 적용 없이 제안만 기록.
    - NO_CANDIDATE  : 대체 후보를 찾지 못함(원래 실패 유지) — 내구성 맵의 취약 신호로 활용.
    """

    AUTO_HEALED = "AUTO_HEALED"
    SUGGESTED = "SUGGESTED"
    NO_CANDIDATE = "NO_CANDIDATE"


class PatchStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass
class HealingAttempt:
    """실행 스레드 안에서 만들어지는 치유 시도 1건(직렬화 전 드래프트).

    실행 어댑터는 이 '사실'만 ``StepExecutionResult`` 에 실어 보고하고, 영속·패치 제안 같은
    부작용은 오케스트레이터(``HealingService``)가 이벤트로 변환해 수행한다 — OTP 일시정지의
    ``StepNeedsInput`` 과 같은 보고-사실/집행-정책 분리.
    """

    broken_selector: str
    action: HealingAction
    healed_selector: str | None = None
    confidence: float = 0.0
    strategy: str = "heuristic-dom-scan"
    candidates_considered: int = 0
    error_excerpt: str = ""
    page_url: str | None = None
    duration_ms: int = 0
    retry_succeeded: bool | None = None

    @property
    def auto_applied(self) -> bool:
        return self.action is HealingAction.AUTO_HEALED


class HealingEvent(BaseModel):
    """영속되는 치유 이벤트(감사 로그) 1건 — 무엇이 깨졌고 어떻게 복구했는지."""

    event_id: str
    run_id: str
    module_id: str
    system_code: str
    module_name: str = ""
    workflow_step: str | None = None
    broken_selector: str
    healed_selector: str | None = None
    strategy: str = "heuristic-dom-scan"
    confidence: float = 0.0
    action: HealingAction
    retry_succeeded: bool | None = None
    candidates_considered: int = 0
    error_excerpt: str = ""
    page_url: str | None = None
    duration_ms: int = 0
    created_at: datetime


class HealingPolicy(BaseModel):
    """시스템별 자동 복구 정책(auto-heal on/off + 신뢰도 임계치). ``*`` 는 전역 기본값."""

    system_code: str
    auto_heal_enabled: bool = True
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    updated_at: datetime | None = None
    updated_by: str | None = None


class HealingPatch(BaseModel):
    """치유 결과를 실제 steps 소스에 반영하기 위한 **승인 대기 패치**(사람 승인 게이트).

    런타임 복구는 일회성이므로, 하드코딩 셀렉터를 대체 셀렉터로 바꾸는 before/after diff 를
    제안한다. 승인 시 소스 파일에 적용(또는 diff 다운로드)하고, 거절/승인 이력이 감사
    기록으로 남는다. 자동 병합은 하지 않는다.
    """

    patch_id: str
    event_id: str
    run_id: str = ""
    system_code: str
    broken_selector: str
    healed_selector: str
    file_path: str
    occurrences: int = 1
    diff: str = ""
    warnings: list[str] = Field(default_factory=list)
    status: PatchStatus = PatchStatus.PROPOSED
    created_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    applied: bool = False
    note: str = ""


@dataclass(frozen=True)
class ResolvedHealingPolicy:
    """실행 스레드가 치유 직전에 조회하는 정책 스냅샷(시스템별 → 전역 → 기본값 순 해석)."""

    enabled: bool = True
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD


@dataclass(frozen=True)
class ScoredCandidate:
    """DOM 스캔 후보 1건의 스코어링 결과(순수 계산 산출물)."""

    selector: str
    confidence: float
    reason: str = ""
    summary: str = ""


@dataclass(frozen=True)
class SelectorHints:
    """깨진 셀렉터에서 추출한 매칭 힌트(후보 스코어링의 입력)."""

    raw: str
    element_id: str | None = None
    id_prefix: str | None = None
    name: str | None = None
    text: str | None = None
    tag: str | None = None
    classes: tuple[str, ...] = field(default_factory=tuple)
