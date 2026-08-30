// 수트 남은 시간 — baseline(과거 PASSED 평균) + 라이브 상태로 계산한다(설계 §3.3).
// 서버는 baseline 만 주고 산술은 여기서 한다. 소켓 이벤트마다 다시 부른다.

const WAITING = "waiting_input";
const DONE = new Set(["passed", "anomaly", "error", "failed", "cancelled", "skipped"]);

export type EtaInput = {
  steps: Array<{ order: number; system_code: string; status: string }>;
  baselines: Record<string, number>;
  currentStepOrder: number | null;
  currentStepElapsedMs: number;
  suiteStatus: string;
};

export type EtaResult = {
  /** 남은 밀리초. 계산 불가면 null. */
  remainingMs: number | null;
  /** baseline 이 없는 스텝을 제외하고 계산했다. */
  partial: boolean;
  /** 입력 대기 중이라 계산을 보류했다. */
  held: boolean;
};

export function computeSuiteEta(input: EtaInput): EtaResult {
  if (input.suiteStatus.toLowerCase() === WAITING) {
    return { remainingMs: null, partial: false, held: true };
  }

  let total = 0;
  let known = 0;
  let missing = 0;

  for (const step of input.steps) {
    if (DONE.has(step.status.toLowerCase())) continue;
    const base = input.baselines[step.system_code];
    if (base === undefined) {
      missing += 1;
      continue;
    }
    known += 1;
    if (step.order === input.currentStepOrder) {
      total += Math.max(0, base - input.currentStepElapsedMs);
    } else {
      total += base;
    }
  }

  // known===0 두 경우를 가른다: 결측이 있으면(남은 스텝은 있으나 baseline 전무) null,
  // 결측도 없으면(남은 스텝 자체가 없음) 0.
  if (known === 0) return { remainingMs: missing > 0 ? null : 0, partial: missing > 0, held: false };
  return { remainingMs: total, partial: missing > 0, held: false };
}
