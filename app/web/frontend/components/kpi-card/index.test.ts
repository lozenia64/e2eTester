import { beforeEach, describe, expect, it, vi } from "vitest";
// @ts-expect-error Idiomorph 0.7.4는 선언 파일을 제공하지 않는다.
import { Idiomorph } from "idiomorph";
import { animateCountUp, bindKpiCards } from "./index";

function makeCard(value: string): HTMLElement {
  const card = document.createElement("article");
  card.className = "kpi-card";
  card.dataset.tone = "passed";
  const el = document.createElement("span");
  el.className = "kpi-card__value";
  el.dataset.target = value;
  el.textContent = "0";
  card.appendChild(el);
  document.body.appendChild(card);
  return card;
}

function kpiFragment(value: string): string {
  return `
    <article id="kpi-passed" class="kpi-card" data-tone="passed" data-key="passed" data-size="md">
      <span class="kpi-card__value" data-target="${value}">${value}</span>
    </article>
  `;
}

beforeEach(() => {
  document.body.innerHTML = "";
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("animateCountUp", () => {
  it("최종적으로 목표값에 도달한다", async () => {
    const el = document.createElement("span");
    animateCountUp(el, 94, 0);
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(el.textContent).toBe("94");
  });

  it("목표가 0 이면 0 을 표시한다", async () => {
    const el = document.createElement("span");
    animateCountUp(el, 0, 0);
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    expect(el.textContent).toBe("0");
  });
});

describe("bindKpiCards", () => {
  it("data-target 이 숫자인 카드만 애니메이션한다", async () => {
    makeCard("94");
    const textCard = makeCard("추정치 미설정");
    bindKpiCards(document);
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    const textValue = textCard.querySelector(".kpi-card__value")!;
    expect(textValue.textContent).toBe("추정치 미설정");
  });

  it("이미 바인딩된 카드를 두 번 처리해도 애니메이션을 다시 예약하지 않는다", () => {
    const requestAnimationFrame = vi.fn();
    vi.stubGlobal("requestAnimationFrame", requestAnimationFrame);

    makeCard("7");
    bindKpiCards(document);
    bindKpiCards(document);

    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
  });

  it("이미 바인딩된 카드도 목표값이 바뀌면 다시 카운트업한다", () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));

    const card = makeCard("7");
    const valueEl = card.querySelector<HTMLElement>(".kpi-card__value")!;

    bindKpiCards(document);
    expect(valueEl.textContent).toBe("7");

    valueEl.dataset.target = "9";
    bindKpiCards(document);

    expect(valueEl.textContent).toBe("9");
  });

  it("동일 KPI를 Idiomorph로 갱신한 뒤 다시 바인딩해도 애니메이션을 다시 예약하지 않는다", () => {
    const requestAnimationFrame = vi.fn();
    vi.stubGlobal("requestAnimationFrame", requestAnimationFrame);
    document.body.innerHTML = `<section id="dash-zone-stats">${kpiFragment("7")}</section>`;

    const zone = document.querySelector<HTMLElement>("#dash-zone-stats")!;
    const card = document.querySelector<HTMLElement>("#kpi-passed")!;
    bindKpiCards(document);

    Idiomorph.morph(zone, kpiFragment("7"), { morphStyle: "innerHTML" });
    expect(document.querySelector("#kpi-passed")).toBe(card);

    bindKpiCards(document);

    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
  });

  it("목표값이 바뀐 KPI를 Idiomorph로 갱신하면 애니메이션을 한 번 더 예약한다", () => {
    const requestAnimationFrame = vi.fn();
    vi.stubGlobal("requestAnimationFrame", requestAnimationFrame);
    document.body.innerHTML = `<section id="dash-zone-stats">${kpiFragment("7")}</section>`;

    const zone = document.querySelector<HTMLElement>("#dash-zone-stats")!;
    const card = document.querySelector<HTMLElement>("#kpi-passed")!;
    bindKpiCards(document);

    Idiomorph.morph(zone, kpiFragment("9"), { morphStyle: "innerHTML" });
    expect(document.querySelector("#kpi-passed")).toBe(card);

    bindKpiCards(document);

    expect(requestAnimationFrame).toHaveBeenCalledTimes(2);
  });
});
