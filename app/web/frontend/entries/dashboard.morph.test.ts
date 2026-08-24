// @ts-expect-error Idiomorph 0.7.4는 선언 파일을 제공하지 않는다.
import { Idiomorph } from "idiomorph";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("dashboard morph identity", () => {
  it("stable system id keeps a focused row with its logical system after attention reorder", () => {
    document.body.innerHTML = `
      <div id="dash-zone-matrix">
        <div id="dash-system-hom" class="dash-sys-row" data-system-code="hom">
          <button type="button">홈</button>
        </div>
        <div id="dash-system-mhm" class="dash-sys-row" data-system-code="mhm">
          <button type="button">마이홈</button>
        </div>
      </div>
    `;
    const focusedRow = document.querySelector<HTMLElement>("#dash-system-hom")!;
    const focusedButton = focusedRow.querySelector<HTMLButtonElement>("button")!;
    focusedButton.focus();

    Idiomorph.morph(
      document.querySelector("#dash-zone-matrix")!,
      `
        <div id="dash-system-mhm" class="dash-sys-row" data-system-code="mhm">
          <button type="button">마이홈</button>
        </div>
        <div id="dash-system-hom" class="dash-sys-row" data-system-code="hom">
          <button type="button">홈</button>
        </div>
      `,
      { morphStyle: "innerHTML" },
    );

    expect(document.querySelector("#dash-system-hom")).toBe(focusedRow);
    expect(focusedRow.dataset.systemCode).toBe("hom");
    expect(document.activeElement).toBe(focusedButton);
  });
});
