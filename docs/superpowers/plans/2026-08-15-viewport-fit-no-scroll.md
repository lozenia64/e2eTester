# Dashboard Viewport-Fit No-Scroll (SPEC-UI-007) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the product intent — **no scroll anywhere**; all dashboard content compresses to fit inside the viewport via equal row partition + density tiers (UI-006 visibility preserved).

**Architecture:** Revert UI-005/006 Zone C scroll model. CSS: `.dash__systems { overflow: hidden }`, `.dash-sys-row { flex: 1 1 0 }`. JS: density from `row_h = container.clientHeight / N` (not `ROW_MIN_H` budget). KPI host: remove `min-height`, add `max-height: 42%` + optional `data-kpi-compress`. Tests: replace AC that asserted `overflow-y: auto` with AC-002/003/007. Live E2E via `.agents/skills/e2e-browser`.

**Tech Stack:** CSS flex, vanilla JS `ResizeObserver`, pytest + Playwright, Orca browser / Playwright MCP (e2e-browser skill).

**Spec:** `docs/specs/dashboard/07-viewport-fit-no-scroll.md`

## Global Constraints

- **Zero scrollbar:** No `overflow: auto|scroll` on `.dash` descendants (drawer panel `position:fixed` excluded).
- **Partition:** Zone C rows `flex: 1 1 0`; N systems fill 100% of Zone C height.
- **Compress, don’t scroll:** tier downgrade + hide segment (dense+) + chip dots (minimal+) — never scroll.
- **UI-006 visibility preserved:** hero flex DOM, `dash-sys-row__header`, KPI 4 tiles, system name never `display:none`.
- **API/JS scope:** Only `dashboard.js` density/KPI-compress logic; no `daily_dashboard.py`.
- **Cache bust:** `dashboard.css?v=4`, `dashboard.js?v=16`.
- **E2E gate:** Task 5 MUST follow `.agents/skills/e2e-browser/SKILL.md` (Orca first → Playwright MCP fallback).

---

## File Map

| File | Action | Change |
| --- | --- | --- |
| `app/web/static/dashboard.css` | **Modify** | Remove scroll/mask/min-h rows; equal flex; KPI max-height; dense segment hide; micro summary hide |
| `app/web/static/dashboard.js` | **Modify** | row_h tier; remove scrollable; add `syncKpiCompress()` |
| `app/web/templates/dashboard.html` | **Modify** | `css?v=4`, `js?v=16` |
| `tests/test_dashboard_viewport.py` | **Modify** | AC-002/003/007 add; **fix** `test_dashboard_zone_c_internal_scroll_*` → asserts `hidden` |
| `zone_a_kpi.html` | **Verify** | No change unless KPI compress needs hook on `#dash-host-kpi` |

---

### Task 1: Tests first — AC-002, AC-003, AC-007 + fix conflicting test

**Files:**
- Modify: `tests/test_dashboard_viewport.py`

**Interfaces:**
- Produces: failing tests tagged `@pytest.mark.spec("SPEC-UI-007", ...)`

- [ ] **Step 1: Add helper `assert_no_scroll_el(page, selector)`**

```python
def _assert_no_scroll(page, selector: str) -> None:
    result = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return { ok: false, reason: 'missing' };
            const oy = getComputedStyle(el).overflowY;
            return {
                ok: el.scrollHeight <= el.clientHeight + 1 && oy !== 'auto' && oy !== 'scroll',
                scrollHeight: el.scrollHeight,
                clientHeight: el.clientHeight,
                overflowY: oy,
            };
        }""",
        selector,
    )
    assert result["ok"], f"{selector}: {result}"
```

- [ ] **Step 2: Add AC-002 Zone C no scroll**

```python
@pytest.mark.spec("SPEC-UI-007", "AC-002")
def test_zone_c_no_internal_scroll_1280x720(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash__systems")
    _assert_no_scroll(page, ".dash__systems")
    has_scrollable = page.evaluate(
        "() => document.querySelector('.dash__systems')?.dataset.scrollable"
    )
    assert has_scrollable in (None, "", "false")
```

