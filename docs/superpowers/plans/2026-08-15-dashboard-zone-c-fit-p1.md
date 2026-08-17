# Dashboard Zone C Fit P1 Hotfix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix P1 defects blocking SPEC-UI-007 AC-002 — Zone C must fit inside the viewport without internal overflow (`scrollHeight <= clientHeight`), while preserving UI-005/006 visibility and accent styling.

**Architecture:** Single-pass density pipeline in `dashboard.js`: read computed CSS gap → pick tier from **content budget** (not row_h alone) → apply `data-density` → partition row heights → verify fit. Remove destructive inline styles on rows. Minor CSS tweaks so tier rules actually shrink content before overflow.

**Tech Stack:** CSS flex + density tier selectors, vanilla JS `ResizeObserver`, pytest + Playwright.

**Specs (no new spec — implement existing AC):**

| Spec | AC / FR | What P1 fixes |
| --- | --- | --- |
| `SPEC-UI-007` | AC-002, AC-003, FR-001~003 | Zone C `scrollHeight <= clientHeight`, equal partition |
| `SPEC-UI-005` | AC-009, FR-003 | Accent border-left on attention rows |
| `SPEC-UI-006` | FR-004 | No regression to hero/KPI/identity visibility |

**Trigger:** `test_dashboard_zone_c_fits_without_scroll` fails — `.dash__systems` `scrollHeight=650`, `clientHeight=501` at 1280×720 with 6 systems.

---

## Root Cause (confirmed)

| # | Issue | Mechanism |
| --- | --- | --- |
| **P1-A** | Tier from `row_h` only | At 1280×720, `row_h ≈ 77px` → `compact` tier still renders segment + header (`min-height: 2.25rem`) + chips → intrinsic content **taller than allocated row** |
| **P1-B** | Gap mismatch | `updateDashboardDensity` uses `DENSITY_GAP_PX = 8` fixed; CSS uses `gap: clamp(2px, 0.6cqh, 8px)`; tier vs partition use different gap values |
| **P1-C** | `borderWidth: "0"` | `syncRowPartition` inline style strips card border **and** `border-left` accent every resize/HTMX swap |
| **P1-D** | Tier applied after partition | `data-density` set before DOM reflow; CSS tier rules (hide segment, chip dots) may not apply before `scrollHeight` measured |

---

## Global Constraints

- **No new Spec** — behavior already defined in UI-007 §3.3–3.4, UI-005 §3.3.
- **No API / template logic changes** unless CSS hooks need a `data-*` attribute (prefer CSS-only).
- **No Zone C scroll** — `overflow: hidden` stays; fix is compression, not scrolling.
- **UI-006 DOM preserved** — `dash-sys-row__header`, hero `__top`/`__aside` untouched.
- **Cache bust:** `dashboard.js?v=17` (CSS change only if tier CSS adjusted → `dashboard.css?v=6`).
- **Verification:** `python -m pytest tests/test_dashboard_viewport.py -q` green + `run_all_gates.py --profile full`.

---

## File Map

| File | Action | Change |
| --- | --- | --- |
| `app/web/static/dashboard.js` | **Modify** | Content-aware tier; unified gap helper; fix `syncRowPartition`; optional fit verification loop |
| `app/web/static/dashboard.css` | **Modify** (small) | Tier row internal flex shrink; `compact` may hide segment earlier if needed |
| `app/web/templates/dashboard.html` | **Modify** | `dashboard.js?v=17` (+ `css?v=6` if CSS touched) |
| `tests/test_dashboard_viewport.py` | **Modify** | Stabilize wait for density sync before assert |

---

## Design — Content-Aware Density Pipeline

### Step 1: Unified gap helper

```javascript
function readContainerGapPx(container) {
  const style = getComputedStyle(container);
  return parseFloat(style.rowGap || style.gap) || 0;
}
```

Use **only** this in both tier selection and row partition (delete `DENSITY_GAP_PX` constant).

### Step 2: Tier content budget (per tier)

Estimate minimum row content height at each tier (constants in JS, mirror CSS):

| tier | segment | modules row | header | row gap + padding (approx) | **budget** |
| --- | --- | --- | --- | --- | --- |
| comfortable | 4px | 28px | 36px | ~24px | **~92px** |
| compact | 3px | 24px | 36px | ~20px | **~83px** |
| dense | 0 | 22px | 32px | ~16px | **~70px** |
| minimal | 0 | 10px (dots) | 32px | ~14px | **~56px** |
| micro | 0 | 10px | 28px | ~12px | **~50px** |

