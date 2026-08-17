# Dashboard Visibility Hotfix (SPEC-UI-006) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three real-screen visibility regressions (hero text, system card identity, KPI 4th tile) per SPEC-UI-006 so operators see title, system names, and all four stat tiles at 1280×720 with sidebar.

**Architecture:** CSS + minimal Jinja wrapper changes only — no API/JS. Hero grid → flex; system card grid → flex column + header row; stats grid → `minmax(0,1fr)`. Automated pytest uses `getBoundingClientRect` in-view asserts. **Live acceptance** uses `.agents/skills/e2e-browser` (Orca browser first, Playwright MCP fallback).

**Tech Stack:** Jinja2, CSS flex/grid, pytest + Playwright (automated), Orca CLI browser / Playwright MCP (manual E2E per e2e-browser skill).

**Spec:** `docs/specs/dashboard/06-visibility-hotfix.md`

## Global Constraints

- **API frozen:** Do not change `/api/dashboard/daily` or `daily_dashboard.py`.
- **JS frozen:** Do not change `dashboard.js` density/scroll logic.
- **Korean copy frozen:** Title `오늘의 점검 현황`, label `통과율`, summary `오늘 아직 점검이 시작되지 않았습니다`, first KPI `이상징후`.
- **UI-005 regression:** Keep segment bar, glyphs, CTA, chevron, attention strip, Zone C internal scroll.
- **Document no-scroll:** `scrollHeight <= innerHeight` at 1280×720.
- **Cache bust:** `dashboard.html` → `dashboard.css?v=3`.
- **Visibility asserts:** pytest must use bounding boxes inside `.dash`, not `is_visible()` alone.
- **E2E gate:** Manual live verification MUST follow `.agents/skills/e2e-browser/SKILL.md` (Orca → Playwright MCP); do not substitute ad-hoc browser automation.

---

## File Map

| File | Action | HF |
| --- | --- | --- |
| `app/web/templates/dashboard/partials/zone_a_kpi.html` | **Modify** | HF-1 — `dash-hero__top` / `dash-hero__aside` |
| `app/web/templates/dashboard/partials/_macros.html` | **Modify** | HF-2 — `dash-sys-row__header` |
| `app/web/static/dashboard.css` | **Modify** | HF-1, HF-2, HF-3 |
| `app/web/templates/dashboard.html` | **Modify** | `css?v=3`; placeholder skeleton matches new hero DOM |
| `tests/test_dashboard_viewport.py` | **Modify** | AC-001~004 bounding-box tests |
| `tests/test_dashboard_fragments_http.py` | **Modify** | AC-005 wrapper asserts |
| `docs/specs/dashboard/06-visibility-hotfix.md` | **Exists** | SSOT |

---

### Task 1: Automated tests first (TDD — bounding box AC)

**Files:**
- Modify: `tests/test_dashboard_viewport.py`
- Modify: `tests/test_dashboard_fragments_http.py`

**Interfaces:**
- Produces: failing tests `@pytest.mark.spec("SPEC-UI-006", ...)`
- Helper: `_rect_in_container(page, selector, container=".dash") -> dict` with `left, top, right, bottom, width, height`

- [ ] **Step 1: Add rect helper and empty-day fixture**

```python
def _rect_in_container(page, selector: str, *, container: str = ".dash") -> dict:
    return page.evaluate(
        """([sel, boxSel]) => {
            const el = document.querySelector(sel);
            const box = document.querySelector(boxSel);
            if (!el || !box) return null;
            const r = el.getBoundingClientRect();
            const b = box.getBoundingClientRect();
            return {
                left: r.left, top: r.top, right: r.right, bottom: r.bottom,
                width: r.width, height: r.height,
                inBox: r.left >= b.left - 1 && r.right <= b.right + 1
                    && r.top >= b.top - 1 && r.bottom <= b.bottom + 1,
            };
        }""",
        [selector, container],
    )


@pytest.fixture(scope="module")
def empty_day_live_server(registry, dashboard_user) -> str:
    """All-not-inspected payload for HF-1 summary AC."""
    data = build_daily_dashboard(
        registry.list_systems(), [], generated_at=GEN_AT, date_label="2026-08-15"
    )
    # ... same uvicorn fixture pattern as live_server ...
```

- [ ] **Step 2: Write failing AC tests**

