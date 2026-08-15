# Dashboard Sidebar Shell Inset (SPEC-UI-008) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 데스크톱에서 고정 사이드바(`w-64`)가 대시보드 본문을 가리지 않도록 `main` 좌측 인셋을 복원한다. UI-007 무스크롤·UI-006 가시성 회귀 없음.

**Architecture:** `dashboard.css`의 `padding: 0` shorthand 제거 → `padding-top/right/bottom: 0` + `@media (min-width: 768px) { padding-left: 16rem }`. `.dash`에 `width/max-width: 100%`. Playwright로 사이드바-본문 겹침 AC. Orca E2E 스크린샷.

**Tech Stack:** CSS only (no JS), pytest + Playwright, Orca browser / Playwright MCP (e2e-browser skill).

**Spec:** `docs/specs/dashboard/08-sidebar-shell-inset.md`

**Evidence:** `research/dashboard-sidebar-overlap-orca.png`

## Global Constraints

- **Layout inset only:** `z-index`·사이드바 디자인·메뉴 항목 변경 금지
- **No `padding: 0` on `main`:** shorthand가 `md:pl-64` 재삭제 — longhand만
- **No `100vw` on `.dash`/`main`:** 가용 폭은 `main` 콘텐츠 박스 안 `100%`
- **Mobile unchanged:** `<768px` → `padding-left: 0`, 사이드바 오버레이
- **UI-007 preserved:** 문서·Zone C 무스크롤, row partition, density tier
- **Scope:** `dashboard.css`, `dashboard.html` (cache bust), `tests/test_dashboard_viewport.py` only
- **Cache bust:** `dashboard.css?v=5` (JS 버전 변경 없음)
- **E2E gate:** Task 3 MUST follow `.agents/skills/e2e-browser/SKILL.md`

---

## File Map

| File | Action | Change |
| --- | --- | --- |
| `app/web/static/dashboard.css` | **Modify** | Shell inset: targeted padding + `.dash` width |
| `app/web/templates/dashboard.html` | **Modify** | `dashboard.css?v=5` |
| `tests/test_dashboard_viewport.py` | **Modify** | AC-001~005 helpers + tests |
| `app/web/templates/base.html` | **No change** | `md:pl-64` 유지 — CSS가 보완 |

---

### Task 1: Tests first — AC-001~005 (TDD red)

**Files:**
- Modify: `tests/test_dashboard_viewport.py`

**Interfaces:**
- Produces: `_sidebar_inset_metrics(page) -> dict`
- Produces: failing tests `@pytest.mark.spec("SPEC-UI-008", ...)`

**Note:** Ephemeral test server는 `dashboard.html` → `base.html` 전체 렌더 → `#app-sidebar` 존재. 1280×720은 `md` breakpoint 충족.

- [ ] **Step 1: Add helper `_sidebar_inset_metrics`**

```python
def _sidebar_inset_metrics(page) -> dict:
    return page.evaluate(
        """() => {
            const sb = document.querySelector('#app-sidebar');
            const dash = document.querySelector('.dash');
            const main = document.querySelector('main');
            if (!sb || !dash || !main) return { ok: false, reason: 'missing' };
            const sr = sb.getBoundingClientRect();
            const dr = dash.getBoundingClientRect();
            const mcs = getComputedStyle(main);
            const overlapPx = Math.max(0, sr.right - dr.left);
            return {
                ok: overlapPx <= 1 && dr.left >= sr.right - 1,
                dashLeft: dr.left,
                sidebarRight: sr.right,
                sidebarWidth: sr.width,
                overlapPx,
                mainPaddingLeft: mcs.paddingLeft,
                dashWidth: dr.width,
                innerWidth: window.innerWidth,
            };
        }"""
    )
```

- [ ] **Step 2: AC-001 사이드바-본문 비겹침**

```python
@pytest.mark.spec("SPEC-UI-008", "AC-001")
def test_dash_not_under_sidebar_1280x720(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector("#app-sidebar")
    page.wait_for_selector(".dash")
    m = _sidebar_inset_metrics(page)
    assert m["ok"], m
    assert m["overlapPx"] <= 1, m
```

- [ ] **Step 3: AC-002 main padding-left**

```python
@pytest.mark.spec("SPEC-UI-008", "AC-002")
def test_main_padding_left_desktop_1280x720(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector("main")
    pl = page.eval_on_selector("main", "el => getComputedStyle(el).paddingLeft")
    assert pl in ("256px", "16rem") or float(pl.replace("px", "")) >= 250, pl
```

