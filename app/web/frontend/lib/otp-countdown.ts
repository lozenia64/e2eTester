// Run 상세와 수트 실행이 함께 쓰는 OTP 유효시간 카운트다운. app.js 에서 승격.
// 타이머 슬롯은 모듈 전역 하나뿐이라 두 화면을 오갈 때 정리가 빠지면 누적된다 —
// start 는 항상 이전 타이머를 먼저 정리한다.

const OTP_VALIDITY_SECONDS = 180;

let otpCountdownTimer: number | null = null;
let currentTarget: HTMLElement | null = null;

function formatClock(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function clearOtpCountdownTimer(): void {
  if (otpCountdownTimer !== null) {
    window.clearInterval(otpCountdownTimer);
    otpCountdownTimer = null;
  }
}

export function stopOtpCountdown(): void {
  clearOtpCountdownTimer();
  if (currentTarget) {
    currentTarget.classList.remove("is-hidden");
    currentTarget.hidden = true;
    currentTarget.textContent = "";
    currentTarget = null;
  }
}

export function startOtpCountdown(startedAtIso: string | null, target: HTMLElement | null): void {
  if (!target) {
    return;
  }
  clearOtpCountdownTimer();
  currentTarget = target;
  const startedMs = startedAtIso ? new Date(startedAtIso).getTime() : Date.now();
  const baselineMs = Number.isNaN(startedMs) ? Date.now() : startedMs;
  target.classList.remove("is-hidden");
  target.hidden = false;

  const tick = (): void => {
    const remaining = OTP_VALIDITY_SECONDS - Math.floor((Date.now() - baselineMs) / 1000);
    if (remaining > 0) {
      target.textContent = `⏳ 인증 유효시간 ${formatClock(remaining * 1000)} 남음`;
      target.classList.remove("bg-red-100", "text-red-700");
      target.classList.add("bg-amber-100", "text-amber-700");
    } else {
      target.textContent = "⚠ 인증 유효시간이 지났을 수 있습니다. 인증을 다시 시도하세요.";
      target.classList.remove("bg-amber-100", "text-amber-700");
      target.classList.add("bg-red-100", "text-red-700");
      clearOtpCountdownTimer();
    }
  };
  tick();
  otpCountdownTimer = window.setInterval(tick, 1000);
}

export function moduleStartedAtFromRun(runPayload: unknown, moduleId: string): string | null {
  const payload = runPayload as
    | { modules?: Array<{ module_id?: string; started_at?: string | null }> }
    | null
    | undefined;
  const module = (payload?.modules ?? []).find((item) => item.module_id === moduleId);
  return module?.started_at ?? null;
}
