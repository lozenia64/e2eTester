import { beforeEach, describe, expect, it } from "vitest";
import { syncConditionalFields, updateOtpPanel } from "./run-form";

beforeEach(() => {
  document.body.innerHTML = "";
});

function formWith(authMethod: string): HTMLFormElement {
  const form = document.createElement("form");
  form.innerHTML = `
    <select name="auth_method">
      <option value="mobile" ${authMethod === "mobile" ? "selected" : ""}></option>
      <option value="id" ${authMethod === "id" ? "selected" : ""}></option>
    </select>
    <label class="conditional-field is-hidden" data-show-when-key="auth_method"
           data-show-when-value="mobile" data-required="true">
      <input name="phone" required>
    </label>`;
  return form;
}

describe("syncConditionalFields", () => {
  it("조건이 맞으면 필드를 보인다", () => {
    const form = formWith("mobile");
    syncConditionalFields(form);
    expect(form.querySelector(".conditional-field")!.classList.contains("is-hidden")).toBe(false);
  });

  it("조건이 어긋나면 감춘다", () => {
    const form = formWith("id");
    form.querySelector(".conditional-field")!.classList.remove("is-hidden");
    syncConditionalFields(form);
    expect(form.querySelector(".conditional-field")!.classList.contains("is-hidden")).toBe(true);
  });

  it("감춰진 필수 필드는 required 를 벗는다 — 안 그러면 폼이 제출되지 않는다", () => {
    const form = formWith("id");
    syncConditionalFields(form);
    expect(form.querySelector<HTMLInputElement>('[name="phone"]')!.required).toBe(false);
  });

  it("값이 콤마 목록이면 그중 하나만 맞아도 보인다", () => {
    const form = formWith("mobile");
    form.querySelector(".conditional-field")!.setAttribute("data-show-when-value", "id,mobile");
    syncConditionalFields(form);
    expect(form.querySelector(".conditional-field")!.classList.contains("is-hidden")).toBe(false);
  });
});

describe("updateOtpPanel", () => {
  it("app.js 다리가 모듈 로드 뒤 설치돼도 WAITING_INPUT 패널을 갱신한다", () => {
    let countdownStartedAt: string | null | undefined;
    window.__executeLegacy = {
      setInlineFeedback: () => undefined,
      readErrorMessage: async () => "",
      bindScheduleBuilder: () => undefined,
      buildScheduleCron: () => ({}),
      refreshScheduleList: async () => undefined,
      startOtpCountdown: (startedAt) => { countdownStartedAt = startedAt; },
      stopOtpCountdown: () => undefined,
      moduleStartedAtFromRun: (_run, moduleId) => moduleId === "auth" ? "2026-08-26T00:00:00Z" : null,
    };
    document.body.innerHTML = `
      <section id="otp-panel" class="is-hidden"><p id="otp-prompt"></p></section>`;

    updateOtpPanel({
      awaiting_input_module_id: "auth",
      awaiting_input_prompt: "휴대폰으로 받은 OTP를 입력하세요.",
    });

    const panel = document.getElementById("otp-panel")!;
    expect(panel.classList.contains("is-hidden")).toBe(false);
    expect(panel.dataset.awaitingModuleId).toBe("auth");
    expect(document.getElementById("otp-prompt")!.textContent).toBe("휴대폰으로 받은 OTP를 입력하세요.");
    expect(countdownStartedAt).toBe("2026-08-26T00:00:00Z");
  });
});
