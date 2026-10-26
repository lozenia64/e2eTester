// 지배 상태 진행 링. conic-gradient 각도만 계산한다 — SVG·차트 라이브러리 없음.
import { animateCountUp } from "../kpi-card/index";

const FULL_TURN_DEG = 360;
const COUNT_UP_MS = 1200;
// morph 가 노드를 보존하므로 노드당 한 번 = 첫 진입에서만 카운트업.
const countedUp = new WeakMap<HTMLElement, { target: string; cancel: () => void }>();

export function passRateToDegrees(passed: number, total: number): number {
  if (!Number.isFinite(passed) || !Number.isFinite(total) || total <= 0) return 0;
  const ratio = Math.min(Math.max(passed / total, 0), 1);
  return Math.round(ratio * FULL_TURN_DEG);
}

export function bindStatusHero(root: ParentNode = document): void {
  const rings = root.querySelectorAll<HTMLElement>(".status-hero__ring");
  rings.forEach((ring) => {
    const passed = Number(ring.dataset.passed ?? "0");
    const total = Number(ring.dataset.total ?? "0");
    ring.style.setProperty("--ring-deg", `${passRateToDegrees(passed, total)}deg`);
  });

  root.querySelectorAll<HTMLElement>("[data-count-up]").forEach((el) => {
    const target = el.dataset.countUp ?? "0";
    const previous = countedUp.get(el);
    if (previous) {
      if (previous.target !== target) {
        previous.cancel();
        el.textContent = target;
        previous.target = target;
      }
      return;
    }
    countedUp.set(el, { target, cancel: animateCountUp(el, Number(target), COUNT_UP_MS) });
  });
}
