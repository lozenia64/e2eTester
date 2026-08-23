// KPI 카드 동작. 마크업은 macro.jinja 가 SSOT 이며, 여기서는 값 카운트업만 맡는다
// (dashboard.js 의 animateCountUp 을 컴포넌트로 이관).

const DEFAULT_DURATION_MS = 600;
const boundKpiTargets = new WeakMap<HTMLElement, string>();

export function animateCountUp(
  el: HTMLElement,
  target: number,
  durationMs: number = DEFAULT_DURATION_MS,
): void {
  const prefersReducedMotion =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (durationMs <= 0 || Number.isNaN(target) || prefersReducedMotion) {
    el.textContent = String(target);
    return;
  }
  const start = performance.now();
  const step = (now: number): void => {
    const progress = Math.min((now - start) / durationMs, 1);
    // ease-out cubic — 토큰 --ease-out 과 같은 감각
    const eased = 1 - (1 - progress) ** 3;
    el.textContent = String(Math.round(target * eased));
    if (progress < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

export function bindKpiCards(root: ParentNode = document): void {
  const cards = root.querySelectorAll<HTMLElement>(".kpi-card");
  cards.forEach((card) => {
    const valueEl = card.querySelector<HTMLElement>(".kpi-card__value");
    if (!valueEl) return;
    const raw = valueEl.dataset.target ?? "";
    if (raw === "") return;
    if (boundKpiTargets.get(card) === raw) return;
    boundKpiTargets.set(card, raw);
    const target = Number(raw);
    // 숫자가 아닌 값(예: "추정치 미설정")은 원문 그대로 표시한다(애니메이션은 생략).
    if (Number.isNaN(target)) {
      valueEl.textContent = raw;
      return;
    }
    animateCountUp(valueEl, target);
  });
}
