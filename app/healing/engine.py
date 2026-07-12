"""자가 치유 엔진 — 스텝 실패 시 라이브 DOM 을 스캔해 대체 셀렉터를 찾는 실행측 I/O.

실행 스레드(게이트웨이 세션의 단일 스레드 풀) 안에서 **동기**로 호출된다. 순수 계산
(파싱·스코어링)은 ``selector_healer`` 에 위임하고, 이 모듈은 브라우저 I/O(DOM 스캔·후보
검증)와 정책 게이팅만 담당한다.

폐루프(detect → diagnose → substitute → verify → record):
  1. detect   : 스텝 예외 메시지에서 깨진 셀렉터를 추출
  2. diagnose : 라이브 DOM 스캔(요소 지문 수집) 후 후보 스코어링(신뢰도)
  3. substitute: 정책(auto-heal on/off + 신뢰도 임계치)이 허가하면 런타임 오버라이드 등록
  4. verify   : 엔진 골격이 스텝을 1회 재시도(결과는 attempt.retry_succeeded 에 기록)
  5. record   : 모든 시도를 HealingAttempt 로 보고(오케스트레이터가 이벤트로 영속)
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Protocol

from app.core.system_models import ModuleDefinition
from app.healing.models import HealingAction, HealingAttempt, ResolvedHealingPolicy
from app.healing.selector_healer import extract_hints, parse_broken_selector, score_candidates

# 라이브 DOM 요소 지문 수집 스크립트(상호작용 가능/식별자 보유 요소 위주, 상한 400개).
_DOM_SCAN_JS = """
() => {
  const els = document.querySelectorAll(
    "a,button,input,select,textarea,[role],[id],[onclick],label"
  );
  const out = [];
  for (const el of els) {
    if (out.length >= 400) break;
    const r = el.getBoundingClientRect();
    out.push({
      tag: el.tagName.toLowerCase(),
      id: el.id || "",
      name: el.getAttribute("name") || "",
      role: el.getAttribute("role") || "",
      aria: el.getAttribute("aria-label") || "",
      cls: typeof el.className === "string" ? el.className : "",
      text: ((el.innerText || el.value || "") + "").trim().slice(0, 60),
      type: el.getAttribute("type") || "",
      visible: !!(r.width && r.height),
    });
  }
  return out;
}
"""

# 검증까지 통과해야 하는 상위 후보 수(치유 예산 — 스텝 타임아웃을 다시 태우지 않는다).
_VERIFY_TOP_N = 3


class HealingPolicySource(Protocol):
    """실행 스레드에서 동기 조회 가능한 정책 스냅샷 공급자(구현: SQLite 리더/테스트 페이크)."""

    def resolve(self, system_code: str) -> ResolvedHealingPolicy: ...


class SelfHealingEngine:
    strategy = "heuristic-dom-scan"

    def __init__(self, policy_source: HealingPolicySource) -> None:
        self._policy_source = policy_source

    def try_heal(
        self,
        page: Any,
        module: ModuleDefinition,
        error: Exception,
        overrides: dict[str, str],
        log: Callable[[str], None],
    ) -> HealingAttempt | None:
        """스텝 예외 1건에 대해 치유를 시도한다. 치유 대상이 아니면 None."""
        started = time.monotonic()
        policy = self._resolve_policy(module.system_code)
        broken = parse_broken_selector(str(error))
        if broken is None:
            return None  # 셀렉터 실패가 아님(URL 대기·role 조회 등) → 치유 범위 밖
        if broken in overrides:
            return None  # 이미 치유한 셀렉터가 또 깨짐 → 재치유 루프 방지
        if not policy.enabled:
            log(f"[heal] 셀렉터 실패 감지({broken}) — 정책상 자가 치유 비활성이라 건너뜁니다.")
            return None

        log(f"[heal] 셀렉터 실패 감지: {broken} — 대체 셀렉터 탐색을 시작합니다.")
        candidates = self._scan_dom(page, log)
        hints = extract_hints(broken)
        scored = score_candidates(hints, candidates)
        best = self._verify_candidates(page, scored)

        attempt = HealingAttempt(
            broken_selector=broken,
            action=HealingAction.NO_CANDIDATE,
            strategy=self.strategy,
            candidates_considered=len(scored),
            error_excerpt=str(error)[:300],
            page_url=self._safe_url(page),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        if best is None:
            log("[heal] 대체 셀렉터 후보를 찾지 못했습니다 — 원래 실패를 유지합니다.")
            return attempt

        attempt.healed_selector = best.selector
        attempt.confidence = best.confidence
        if best.confidence >= policy.threshold:
            overrides[broken] = best.selector
            attempt.action = HealingAction.AUTO_HEALED
            log(
                f"[heal] 대체 셀렉터 적용: {best.selector} "
                f"(신뢰도 {best.confidence:.2f} ≥ 임계 {policy.threshold:.2f} · {best.reason})"
            )
        else:
            attempt.action = HealingAction.SUGGESTED
            log(
                f"[heal] 후보 {best.selector} 의 신뢰도 {best.confidence:.2f} 가 "
                f"임계 {policy.threshold:.2f} 미만 — 자동 적용 없이 승인 대기 제안만 남깁니다."
            )
        attempt.duration_ms = int((time.monotonic() - started) * 1000)
        return attempt

    # --- 내부 I/O 헬퍼 ------------------------------------------------------

    def _resolve_policy(self, system_code: str) -> ResolvedHealingPolicy:
        try:
            return self._policy_source.resolve(system_code)
        except Exception:
            return ResolvedHealingPolicy()

    def _scan_dom(self, page: Any, log: Callable[[str], None]) -> list[dict]:
        try:
            result = page.evaluate(_DOM_SCAN_JS)
            return result if isinstance(result, list) else []
        except Exception as exc:
            log(f"[heal] DOM 스캔 실패(치유 중단): {exc}")
            return []

    def _verify_candidates(self, page: Any, scored: list) -> Any:
        """상위 후보를 라이브 페이지에서 검증한다(존재 여부 + 유일성 보정)."""
        for candidate in scored[:_VERIFY_TOP_N]:
            try:
                count = page.locator(candidate.selector).count()
            except Exception:
                continue
            if count == 1:
                return candidate
            if count > 1:
                return replace(
                    candidate,
                    selector=f"{candidate.selector} >> nth=0",
                    confidence=round(candidate.confidence * 0.85, 3),
                    reason=f"{candidate.reason} (다중 매치 → 첫 요소 고정)",
                )
        return None

    @staticmethod
    def _safe_url(page: Any) -> str | None:
        try:
            return str(page.url)
        except Exception:
            return None
