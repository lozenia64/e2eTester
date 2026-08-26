import { describe, expect, it } from "vitest";
import { applyPresetToForm, presetSummaryText } from "./presets";

describe("presetSummaryText", () => {
  it("인증 수단과 계정 정보를 한 줄로 요약한다", () => {
    const text = presetSummaryText({
      preset_id: "p1",
      system_code: "hom",
      system_name: "홈택스",
      name: "홍길동 휴대폰인증",
      auth_method: "phone",
      input_data: { name: "홍길동", phone_number: "010-1234-5678" },
      selected_module_ids: ["login", "list"],
      created_at: "2026-08-26T00:00:00+00:00",
      updated_at: "2026-08-26T00:00:00+00:00",
    });

    expect(text).toBe("휴대폰인증 · 홍길동 · 010-1234-5678");
  });

  it("입력이 비어도 예외를 던지지 않는다", () => {
    expect(() => presetSummaryText({
      preset_id: "p2",
      system_code: "hom",
      system_name: "홈택스",
      name: "빈 프리셋",
      auth_method: "",
      input_data: {},
      selected_module_ids: [],
      created_at: "2026-08-26T00:00:00+00:00",
      updated_at: "2026-08-26T00:00:00+00:00",
    })).not.toThrow();
  });
});

describe("applyPresetToForm", () => {
  it("폼 필드와 선택 모듈을 프리셋 값으로 적용한다", () => {
    const form = document.createElement("form");
    form.innerHTML = `
      <input name="login_id">
      <select name="auth_method"><option value="phone">휴대폰인증</option><option value="kakao" selected>카카오인증</option></select>
      <div class="conditional-field is-hidden" data-show-when-key="auth_method" data-show-when-value="phone" data-required="true"><input name="phone_number"></div>
      <div data-role="module-selector">
        <p data-role="module-selection-summary"></p>
        <button data-role="module-graph-node" data-module-id="login" data-order="0" data-selected="false"></button>
        <button data-role="module-graph-node" data-module-id="list" data-order="1" data-selected="false"></button>
      </div>`;

    applyPresetToForm(form, {
      preset_id: "p1",
      system_code: "hom",
      system_name: "홈택스",
      name: "n",
      auth_method: "phone",
      input_data: { login_id: "hong", auth_method: "phone" },
      selected_module_ids: ["list"],
      created_at: "2026-08-26T00:00:00+00:00",
      updated_at: "2026-08-26T00:00:00+00:00",
    });

    expect(form.querySelector<HTMLInputElement>('[name="login_id"]')!.value).toBe("hong");
    expect(form.querySelector<HTMLSelectElement>('[name="auth_method"]')!.value).toBe("phone");
    expect(form.querySelector(".conditional-field")!.classList.contains("is-hidden")).toBe(false);
    expect(form.querySelector<HTMLInputElement>('[name="phone_number"]')!.required).toBe(true);
    expect(form.querySelector<HTMLButtonElement>('[data-module-id="login"]')!.dataset.selected).toBe("false");
    expect(form.querySelector<HTMLButtonElement>('[data-module-id="list"]')!.dataset.selected).toBe("true");
    expect(form.querySelector('[data-role="module-selection-summary"]')!.textContent).toBe("1 / 2 선택 · 1개 제외");
  });

  it("프리셋에 없는 필드는 건드리지 않는다", () => {
    const form = document.createElement("form");
    form.innerHTML = '<input name="login_id" value="기존"><input name="etc" value="유지">';

    applyPresetToForm(form, {
      preset_id: "p1",
      system_code: "hom",
      system_name: "홈택스",
      name: "n",
      auth_method: "",
      input_data: { login_id: "새값" },
      selected_module_ids: [],
      created_at: "2026-08-26T00:00:00+00:00",
      updated_at: "2026-08-26T00:00:00+00:00",
    });

    expect(form.querySelector<HTMLInputElement>('[name="etc"]')!.value).toBe("유지");
  });
});
