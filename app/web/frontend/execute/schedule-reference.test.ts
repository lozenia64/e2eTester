import { describe, expect, it } from "vitest";
import { rememberSchedulePreset, scheduleReference } from "./schedule-reference";
import { collectSuiteScheduleRequest } from "./suite-form";
import { getPresetState } from "./presets";
import { applyPresetToForm } from "./presets";

describe("예약 프리셋 참조", () => {
  it("과거 프리셋에 없는 인증값이 폼에 남아 있으면 저장을 안내한다", () => {
    const form = document.createElement("form");
    form.innerHTML = '<input name="name" value="테스트"><input name="manager_employee_id" value="7654321">';
    applyPresetToForm(form, {
      preset_id: "old", system_code: "fp", system_name: "FP", name: "과거 프리셋",
      auth_method: "phone", input_data: { name: "테스트" }, selected_module_ids: [],
      created_at: "", updated_at: "",
    });
    expect(() => scheduleReference(form)).toThrow("저장");
  });
  it("프리셋 ID와 예약 브라우저 모드를 보내고 인증값은 복사하지 않는다", () => {
    const form = document.createElement("form");
    form.innerHTML = '<input name="name" value="테스트"><input name="manager_employee_id" value="1234567"><select name="browser_mode"><option>headed</option><option selected>headless</option></select>';
    rememberSchedulePreset(form, "p1");
    expect(scheduleReference(form)).toEqual({ preset_id: "p1", browser_mode: "headless" });
    form.querySelector<HTMLSelectElement>("select")!.value = "headed";
    expect(scheduleReference(form).browser_mode).toBe("headed");
    form.querySelector<HTMLInputElement>('[name="manager_employee_id"]')!.value = "7654321";
    expect(() => scheduleReference(form)).toThrow("저장");
  });

  it("프리셋을 선택하지 않은 인증 폼은 저장 안내를 표시한다", () => {
    const form = document.createElement("form");
    form.innerHTML = '<section data-role="preset-panel"></section><input name="name" value="테스트">';
    expect(() => scheduleReference(form)).toThrow("프리셋");
  });

  it("수트 예약은 선택한 시스템별 ID만 보내고 인증값은 포함하지 않는다", () => {
    const form = document.createElement("form");
    form.innerHTML = '<input type="checkbox" checked data-role="suite-system-checkbox" data-system-code="fp" data-auth-required="true"><select name="browser_mode"><option>headless</option></select>';
    getPresetState().suitePresetSelection.set("fp", "p1");
    const result = collectSuiteScheduleRequest(form);
    expect(result.preset_ids).toEqual({ fp: "p1" });
    expect(result.systems).toEqual({});
    expect(result.browser_mode).toBe("headless");
    expect(result.selected_system_codes).toEqual(["fp"]);
  });
});