```python
@pytest.mark.spec("SPEC-UI-006", "AC-001")
def test_hero_title_in_view_1280x720(page, empty_day_live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{empty_day_live_server}/")
    page.wait_for_selector(".dash-hero__title")
    rect = _rect_in_container(page, ".dash-hero__title")
    assert rect and rect["width"] >= 120 and rect["height"] >= 16 and rect["inBox"]
    assert "아직 점검이 시작되지 않았습니다" in page.locator(".dash-hero__summary").inner_text()
    assert page.locator(".dash-hero__rate-label").is_visible()


@pytest.mark.spec("SPEC-UI-006", "AC-002")
def test_system_identity_in_view_1280x720(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-sys-row__icon")
    icon = _rect_in_container(page, ".dash-sys-row__icon")
    name = _rect_in_container(page, ".dash-sys-row__name")
    assert icon and icon["width"] >= 24 and icon["height"] >= 24 and icon["inBox"]
    assert name and name["width"] >= 40 and name["inBox"]
    fs = page.eval_on_selector(
        ".dash-sys-row__name", "el => parseFloat(getComputedStyle(el).fontSize)"
    )
    assert fs >= 14


@pytest.mark.spec("SPEC-UI-006", "AC-003")
def test_all_four_kpi_tiles_in_dash_box(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector("#dash-zone-stats .dash-stats__tile")
    tiles = page.locator("#dash-zone-stats .dash-stats__tile")
    assert tiles.count() == 4
    for i in range(4):
        sel = f"#dash-zone-stats .dash-stats__tile:nth-child({i + 1})"
        rect = _rect_in_container(page, sel)
        assert rect and rect["inBox"], f"tile {i} outside .dash"
    assert tiles.first.locator(".dash-stats__label").inner_text() == "이상징후"


@pytest.mark.spec("SPEC-UI-006", "AC-005")
def test_fragments_include_visibility_wrappers(client: TestClient) -> None:
    kpi = client.get("/api/dashboard/daily/fragments/kpi").text
    matrix = client.get("/api/dashboard/daily/fragments/matrix").text
    assert "dash-hero__top" in kpi
    assert "dash-hero__aside" in kpi
    assert "dash-sys-row__header" in matrix
```

- [ ] **Step 3: Run tests — expect FAIL**

```bash
python3 -m pytest tests/test_dashboard_viewport.py tests/test_dashboard_fragments_http.py -v -k "UI-006 or visibility_wrappers or hero_title_in_view or system_identity or four_kpi"
```

Expected: FAIL on missing wrappers / rects.

---

### Task 2: HF-1 — Hero template + CSS

**Files:**
- Modify: `app/web/templates/dashboard/partials/zone_a_kpi.html`
- Modify: `app/web/static/dashboard.css` (Zone A section)
- Modify: `app/web/templates/dashboard.html` (loading placeholder only)

**Interfaces:**
- Produces: DOM with `.dash-hero__top`, `.dash-hero__aside`, `.dash-hero__text`, `.dash-hero__rate-block`, `.dash-hero__actions`

- [ ] **Step 1: Restructure `zone_a_kpi.html` hero block**

```jinja
<section id="dash-zone-hero" class="dash-hero">
  <div class="dash-hero__top">
    <div class="dash-hero__text">
      <h1 class="dash-hero__title">오늘의 점검 현황</h1>
      <p class="dash-hero__meta">…</p>
      {# summary Jinja — unchanged priority #}
    </div>
    <div class="dash-hero__aside">
      <div class="dash-hero__rate-block">
        <span class="dash-hero__rate-label">통과율</span>
        <div class="dash-hero__rate-wrap">…</div>
      </div>
      <div class="dash-hero__actions">…refresh…</div>
    </div>
  </div>
</section>
```

- [ ] **Step 2: Replace hero CSS grid with flex (remove old `.dash-hero` grid rules)**

```css
#dash-host-kpi {
  min-height: clamp(7rem, 18cqh, 11rem);
  overflow: visible;
}

.dash-hero {
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.dash-hero__top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.dash-hero__text {
  flex: 1 1 12rem;
  min-width: 12rem;
}

.dash-hero__aside {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.35rem;
}

.dash-hero__title {
  overflow: visible;
}
```

- [ ] **Step 3: Delete obsolete rules** — old `grid-column` / `grid-row` on `dash-hero__text`, `dash-hero__rate-block`, `dash-hero__actions`; update `@media (max-width: 767px)` hero overrides to flex layout.

- [ ] **Step 4: Run fragment test**

