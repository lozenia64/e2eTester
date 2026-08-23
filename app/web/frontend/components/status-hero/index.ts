// 지배 상태 진행 링. conic-gradient 각도만 계산한다 — SVG·차트 라이브러리 없음.

const FULL_TURN_DEG = 360;

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
}
