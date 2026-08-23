import { beforeEach, describe, expect, it, vi } from "vitest";
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

  it("이미 바인딩된 카드를 두 번 처리하지 않는다", () => {
    const card = makeCard("7");
    bindKpiCards(document);
    bindKpiCards(document);
    expect(card.dataset.kpiBound).toBe("true");
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
});