```javascript
const TIER_ORDER = ["comfortable", "compact", "dense", "minimal", "micro"];
const TIER_MIN_H = { comfortable: 92, compact: 83, dense: 70, minimal: 56, micro: 50 };

function pickTierForRowH(rowH) {
  // Largest tier whose budget fits in rowH (leave 2px slack)
  for (const tier of TIER_ORDER) {
    if (TIER_MIN_H[tier] <= rowH - 2) return tier;
  }
  return "micro";
}
```

`data-density` threshold bands (UI-007 §3.4 `row_h` labels) remain for CSS cosmetics; **selection** uses budget table above.

### Step 3: `updateDashboardDensity` flow

```text
1. container = #dash-zone-matrix, n = system count
2. gap = readContainerGapPx(container)
3. rowH = (container.clientHeight - gap * (n - 1)) / n
4. tier = pickTierForRowH(rowH)
5. container.dataset.density = tier
6. syncRowPartition(container, n, gap)   // use same gap
7. requestAnimationFrame → verify scrollHeight <= clientHeight
   - if fail && tier !== "micro": force tier down one step, goto 5 (max 4 retries)
8. syncKpiCompress(); syncAttentionCompact()
```

### Step 4: Fix `syncRowPartition`

**Remove:**
- `row.style.borderWidth = "0"`
- `row.style.animation = "none"` (prefer `@media (prefers-reduced-motion)` — optional cleanup)
- `row.style.transform = "none"` (breaks hover until hover again — remove)

**Keep:**
- `row.style.flex = \`0 0 ${rowClientH}px\``

**Optional:** use CSS custom property instead of inline flex:

```javascript
row.style.setProperty("--dash-row-h", `${rowClientH}px`);
```

```css
.dash-sys-row { flex: 0 0 var(--dash-row-h, 0); }
```

Prefer inline `flex` for minimal diff unless reviewer wants CSS variable.

### Step 5: CSS micro-adjustments (if budget table insufficient)

Only if tests still fail after JS tier fix:

- `.dash-sys-row__header { min-height: 0; flex-shrink: 1; }` at `dense`+ tiers
- `.dash-sys-row__modules { flex: 1 1 auto; min-height: 0; }` (already partially present)
- `compact` tier: hide segment when `row_h < 80px` — or rely on JS picking `dense` earlier

**Do not** reintroduce `overflow-y: auto` on `.dash__systems`.

---

## Task Breakdown

### Task 1: Reproduce & baseline

**Files:** none (read-only)

- [ ] **Step 1:** Run `python -m pytest tests/test_dashboard_viewport.py::test_dashboard_zone_c_fits_without_scroll -v` — confirm fail
- [ ] **Step 2:** Run `test_system_rows_equal_partition_1280x720` — note pass/fail (partition may pass while scrollHeight fails)
- [ ] **Step 3:** In browser devtools at 1280×720, log `rowH`, `data-density`, first row `scrollHeight` vs `clientHeight`

---

### Task 2: Fix `syncRowPartition` (P1-C) — quick win

**Files:**
- Modify: `app/web/static/dashboard.js`
- Modify: `app/web/templates/dashboard.html` (`js?v=17`)

- [ ] **Step 1:** Delete `row.style.borderWidth = "0"` and `row.style.transform = "none"` from `syncRowPartition`
- [ ] **Step 2:** Manual check — error system row shows 3px left accent after resize
- [ ] **Step 3:** Run `test_matrix_fragment_error_system_has_attention_priority` — still passes (DOM unchanged)

**Acceptance:** SPEC-UI-005 AC-009 visually restored; no inline border override.

---

### Task 3: Unified gap + content-aware tier (P1-A, P1-B)

**Files:**
- Modify: `app/web/static/dashboard.js`

- [ ] **Step 1:** Add `readContainerGapPx`, `TIER_MIN_H`, `pickTierForRowH`
- [ ] **Step 2:** Refactor `updateDashboardDensity` to use computed gap everywhere; remove `DENSITY_GAP_PX`
- [ ] **Step 3:** Set `dataset.density` **before** `syncRowPartition`
- [ ] **Step 4:** Add post-layout verify loop (rAF, tier downgrade if `scrollHeight > clientHeight + 1`)

**Acceptance:** At 1280×720 / 6 systems, `data-density` is `dense`, `minimal`, or `micro` (not `compact` when content overflows).

