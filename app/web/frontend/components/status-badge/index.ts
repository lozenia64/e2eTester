import {
  MODULE_STATUS_LABELS,
  STATUS_TONES,
  type StatusTone,
} from "../../lib/status.generated";

// 서버 status 문자열 → 톤. status_labels.py 의 *_badge_tone() 과 같은 규칙이다.
const TONE_ALIASES: Record<string, StatusTone> = {
  failed: "anomaly",
  queued: "pending",
  not_inspected: "pending",
};

export function normalizeTone(status: string): StatusTone {
  const key = String(status ?? "").toLowerCase();
  const alias = TONE_ALIASES[key];
  if (alias) return alias;
  return (STATUS_TONES as readonly string[]).includes(key) ? (key as StatusTone) : "pending";
}

export function statusLabel(status: string): string {
  const key = String(status ?? "").toLowerCase();
  return MODULE_STATUS_LABELS[key] ?? MODULE_STATUS_LABELS[normalizeTone(key)] ?? key;
}

export function renderStatusBadge(
  status: string,
  options: { size?: "sm" | "md" } = {},
): HTMLElement {
  const el = document.createElement("span");
  el.className = "status-badge";
  el.dataset.tone = normalizeTone(status);
  el.dataset.size = options.size ?? "md";
  el.textContent = statusLabel(status);
  return el;
}