- [ ] **Step 3: Add AC-003 equal row heights**

```python
@pytest.mark.spec("SPEC-UI-007", "AC-003")
def test_system_rows_equal_partition_1280x720(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-sys-row")
    metrics = page.evaluate(
        """() => {
            const rows = [...document.querySelectorAll('.dash-sys-row')];
            const heights = rows.map((r) => r.clientHeight);
            const sys = document.querySelector('.dash__systems');
            const gap = parseFloat(getComputedStyle(sys).rowGap || getComputedStyle(sys).gap) || 0;
            const sum = heights.reduce((a, b) => a + b, 0) + gap * Math.max(0, heights.length - 1);
            return {
                heights,
                spread: Math.max(...heights) - Math.min(...heights),
                sum,
                container: sys.clientHeight,
            };
        }"""
    )
    assert metrics["spread"] <= 2, metrics
    assert abs(metrics["sum"] - metrics["container"]) <= 4, metrics
```

- [ ] **Step 4: Add AC-007 no data-scrollable**

```python
@pytest.mark.spec("SPEC-UI-007", "AC-007")
@pytest.mark.parametrize("width,height", [(1280, 720), (1920, 1080), (320, 568)])
def test_no_data_scrollable_dataset(page, live_server: str, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{live_server}/")
    page.wait_for_selector("#dash-zone-matrix")
    assert page.evaluate(
        "() => !document.querySelector('.dash__systems')?.hasAttribute('data-scrollable')"
        " || document.querySelector('.dash__systems').dataset.scrollable === 'false'"
    )
```

- [ ] **Step 5: Replace `test_dashboard_zone_c_internal_scroll_document_fixed`**

Current test asserts `overflowY === "auto"` (UI-005). **Delete or rewrite:**

```python
@pytest.mark.spec("SPEC-UI-007", "AC-002")
def test_dashboard_zone_c_fits_without_scroll(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash__systems")
    _assert_no_scroll(page, ".dash__systems")
    doc = page.evaluate(
        "() => ({ sh: document.documentElement.scrollHeight, ih: window.innerHeight })"
    )
    assert doc["sh"] <= doc["ih"]
```

- [ ] **Step 6: Run new tests — expect FAIL**

```bash
python3 -m pytest tests/test_dashboard_viewport.py -v -k "UI-007 or zone_c_fits or equal_partition"
```

---

### Task 2: CSS — Zone C equal partition, remove scroll

**Files:**
- Modify: `app/web/static/dashboard.css` (~lines 379–420, 653–657, 391–393)

- [ ] **Step 1: `.dash__systems` — hidden only**

```css
.dash__systems {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: clamp(2px, 0.6cqh, 8px);
  overflow: hidden;
}
```

Delete blocks:
- `.dash__systems[data-scrollable="true"] { mask-image: ... }`
- `overflow-y: auto`, `-webkit-overflow-scrolling`, `scrollbar-gutter`

- [ ] **Step 2: `.dash-sys-row` — equal flex**

```css
.dash-sys-row {
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
  /* keep flex column + header structure from UI-006 */
}
```

Delete:
- `flex: 0 0 auto`
- `min-height: var(--dash-row-min-h, ...)`
- `.dash__systems[data-density="comfortable"] { --dash-row-min-h: ... }` through `micro` (all 5 rules)

- [ ] **Step 3: `.dash-sys-row__modules` — clip only**

```css
.dash-sys-row__modules {
  overflow: hidden;
  flex: 1 1 auto;
  min-height: 0;
}
```

- [ ] **Step 4: Segment hide at dense+ (spec §3.4)**

Ensure existing rules cover dense — add if missing:

```css
.dash__systems[data-density="dense"] .dash-sys-row__segment,
.dash__systems[data-density="minimal"] .dash-sys-row__segment,
.dash__systems[data-density="micro"] .dash-sys-row__segment {
  display: none;
}
```

- [ ] **Step 5: Micro CTA/summary (spec §3.4)**