- [ ] **Step 4: AC-003 히어로·KPI 좌측 가시**

```python
@pytest.mark.spec("SPEC-UI-008", "AC-003")
def test_hero_and_first_kpi_right_of_sidebar(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-hero__title")
    m = _sidebar_inset_metrics(page)
    sw = m["sidebarWidth"]
    title_left = page.eval_on_selector(".dash-hero__title", "el => el.getBoundingClientRect().left")
    tile_left = page.eval_on_selector(
        "#dash-zone-stats .dash-stats__tile:first-child",
        "el => el.getBoundingClientRect().left",
    )
    assert title_left >= sw - 1, {"title_left": title_left, "sidebarWidth": sw}
    assert tile_left >= sw - 1, {"tile_left": tile_left, "sidebarWidth": sw}
    assert page.locator("#dash-zone-stats .dash-stats__tile:first-child .dash-stats__label").inner_text() == "이상징후"
```

- [ ] **Step 5: AC-004 identity 좌측 가시**

```python
@pytest.mark.spec("SPEC-UI-008", "AC-004")
def test_system_identity_right_of_sidebar(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-sys-row__icon")
    sw = _sidebar_inset_metrics(page)["sidebarWidth"]
    icon_left = page.eval_on_selector(".dash-sys-row__icon", "el => el.getBoundingClientRect().left")
    name_left = page.eval_on_selector(".dash-sys-row__name", "el => el.getBoundingClientRect().left")
    assert icon_left >= sw - 1
    assert name_left >= sw - 1
```

- [ ] **Step 6: AC-005 모바일 인셋 없음**

```python
@pytest.mark.spec("SPEC-UI-008", "AC-005")
def test_no_main_inset_mobile_390x844(page, live_server: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash")
    pl = page.eval_on_selector("main", "el => getComputedStyle(el).paddingLeft")
    assert pl == "0px", pl
    dash_left = page.eval_on_selector(".dash", "el => el.getBoundingClientRect().left")
    assert dash_left <= 1, dash_left
```

- [ ] **Step 7: Run new tests — expect FAIL**

```bash
python3 -m pytest tests/test_dashboard_viewport.py -v -k "SPEC-UI-008 or dash_not_under or main_padding_left or right_of_sidebar or no_main_inset"
```

Expected: AC-001~004 fail (overlapPx > 0, paddingLeft 0px). AC-005 may already pass.

- [ ] **Step 8: Commit**

```bash
git add tests/test_dashboard_viewport.py
git commit -m "test: add SPEC-UI-008 sidebar shell inset ACs"
```

---

### Task 2: CSS — shell inset fix

**Files:**
- Modify: `app/web/static/dashboard.css` (lines 31–60, `.dash` block ~62–73)

- [ ] **Step 1: Replace `padding: 0` block (viewport-fit shell)**

**Before (delete):**

```css
body:has(.dash) main,
body:has(.dash) main > div {
  max-width: none;
  padding: 0;
  height: 100dvh;
  overflow: hidden;
}
```

**After:**

```css
body:has(.dash) main,
body:has(.dash) main > div {
  max-width: none;
  padding-top: 0;
  padding-right: 0;
  padding-bottom: 0;
  height: 100dvh;
  overflow: hidden;
  box-sizing: border-box;
}

@media (min-width: 768px) {
  body:has(.dash) main {
    padding-left: 16rem;
    width: 100%;
  }

  body:has(.dash) main > div {
    padding-left: 0;
    width: 100%;
    max-width: none;
  }
}
```

- [ ] **Step 2: Merge into existing mobile `@media (max-width: 767px)` block**

Add to existing mobile rules (do not duplicate media query):

```css
  body:has(.dash) main,
  body:has(.dash) main > div {
    padding-left: 0;
    width: 100%;
  }
```

- [ ] **Step 3: Add `.dash` width constraints**

In `.dash { ... }` block add:

```css
  width: 100%;
  max-width: 100%;
  min-width: 0;
```

- [ ] **Step 4: Run UI-008 tests — expect PASS**

```bash
python3 -m pytest tests/test_dashboard_viewport.py -v -k "dash_not_under or main_padding_left or right_of_sidebar or no_main_inset"
```

- [ ] **Step 5: Commit**

```bash
git add app/web/static/dashboard.css
git commit -m "fix(dashboard): SPEC-UI-008 restore sidebar shell inset on desktop"
```