```bash
python3 -m pytest tests/test_dashboard_fragments_http.py::test_fragments_include_visibility_wrappers -v
```

---

### Task 3: HF-2 — System card header + CSS

**Files:**
- Modify: `app/web/templates/dashboard/partials/_macros.html`
- Modify: `app/web/static/dashboard.css` (Zone C section)

- [ ] **Step 1: Wrap header in `system_row` macro**

```jinja
<div class="dash-sys-row" …>
  <div class="dash-sys-row__header">
    <div class="dash-sys-row__identity">…</div>
    <span class="dash-sys-row__badge" …>…</span>
    {% if show_cta %}<a class="dash-sys-row__cta" …>점검 실행</a>{% endif %}
    <span class="dash-sys-row__chevron" aria-hidden="true">›</span>
  </div>
  {{ module_segment_bar(sys) }}
  <div class="dash-sys-row__modules">…</div>
</div>
```

- [ ] **Step 2: Convert `.dash-sys-row` to flex column**

```css
.dash-sys-row {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  overflow: visible;
  /* remove grid-template-columns/rows */
}

.dash-sys-row__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 2.25rem;
  flex-shrink: 0;
}

.dash-sys-row__identity {
  flex: 1 1 auto;
  min-width: 8rem;
  max-width: 55%;
}

.dash-sys-row__chevron {
  margin-left: auto;
}

.dash-sys-row__modules {
  overflow: hidden;
}

.dash-sys-row__icon {
  min-width: 1.75rem;
  min-height: 1.75rem;
}

.dash-sys-row__name {
  min-width: 4ch;
}
```

- [ ] **Step 3: Remove grid placement rules** for `__identity`, `__badge`, `__cta`, `__chevron`, `__segment`, `__modules` (`grid-column`/`grid-row`). Keep segment/modules as block children.

- [ ] **Step 4: Update mobile `@media` card rules** — drop grid-template overrides; header flex unchanged.

- [ ] **Step 5: Run AC-002 + AC-005 tests**

```bash
python3 -m pytest tests/test_dashboard_viewport.py::test_system_identity_in_view_1280x720 tests/test_dashboard_fragments_http.py::test_fragments_include_visibility_wrappers -v
```

---

### Task 4: HF-3 — KPI stats grid CSS

**Files:**
- Modify: `app/web/static/dashboard.css` (`.dash-stats` section)

- [ ] **Step 1: Stats grid shrink fix**

```css
.dash-stats {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  width: 100%;
  min-width: 0;
}

.dash-stats__tile {
  min-width: 0;
  padding: clamp(0.35rem, 1cqh, 1rem) clamp(0.35rem, 1.5cqi, 0.75rem);
}

.dash-stats__label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 900px) {
  .dash-stats__value {
    font-size: max(1rem, clamp(1rem, 2cqh, 1.5rem));
  }
  .dash-stats__label {
    font-size: 0.6875rem;
  }
}
```

- [ ] **Step 2: Run AC-003 test**

```bash
python3 -m pytest tests/test_dashboard_viewport.py::test_all_four_kpi_tiles_in_dash_box -v
```

---

### Task 5: Cache bust + full automated suite

**Files:**
- Modify: `app/web/templates/dashboard.html`

- [ ] **Step 1: Bump CSS version**

```html
<link rel="stylesheet" href="/static/dashboard.css?v=3">
```

- [ ] **Step 2: Update hero placeholder skeleton** in `dashboard.html` `#dash-host-kpi` to include `dash-hero__top` / `dash-hero__aside` (avoid layout flash).

- [ ] **Step 3: Run full dashboard tests**

```bash
python3 -m pytest tests/test_dashboard_fragments_http.py tests/test_dashboard_viewport.py tests/test_daily_dashboard.py -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/web/templates/dashboard/partials/zone_a_kpi.html \
        app/web/templates/dashboard/partials/_macros.html \
        app/web/static/dashboard.css \
        app/web/templates/dashboard.html \
        tests/test_dashboard_viewport.py \
        tests/test_dashboard_fragments_http.py
git commit -m "fix(dashboard): SPEC-UI-006 visibility hotfix for hero, identity, KPI tiles"
```

---

### Task 6: Live E2E acceptance — `.agents/skills/e2e-browser`

**Skill:** Read and follow `.agents/skills/e2e-browser/SKILL.md` exactly.

**Prerequisite:** Dev server running:

```bash
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 2222
```

