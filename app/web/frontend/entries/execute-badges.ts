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
