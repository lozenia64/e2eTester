export function escapeHtml(value: string): string {
  const span = document.createElement("span");
  span.textContent = value;
  return span.innerHTML.replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}
export function setText(root: HTMLElement, selector: string, value: string): void {
  const el = root.querySelector(selector);
  if (el && el.textContent !== value) el.textContent = value;
}
export function replaceContent(root: HTMLElement, selector: string, html: string): void {
  const el = root.querySelector<HTMLElement>(selector);
  if (!el || el.dataset.content === html) return;
  const active = document.activeElement as HTMLElement | null;
  const key = active && el.contains(active) ? active.dataset.focusKey : undefined;
  el.innerHTML = html;
  el.dataset.content = html;
  if (key) Array.from(el.querySelectorAll<HTMLElement>("[data-focus-key]")).find(node => node.dataset.focusKey === key)?.focus({ preventScroll: true });
}
export const number = (value: number, decimals = 0): string => value.toLocaleString("ko-KR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
}
export function reducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}
const counters = new WeakMap<HTMLElement, () => void>();
export function countTo(root: HTMLElement, selector: string, value: number, first: boolean, decimals = 0): void {
  const el = root.querySelector<HTMLElement>(selector);
  if (!el) return;
  counters.get(el)?.();
  const previous = Number(el.dataset.numericValue ?? "0");
  const hasPrevious = el.dataset.numericValue !== undefined;
  el.dataset.numericValue = String(value);
  el.textContent = number(value, decimals);
  if ((!first && (!hasPrevious || previous === value)) || reducedMotion() || typeof requestAnimationFrame !== "function") return;
  const start = performance.now();
  const from = first ? 0 : previous;
  const duration = first ? 1100 : 250;
  let frame = 0;
  const step = (now: number): void => {
    if (reducedMotion()) { el.textContent = number(value, decimals); return; }
    const progress = Math.min((now - start) / duration, 1);
    el.textContent = number(from + (value - from) * (1 - (1 - progress) ** 3), decimals);
    if (progress < 1) frame = requestAnimationFrame(step);
  };
  frame = requestAnimationFrame(step);
  counters.set(el, () => cancelAnimationFrame(frame));
}