```css
.dash:has(.dash__systems[data-density="micro"]) .dash-hero__summary {
  display: none;
}

.dash__systems[data-density="micro"] .dash-sys-row__cta {
  font-size: 0;
}
.dash__systems[data-density="micro"] .dash-sys-row__cta::after {
  content: "점검";
  font-size: 0.75rem;
}
```

- [ ] **Step 6: Run AC-003 test — still may fail until JS tier uses clientHeight**

---

### Task 3: CSS — KPI host budget (hero clip fix)

**Files:**
- Modify: `app/web/static/dashboard.css` `#dash-host-kpi` block

- [ ] **Step 1: Replace min-height with max-height + compress**

```css
#dash-host-kpi {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: clamp(0.25rem, 0.6cqh, 0.625rem);
  overflow: hidden;
  max-height: 42%;
}

#dash-host-kpi[data-kpi-compress="true"] {
  gap: 0.25rem;
}

#dash-host-kpi[data-kpi-compress="true"] .dash-hero__title {
  font-size: max(1rem, 1rem);
}

#dash-host-kpi[data-kpi-compress="true"] .dash-stats__tile {
  min-height: 44px;
  padding-top: 0.35rem;
  padding-bottom: 0.35rem;
}
```

Remove: `min-height: clamp(7rem, 18cqh, 11rem);`

- [ ] **Step 2: Re-run UI-006 visibility tests**

```bash
python3 -m pytest tests/test_dashboard_viewport.py -v -k "hero_title or four_kpi or hero_visible"
```

---

### Task 4: JS — row_h density + KPI compress

**Files:**
- Modify: `app/web/static/dashboard.js`

**Interfaces:**
- Produces: `computeDensityTierFromRowH(rowH) -> string`
- Produces: `syncKpiCompress()` sets `#dash-host-kpi[data-kpi-compress]`

- [ ] **Step 1: Replace density algorithm**

```javascript
const DENSITY_GAP_PX = 8;

function computeDensityTierFromRowH(rowH) {
  if (rowH >= 72) return "comfortable";
  if (rowH >= 56) return "compact";
  if (rowH >= 44) return "dense";
  if (rowH >= 32) return "minimal";
  return "micro";
}

function updateDashboardDensity() {
  const container = $("#dash-zone-matrix", root);
  if (!container) return;

  const n =
    Number(container.dataset.systemCount) ||
    container.querySelectorAll(".dash-sys-row").length ||
    1;
  const gap = DENSITY_GAP_PX * Math.max(0, n - 1);
  const rowH = (container.clientHeight - gap) / Math.max(n, 1);
  container.dataset.density = computeDensityTierFromRowH(rowH);

  delete container.dataset.scrollable;
  syncKpiCompress();
  syncAttentionCompact();
}

function syncKpiCompress() {
  const kpi = $("#dash-host-kpi", root);
  if (!kpi) return;
  const limit = root.clientHeight * 0.42;
  kpi.dataset.kpiCompress = kpi.offsetHeight > limit ? "true" : "false";
}
```

- [ ] **Step 2: Delete dead code**

Remove: `ROW_MIN_H`, `TIER_ORDER`, `computeDensityTier(zoneCAvail, ...)`, `measureZoneCAvail()`, scrollable logic.

- [ ] **Step 3: Observe `#dash-zone-matrix` or `.dash__systems` for row_h**

`bindDensityObserver` should observe `#dash-host-matrix` (unchanged) — `updateDashboardDensity` uses `container.clientHeight` after flex layout.

Also call `syncKpiCompress()` on KPI fragment swap in `onAfterSwap`.

- [ ] **Step 4: Run all viewport tests**

```bash
python3 -m pytest tests/test_dashboard_viewport.py -q
```

Expected: all pass including UI-007.

---

### Task 5: Cache bust + full suite + E2E (e2e-browser skill)

**Files:**
- Modify: `app/web/templates/dashboard.html`
- Create: `.superpowers/sdd/2026-08-15-viewport-fit-no-scroll/e2e-report.md`

**Skill:** Read `.agents/skills/e2e-browser/SKILL.md` before starting.

