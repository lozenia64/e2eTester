// Cycle 4까지 app.js에 남는 공용 일정·피드백·OTP 보조 함수의 유일한 경계다.
// 각 보조 함수가 TypeScript로 이관되면 해당 계약을 함께 줄이고, app.js 소멸 시 파일도 제거한다.
export type ScheduleBuildResult = { cron?: string; summary?: string; error?: string };

declare global {
  interface Window {
    __executeLegacy: {
      setInlineFeedback(element: Element | null, message: string, tone?: "error" | "success" | "info"): void;
      readErrorMessage(response: Response): Promise<string>;
      bindScheduleBuilder(form: HTMLFormElement): void;
      buildScheduleCron(form: HTMLFormElement): ScheduleBuildResult;
      refreshScheduleList(): Promise<void>;
      startOtpCountdown(startedAtIso: string | null): void;
      stopOtpCountdown(): void;
      moduleStartedAtFromRun(run: unknown, moduleId: string): string | null;
    };
    // Run 상세 WebSocket 호출부가 TypeScript로 이관되면 공용 OTP 모듈과 함께 재검토·제거한다.
    __executeOtpPanel?: { updateOtpPanel(runOrMessage: unknown): void };
  }
}

export function getLegacy(): Window["__executeLegacy"] {
  const legacy = window.__executeLegacy;
  if (!legacy) throw new Error("레거시 실행 다리가 아직 준비되지 않았습니다.");
  return legacy;
}