**Decision flow (copy to report):**

```text
E2E browser backend:
- [ ] Step A: Orca runtime reachable (`ORCA status --json`)
- [ ] Step B: Orca browser tab (`ORCA tab list --json` or `tab create --url http://127.0.0.1:2222/`)
- [ ] Step C: Interact via Orca snapshot loop
- [ ] Fallback: Playwright MCP only if A/B fail
```

#### 6.1 Setup

- [ ] **Resolve ORCA CLI** per e2e-browser skill (`ORCA_CLI_COMMAND` / `orca-dev` / `orca`).
- [ ] **Viewport:** Resize browser to **1280×720** (Orca: if supported via window API; else document target size in report).
- [ ] **Login:** Navigate to `http://127.0.0.1:2222/`, authenticate as non-admin user with all 6 systems (use existing test credentials or dev login).
- [ ] **Hard refresh** to bypass cache (`Ctrl+Shift+R` or append `?v=3` once).

#### 6.2 Manual checklist (maps to SPEC-UI-006 §7)

| ID | Check | Pass criteria |
| --- | --- | --- |
| **E2E-1** | Hero title | Snapshot/text contains `오늘의 점검 현황` left of `통과율` |
| **E2E-2** | Hero meta + summary | Date + `모듈 정상`; if all not inspected → `아직 점검이 시작되지 않았습니다` |
| **E2E-3** | KPI 4 tiles | All four labels visible: `이상징후`, `점검실패`, `진행 중`, `미점검` — **이상징후 not clipped** |
| **E2E-4** | System identity | First card shows code badge (e.g. `HOM`) + system name (e.g. `대표홈페이지`) |
| **E2E-5** | UI-005 regression | Segment bar, `점검 실행` CTA, `전체 보기`, Zone C scrollbar present |
| **E2E-6** | Document scroll | No page-level scrollbar; only Zone C scrolls if needed |

#### 6.3 Orca command sequence (when Orca available)

```bash
ORCA goto --url http://127.0.0.1:2222/ --json
ORCA snapshot --json
# Verify E2E-1..6 from snapshot text/refs
# Optional: ORCA screenshot for evidence
```

#### 6.4 Playwright MCP fallback (only if Orca unavailable)

Use `GetMcpTools` server `playwright`:

1. `browser_resize` → 1280×720
2. `browser_navigate` → `http://127.0.0.1:2222/`
3. `browser_snapshot` → verify checklist
4. `browser_take_screenshot` on failure

Report fallback reason verbatim per e2e-browser skill.

#### 6.5 E2E report artifact

Write: `.superpowers/sdd/2026-08-15-dashboard-visibility-hotfix/e2e-report.md`

```markdown
# SPEC-UI-006 E2E Report

- Backend: Orca browser | Playwright MCP
- Viewport: 1280×720
- URL: http://127.0.0.1:2222/

| Check | Result | Notes |
| E2E-1 | PASS/FAIL | |
| … | | |

## Evidence
- snapshot ref or screenshot path
```

- [ ] **Gate:** Task 6 is **not complete** until E2E-1..E2E-6 are PASS or documented FAIL with screenshot.

---

## Spec Coverage Self-Review

| Spec | Task |
| --- | --- |
| HF-1 hero flex | Task 2 |
| HF-2 card header | Task 3 |
| HF-3 stats minmax | Task 4 |
| AC-001~004 pytest | Task 1, 5 |
| AC-005 fragment | Task 1 |
| NFR-002 cache v=3 | Task 5 |
| Manual QA §7 | Task 6 (e2e-browser) |
| FR-004 regression | Task 6 E2E-5 |

---

## Suggested Commit Sequence

1. `test: add SPEC-UI-006 bounding-box visibility tests`
2. `fix(dashboard): hero flex layout for HF-1`
3. `fix(dashboard): system card header flex for HF-2`
4. `fix(dashboard): KPI stats grid shrink for HF-3`  
   *(or single commit as Task 5 suggests)*

---

## Execution Handoff

**Plan saved to `docs/superpowers/plans/2026-08-15-dashboard-visibility-hotfix.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** — Task 1 → 5 implementer, Task 6 E2E with e2e-browser skill
2. **Inline Execution** — same session, checkpoint after Task 5 before live E2E

**E2E reminder:** Task 6 is mandatory and must use `.agents/skills/e2e-browser` — not generic Playwright pytest for the manual acceptance gate.

Which approach do you want?