---

### Task 3: Cache bust + regression suite + E2E

**Files:**
- Modify: `app/web/templates/dashboard.html`
- Create: `.superpowers/sdd/2026-08-15-sidebar-shell-inset/e2e-report.md`

**Skill:** Read `.agents/skills/e2e-browser/SKILL.md` before E2E.

- [ ] **Step 1: Bump CSS version in `dashboard.html`**

```html
<link rel="stylesheet" href="/static/dashboard.css?v=5">
```

(`dashboard.js?v=16` — 변경 없음)

- [ ] **Step 2: Full regression pytest**

```bash
python3 -m pytest tests/test_dashboard_fragments_http.py tests/test_dashboard_viewport.py tests/test_daily_dashboard.py -q
```

Expected: all pass including UI-007 (`zone_c`, `equal_partition`, `no_data_scrollable`) and UI-006 (`hero_title`, `four_kpi`, `identity`).

- [ ] **Step 3: E2E — e2e-browser**

| ID | Check |
| --- | --- |
| E2E-INSET-1 | `.dash.left >= #app-sidebar.right` |
| E2E-INSET-2 | "오늘의 점검 현황" 전체 가시 |
| E2E-INSET-3 | KPI 첫 타일 "이상징후" 가시 |
| E2E-INSET-4 | 첫 카드 아이콘·이름 가시 |

Orca `screenshot --json` at 1280×720 on `http://127.0.0.1:2222/` — compare with `research/dashboard-sidebar-overlap-orca.png` (before). Save after-shot to `research/dashboard-sidebar-inset-fixed-orca.png`.

**evaluate (E2E-INSET-1):**

```javascript
() => {
  const sb = document.querySelector('#app-sidebar');
  const dash = document.querySelector('.dash');
  const sr = sb.getBoundingClientRect();
  const dr = dash.getBoundingClientRect();
  return { ok: dr.left >= sr.right - 1, dashLeft: dr.left, sidebarRight: sr.right };
}
```

- [ ] **Step 4: Write `e2e-report.md`**

- [ ] **Step 5: Commit**

```bash
git add app/web/templates/dashboard.html
git commit -m "chore(dashboard): bump cache bust for SPEC-UI-008"
```

---

## Spec Coverage Self-Review

| Spec | Task |
| --- | --- |
| FR-001 desktop inset | Task 1 AC-001/002, Task 2 |
| FR-002 content width | Task 2 `.dash width:100%`, AC-001 |
| FR-003 UI-006/007 regression | Task 3 full suite |
| FR-004 mobile | Task 1 AC-005 |
| AC-001~005 | Task 1 |
| AC-006 UI-007 regression | Task 3 full suite |
| NFR-002 cache bust v=5 | Task 3 |
| NFR-003 Orca E2E | Task 3 |

---

## Migration Notes

| Current (broken) | Target (UI-008) |
| --- | --- |
| `main { padding: 0 }` | `padding-top/right/bottom: 0` only |
| desktop `padding-left` missing | `padding-left: 16rem` @ `min-width: 768px` |
| `.dash` implicit full viewport width | `width: 100%; max-width: 100%` |
| Hero/KPI under sidebar | `dash.left >= sidebar.right` |

---

## Risk / Edge Cases

| Risk | Mitigation |
| --- | --- |
| `box-sizing` on `main` changes width math | `box-sizing: border-box` + AC-001 overlap check |
| Tailwind `md:pl-64` + CSS `padding-left: 16rem` double inset | CSS **replaces** shorthand zeroing; both set 16rem — no double if shorthand removed. Optional: rely on CSS only, Tailwind class redundant but harmless |
| Test server viewport 1280 lacks sidebar at `<768` | AC-005 uses 390×844; desktop tests use 1280×720 |
| Orca browser unavailable | Playwright MCP fallback per e2e-browser skill |

---

## Suggested Commit Sequence

1. `test: add SPEC-UI-008 sidebar shell inset ACs`
2. `fix(dashboard): SPEC-UI-008 restore sidebar shell inset on desktop`
3. `chore(dashboard): bump cache bust for SPEC-UI-008`

---

## Execution Handoff

**Plan saved to `docs/superpowers/plans/2026-08-15-sidebar-shell-inset.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** — Tasks 1→3 sequential subagents
2. **Inline Execution** — same session, ~30min (small diff)

Which approach do you want?
