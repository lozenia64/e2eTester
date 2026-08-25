// 좌측 목록의 오늘 상태 배지이며 새 엔드포인트 없이 대시보드 API를 재사용한다.
// tone·label은 서버가 summary_badge로 파생해 내려주므로 여기서 counts를 해석하지 않는다.
// 호출 실패는 배지 없음으로만 나타나 실행 기능은 살아야 한다.
// 설계 §4.5·D6 및 FG-006의 매핑 복제 방지를 따른다.
import { renderStatusBadge } from "../components/status-badge/index";

type SystemBadge = {
  system_code: string;
  summary_badge: { label: string; tone: string };
};

export function applySystemBadges(root: ParentNode, systems: SystemBadge[]): void {
  const byCode = new Map(systems.map((system) => [system.system_code, system]));
  for (const slot of root.querySelectorAll<HTMLElement>("[data-exec-badge]")) {
    const system = byCode.get(slot.dataset.execBadge ?? "");
    slot.innerHTML = "";
    if (!system) continue;
    const { tone, label } = system.summary_badge;
    slot.append(renderStatusBadge(tone, { label, size: "sm" }));
  }
}

export async function loadSystemBadges(root: ParentNode = document): Promise<void> {
  try {
    const response = await fetch("/api/dashboard/daily", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return;
    const payload = (await response.json()) as { systems?: SystemBadge[] };
    applySystemBadges(root, payload.systems ?? []);
  } catch {
    // 배지는 부가 정보다. 실패해도 화면의 주 기능은 건드리지 않는다.
  }
}

document.addEventListener("DOMContentLoaded", () => void loadSystemBadges());