- [ ] **Step 1: Bump versions in `dashboard.html`**

```html
<link rel="stylesheet" href="/static/dashboard.css?v=4">
<script src="/static/dashboard.js?v=16" defer></script>
```

- [ ] **Step 2: Run pytest suite**

```bash
python3 -m pytest tests/test_dashboard_fragments_http.py tests/test_dashboard_viewport.py tests/test_daily_dashboard.py -q
```

- [ ] **Step 3: E2E — e2e-browser decision flow**

```text
- [ ] Step A: ORCA status --json (or fallback note)
- [ ] Step B: tab create http://127.0.0.1:2222/ OR ephemeral test server
- [ ] Step C: snapshot at 1280×720
- [ ] Fallback: Playwright MCP if Orca unavailable
```

**Checklist (SPEC-UI-007 §9.1):**

| ID | Check |
| --- | --- |
| E2E-FIT-1 | No scrollbar on page AND `.dash__systems` |
| E2E-FIT-2 | All 6 system cards visible without scrolling |
| E2E-FIT-3 | Hero title + 통과율 + 4 KPI tiles |
| E2E-FIT-4 | Each card: icon + system name |
| E2E-FIT-5 | Resize height 50% — no scroll, `data-density` changes |

**Playwright MCP evaluate for E2E-FIT-1:**

```javascript
() => {
  const sys = document.querySelector('.dash__systems');
  const docOk = document.documentElement.scrollHeight <= window.innerHeight;
  const zoneOk = sys && sys.scrollHeight <= sys.clientHeight + 1
    && getComputedStyle(sys).overflowY === 'hidden';
  return { docOk, zoneOk };
}
```

- [ ] **Step 4: Write `e2e-report.md` with backend used + pass/fail table + screenshot path**

- [ ] **Step 5: Commit**

```bash
git add app/web/static/dashboard.css app/web/static/dashboard.js \
        app/web/templates/dashboard.html tests/test_dashboard_viewport.py
git commit -m "fix(dashboard): SPEC-UI-007 viewport-fit no-scroll (compress, don't scroll)"
```

---

## Spec Coverage Self-Review

| Spec | Task |
| --- | --- |
| FR-001 zero scrollbar | Task 2, 4, 5 E2E-FIT-1 |
| FR-002 equal partition | Task 2, 4, Task 1 AC-003 |
| FR-003 compress ladder | Task 2 segment/summary/CTA rules |
| FR-004 visibility | Task 3, existing UI-006 tests |
| AC-001 document no-scroll | Existing + Task 5 |
| AC-002 Zone C | Task 1, 2 |
| AC-003 equal rows | Task 1, 2 |
| AC-004~005 visibility | Existing UI-006 tests (regression) |
| AC-006 resize tier | Manual E2E-FIT-5 or add test |
| AC-007 no data-scrollable | Task 1, 4 |
| NFR-003 e2e-browser | Task 5 |

---

## Migration Notes (for implementer)

| Current (UI-006) | Target (UI-007) |
| --- | --- |
| `.dash__systems { overflow-y: auto }` | `overflow: hidden` |
| `.dash-sys-row { flex: 0 0 auto; min-height: var(--dash-row-min-h) }` | `flex: 1 1 0; min-height: 0` |
| JS `ROW_MIN_H` budget tier | `rowH = clientHeight / N` tier |
| `dataset.scrollable` | removed |
| `#dash-host-kpi min-height: 7rem` | `max-height: 42%` + compress |
| Test asserts `overflowY === 'auto'` | asserts `hidden` |

---

## Suggested Commit Sequence

1. `test: add SPEC-UI-007 no-scroll and equal-partition ACs`
2. `fix(dashboard): restore viewport-fit partition and remove Zone C scroll`
3. `test(dashboard): SPEC-UI-007 e2e-report` (optional — report only)

---

## Execution Handoff

**Plan saved to `docs/superpowers/plans/2026-08-15-viewport-fit-no-scroll.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** — Tasks 1→5 sequential subagents
2. **Inline Execution** — same session with checkpoint after Task 4

Which approach do you want?
