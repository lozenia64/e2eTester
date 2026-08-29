import { beforeEach, describe, expect, it, vi } from "vitest";
import { syncConditionalFields, updateOtpPanel } from "./run-form";
import { startOtpCountdown } from "../lib/otp-countdown";

vi.mock("../lib/otp-countdown", () => ({
  startOtpCountdown: vi.fn(),
  stopOtpCountdown: vi.fn(),
  moduleStartedAtFromRun: (_run: unknown, moduleId: string) =>
    (moduleId === "auth" ? "2026-08-26T00:00:00Z" : null),
}));

beforeEach(() => {
  document.body.innerHTML = "";
  vi.clearAllMocks();
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
  it("WAITING_INPUT 패널을 갱신하고 해당 모듈의 started_at 으로 카운트다운을 건다", () => {
    document.body.innerHTML = `
      <section id="otp-panel" class="is-hidden"><p id="otp-prompt"></p></section>
      <p id="otp-countdown" class="is-hidden"></p>`;

    updateOtpPanel({
      awaiting_input_module_id: "auth",
      awaiting_input_prompt: "휴대폰으로 받은 OTP를 입력하세요.",
    });

    const panel = document.getElementById("otp-panel")!;
    expect(panel.classList.contains("is-hidden")).toBe(false);
    expect(panel.dataset.awaitingModuleId).toBe("auth");
    expect(document.getElementById("otp-prompt")!.textContent).toBe("휴대폰으로 받은 OTP를 입력하세요.");
    expect(startOtpCountdown).toHaveBeenCalledWith(
      "2026-08-26T00:00:00Z",
      document.getElementById("otp-countdown"),
    );
  });
});