---

### Task 4: CSS tier shrink (only if Task 3 insufficient)

**Files:**
- Modify: `app/web/static/dashboard.css`
- Modify: `app/web/templates/dashboard.html` (`css?v=6`)

- [ ] **Step 1:** At `dense`+, reduce `.dash-sys-row__header { min-height: 1.75rem; }`
- [ ] **Step 2:** Ensure `.dash-sys-row__segment` hidden at `dense`+ (already in CSS — verify)
- [ ] **Step 3:** At `compact` with tight row_h, consider hiding segment via `.dash__systems[data-density="compact"] .dash-sys-row__segment { display: none }` **only if** budget table still insufficient

**Acceptance:** First `.dash-sys-row` `scrollHeight <= clientHeight` at worst-case viewport.

---

### Task 5: Stabilize Playwright tests (P1-D)

**Files:**
- Modify: `tests/test_dashboard_viewport.py`

- [ ] **Step 1:** Add helper `_wait_for_density_stable(page)`:

```python
def _wait_for_density_stable(page) -> None:
    page.wait_for_function(
        """() => {
            const sys = document.querySelector('.dash__systems');
            if (!sys || !sys.dataset.density) return false;
            return sys.scrollHeight <= sys.clientHeight + 1;
        }""",
        timeout=15000,
    )
```

- [ ] **Step 2:** Call after `wait_for_selector(".dash__systems")` in `test_dashboard_zone_c_fits_without_scroll` and `test_zone_c_no_internal_scroll_1280x720`
- [ ] **Step 3:** Deduplicate — both tests can share `_load_dashboard_1280x720(page, url)` helper

**Acceptance:** No flaky pass/fail split between two identical asserts.

---

### Task 6: Full verification

- [ ] **Step 1:** `python -m pytest tests/test_dashboard_viewport.py tests/test_dashboard_fragments_http.py -q`
- [ ] **Step 2:** `python -m pytest tests/test_daily_dashboard.py -q`
- [ ] **Step 3:** `python3 scripts/ci/run_all_gates.py --profile full`
- [ ] **Step 4 (manual):** 1280×720 Orca/e2e-browser — E2E-FIT-1~2 checklist; accent bar visible on HOM error card

---

## Acceptance Checklist (maps to Spec AC)

| Check | Spec | How to verify |
| --- | --- | --- |
| `.dash__systems` scrollHeight ≤ clientHeight | UI-007 AC-002 | Playwright `_assert_no_scroll` |
| Row heights equal ±2px, sum ≈ container | UI-007 AC-003 | `test_system_rows_equal_partition_1280x720` |
| Document no scroll | UI-007 AC-001 | existing viewport tests |
| No `data-scrollable` | UI-007 AC-007 | existing test |
| Attention row `border-left-width: 3px` | UI-005 AC-009 | fragment test + visual |
| Hero/KPI/identity in `.dash` box | UI-006 AC-001~003 | existing tests unchanged |
| Sidebar inset | UI-008 | existing tests unchanged |

---

## Out of Scope (P2+ — separate work)

- Hero meta `max(0.75rem, clamp(...))` typography
- `#dash-host-kpi { overflow: hidden }` → `visible` debate
- Missing AC: 3440×1440, resize density, `prefers-reduced-motion`
- Attention item click → drawer
- New SPEC or plan beyond this P1 hotfix

---

## Risk & Rollback

| Risk | Mitigation |
| --- | --- |
| Over-aggressive tier → UI too cramped at 1920×1080 | Budget table tuned so 1920×1080 stays `comfortable`/`compact`; add assert on `data-density` at 1080p |
| rAF retry loop infinite | Cap at 4 tier downgrades; log `console.warn` in dev only |
| Inline flex vs CSS variable | Start with inline flex (smaller diff); refactor later |

**Rollback:** Revert `dashboard.js` + version bump; CSS changes are additive and safe to keep.

---

## Estimated Effort

| Task | Time |
| --- | --- |
| Task 2 (border fix) | 15 min |
| Task 3 (tier pipeline) | 45–60 min |
| Task 4 (CSS, if needed) | 20–30 min |
| Task 5 (test stability) | 15 min |
| Task 6 (CI) | 15 min |
| **Total** | **~2 hours** |

---

## Change Log

| Date | Author | Note |
| --- | --- | --- |
| 2026-08-15 | AI | P1 hotfix plan — Zone C fit + border regression |
