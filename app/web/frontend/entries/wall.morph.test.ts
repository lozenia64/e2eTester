// @ts-expect-error Idiomorph 0.7.4는 선언 파일을 제공하지 않는다.
import { Idiomorph } from "idiomorph";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("wall morph identity", () => {
  it("stable lane id keeps a lane with its logical system after reorder", () => {
    document.body.innerHTML = `
      <div id="wall-body">
        <div class="wall-timeline__lanes">
          <div id="wall-lane-hom" class="wall-lane" data-system-code="hom">HOM</div>
          <div id="wall-lane-fp" class="wall-lane" data-system-code="fp">FP</div>
        </div>
      </div>
    `;
    const homLane = document.querySelector<HTMLElement>("#wall-lane-hom")!;

    Idiomorph.morph(
      document.querySelector(".wall-timeline__lanes")!,
      `
        <div id="wall-lane-fp" class="wall-lane" data-system-code="fp">FP</div>
        <div id="wall-lane-hom" class="wall-lane" data-system-code="hom">HOM</div>
      `,
      { morphStyle: "innerHTML" },
    );

    expect(document.querySelector("#wall-lane-hom")).toBe(homLane);
    expect(homLane.dataset.systemCode).toBe("hom");
  });
});
