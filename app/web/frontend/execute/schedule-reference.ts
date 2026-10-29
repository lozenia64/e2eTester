// 개별 점검 폼에 적용한 프리셋과 적용 당시 인증값을 기억한다.
const applied = new WeakMap<HTMLFormElement, { id: string; values: string }>();

function authValues(form: HTMLFormElement, expected?: Record<string, string>): string {
  return JSON.stringify([...new FormData(form).entries()]
    .filter(([key]) => key !== "browser_mode")
    .map(([key, value]) => [key, String(expected ? expected[key] ?? "" : value).trim()])
    .sort(([left], [right]) => left!.localeCompare(right!)));
}

export function rememberSchedulePreset(form: HTMLFormElement, id: string, expected?: Record<string, string>): void {
  applied.set(form, { id, values: authValues(form, expected) });
}

export function scheduleReference(form: HTMLFormElement): { preset_id?: string; browser_mode: string } {
  const preset = applied.get(form);
  if (!preset && form.querySelector('[data-role="preset-panel"]')) {
    throw new Error("예약에 연결할 프리셋을 선택해 주세요. 새 인증정보는 먼저 프리셋으로 저장해 주세요.");
  }
  if (preset && preset.values !== authValues(form)) {
    throw new Error("프리셋 적용 후 인증정보가 바뀌었습니다. 변경값을 프리셋으로 저장한 뒤 예약해 주세요.");
  }
  return {
    ...(preset ? { preset_id: preset.id } : {}),
    browser_mode: form.querySelector<HTMLSelectElement>('[name="browser_mode"]')?.value || "headed",
  };
}
