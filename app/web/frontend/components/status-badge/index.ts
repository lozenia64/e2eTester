import {
  MODULE_STATUS_LABELS,
  STATUS_TONE_MAP,
  STATUS_TONES,
  type StatusTone,
} from "../../lib/status.generated";

// 서버 status 문자열 → 톤. 규칙을 여기 다시 적지 않는다 — STATUS_TONE_MAP 은
// status_labels.py 의 run_status_badge_tone()·module_status_badge_tone() 을
// 실제로 호출해 생성한 것이라, 상태가 늘어도 재생성만 하면 따라온다(frontend_tokens 게이트).
export function normalizeTone(status: string): StatusTone {
  const key = String(status ?? "").toLowerCase();
  const mapped = STATUS_TONE_MAP[key];
  if (mapped) return mapped;
  // enum 에 없는 합성 상태(not_inspected 등)와 미지의 값은 pending 으로 떨어뜨린다.
  // 톤 이름 자체가 넘어오는 경우(data-tone 재입력)도 그대로 통과시킨다.
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
