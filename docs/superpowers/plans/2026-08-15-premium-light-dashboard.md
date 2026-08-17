# Premium Light Dashboard Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the daily inspection dashboard (`GET /`) with a Premium Light card-list UI that fits every viewport without horizontal or vertical scroll.

**Architecture:** Keep existing HTMX fragment refresh (`/api/dashboard/daily/fragments/{zone}`) and `daily_dashboard.py` aggregation unchanged. Extract styles to `dashboard.css`, replace Cytoscape matrix with server-rendered system card rows in `zone_b_matrix.html`, and use `ResizeObserver` in `dashboard.js` to set `data-density` tiers (`comfortable` → `micro`) so content compresses instead of scrolling.

**Tech Stack:** Jinja2 partials, HTMX 2.x, Alpine 3.x (drawer only), vanilla JS, CSS container queries (`cqh`/`cqi`), pytest + Playwright (viewport AC).

**Spec:** `docs/specs/dashboard/04-premium-light-redesign.md`

## Global Constraints

- **No scroll ever:** `document.documentElement.scrollHeight <= innerHeight` and `scrollWidth <= innerWidth` at `320×568`, `390×844`, `1280×720`, `1920×1080`.
- **API frozen:** Do not change `/api/dashboard/daily` JSON shape or `daily_dashboard.py` aggregation rules.
- **Korean UI copy:** Title = `오늘의 점검 현황`; remove English eyebrow `Daily Inspection`.
- **Cytoscape removed:** No `cytoscape` / `cytoscape-node-html-label` script tags on dashboard.
- **Status palette:** `--st-passed:#10b981`, `--st-anomaly:#f59e0b`, `--st-error:#ef4444`, `--st-running:#3b82f6`, `--st-idle:#a1a1aa`.
- **Density tiers:** `comfortable` (row_h≥72), `compact` (≥56), `dense` (≥44), `minimal` (≥32), `micro` (<32).
- **Attention strip:** Show only when `data.attention` non-empty AND remaining vertical space ≥ 80px after Zone A+B; max 3 rows + `+N건`.
- **`prefers-reduced-motion`:** Disable count-up and pulse animations.

---

## File Map

| File | Action | Responsibility |
| --- | --- | --- |
| `app/web/static/dashboard.css` | **Create** | Design tokens, viewport shell, zones, cards, density tiers, drawer |
| `app/web/templates/dashboard.html` | **Rewrite** | Shell markup, link CSS, remove inline styles + Cytoscape scripts |
| `app/web/templates/dashboard/partials/zone_a_kpi.html` | **Rewrite** | Zone A hero + Zone B stats + optional attention strip |
| `app/web/templates/dashboard/partials/zone_b_matrix.html` | **Rewrite** | Zone C system card list (replaces Cytoscape) |
| `app/web/templates/dashboard/partials/system_panel.html` | **Modify** | Premium Light drawer styling |
| `app/web/templates/dashboard/partials/_macros.html` | **Create** | Jinja macros: `system_badge`, `module_pill` |
| `app/contexts/insights/application/daily_dashboard.py` | **Modify** | Add `system_summary_badge(system_view) -> dict` pure helper |
| `app/web/static/dashboard.js` | **Rewrite** | Density observer, count-up, HTMX hooks, drawer; remove Cytoscape |
| `tests/test_daily_dashboard.py` | **Modify** | Unit tests for `system_summary_badge` |
| `tests/test_dashboard_fragments_http.py` | **Create** | Fragment HTML contract tests |
| `tests/test_dashboard_viewport.py` | **Create** | Playwright no-scroll tests (4 viewports) |
| `docs/specs/dashboard/01-daily-dashboard.md` | **Modify** | Add pointer to SPEC-UI-004 for UI |

---

### Task 1: `system_summary_badge` pure helper

**Files:**
- Modify: `app/contexts/insights/application/daily_dashboard.py`
- Test: `tests/test_daily_dashboard.py`

**Interfaces:**
- Produces: `system_summary_badge(system_view: dict) -> dict` with keys `label: str`, `tone: str`

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.spec("SPEC-UI-004", "AC-006")
def test_system_summary_badge_error_wins():
    view = {
        "counts": {
            "error": 1,
            "anomaly": 2,
            "running": 1,
            "other": 0,
            "not_inspected": 0,
            "passed": 0,
        },
        "module_total": 4,
    }
    badge = system_summary_badge(view)
    assert badge == {"label": "점검실패", "tone": "error"}


@pytest.mark.spec("SPEC-UI-004", "AC-006")
def test_system_summary_badge_all_passed():
    view = {
        "counts": {
            "error": 0,
            "anomaly": 0,
            "running": 0,
            "other": 0,
            "not_inspected": 0,
            "passed": 4,
        },
        "module_total": 4,
    }
    badge = system_summary_badge(view)
    assert badge == {"label": "정상", "tone": "passed"}
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python3 -m pytest tests/test_daily_dashboard.py::test_system_summary_badge_error_wins -v`

- [ ] **Step 3: Implement helper**

```python
def system_summary_badge(system_view: dict[str, Any]) -> dict[str, str]:
    counts = system_view.get("counts") or {}
    total = system_view.get("module_total") or 0
    if counts.get("error", 0) > 0:
        return {"label": "점검실패", "tone": "error"}
    if counts.get("anomaly", 0) > 0:
        return {"label": "이상징후", "tone": "anomaly"}
    if counts.get("running", 0) > 0:
        return {"label": "진행 중", "tone": "running"}
    if counts.get("other", 0) > 0:
        return {"label": "주의", "tone": "blocked"}
    if counts.get("not_inspected", 0) > 0:
        return {"label": "미점검", "tone": "not_inspected"}
    if total > 0 and counts.get("passed", 0) == total:
        return {"label": "정상", "tone": "passed"}
    return {"label": "미점검", "tone": "not_inspected"}
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python3 -m pytest tests/test_daily_dashboard.py -q`

---

### Task 2: Jinja macros + Zone C card list partial

**Files:**
- Create: `app/web/templates/dashboard/partials/_macros.html`
- Modify: `app/web/templates/dashboard/partials/zone_b_matrix.html`

**Interfaces:**
- Consumes: `system_summary_badge` via template global or import in route (register in `routes_daily.py`: `templates.env.globals["system_summary_badge"] = system_summary_badge`)
- Produces: HTML with `#dash-zone-matrix`, `.dash__systems`, `.dash-sys-row` per system

- [ ] **Step 1: Register Jinja global in `app/api/routes_daily.py`**

```python
from app.contexts.insights.application.daily_dashboard import system_summary_badge

templates.env.globals["system_summary_badge"] = system_summary_badge
```

- [ ] **Step 2: Create `_macros.html`**

Macros:
- `module_pill(mod)` — renders `<span class="dash-mod" data-tone="...">` with `title` tooltip; if `mod.run_id`, wrap in `<a href="/runs/...">` with `@click.stop` handled in JS
- `system_row(sys)` — 3-col grid: identity (code icon + name + `inspected/module_total`), modules loop, badge from `system_summary_badge(sys)`

- [ ] **Step 3: Rewrite `zone_b_matrix.html`**

```jinja2
{% from "dashboard/partials/_macros.html" import system_row %}
<div id="dash-zone-matrix" class="dash__systems" data-system-count="{{ data.systems|length }}">
  {% if not data.systems %}
  <p class="dash__empty">표시할 시스템이 없습니다.</p>
  {% else %}
  {% for sys in data.systems %}
  {{ system_row(sys) }}
  {% endfor %}
  {% endif %}
</div>
```

Each row: `class="dash-sys-row"`, `data-system-code`, `tabindex="0"`, `role="button"`.

- [ ] **Step 4: Manual smoke — fragment renders**

Run server, `GET /api/dashboard/daily/fragments/matrix` (authenticated) → HTML contains `dash-sys-row`, no `dash-matrix-chart`, no `cytoscape`.

---

### Task 3: Zone A hero + Zone B stats partial

**Files:**
- Modify: `app/web/templates/dashboard/partials/zone_a_kpi.html`

**Interfaces:**
- Produces: `#dash-zone-hero`, `#dash-zone-stats`, optional `#dash-zone-attention`

- [ ] **Step 1: Rewrite partial structure**

```jinja2
{% set t = data.totals %}
<section id="dash-zone-hero" class="dash-hero">
  <div class="dash-hero__text">
    <h1 class="dash-hero__title">오늘의 점검 현황</h1>
    <p class="dash-hero__meta">{{ data.date_label }} · {{ t.passed }}/{{ t.modules }} 모듈 정상</p>
  </div>
  <div class="dash-hero__rate-wrap">
    <span class="dash-hero__rate" data-target="{{ t.pass_rate }}">{{ t.pass_rate }}</span><span class="dash-hero__pct">%</span>
  </div>
  <button id="dash-refresh" type="button" class="dash-refresh">새로고침</button>
</section>

<section id="dash-zone-stats" class="dash-stats">
  <!-- 4 tiles: anomaly, error, running, not_inspected -->
</section>

{% if data.attention %}
<section id="dash-zone-attention" class="dash-attention is-collapsible" hidden>
  <!-- max 3 items + overflow badge; JS toggles hidden based on free space -->
</section>
{% endif %}
```

- [ ] **Step 2: Verify fragment**

`GET /api/dashboard/daily/fragments/kpi` → contains `dash-hero__title` with Korean copy, no `dash-kpi-strip`.

---

### Task 4: `dashboard.css` — viewport shell + Premium Light + density tiers

**Files:**
- Create: `app/web/static/dashboard.css`

**Interfaces:**
- Consumes: class names from Tasks 2–3
- Produces: CSS that makes `.dash` fill viewport with `overflow: hidden` at all breakpoints

- [ ] **Step 1: Viewport shell (spec §3.1)**

```css
body:has(.dash) { overflow: hidden; }
body:has(.dash) main,
body:has(.dash) main > div {
  max-width: none;
  padding: 0;
  height: 100dvh;
  overflow: hidden;
}
@media (max-width: 767px) {
  body:has(.dash) main,
  body:has(.dash) main > div {
    height: calc(100dvh - 3.25rem);
  }
}

.dash {
  container-type: size;
  container-name: dash;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: clamp(0.5rem, 1.5cqh, 1.5rem) clamp(0.75rem, 2cqi, 2rem);
  background: #fafafa;
}
.dash__systems {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: clamp(2px, 0.6cqh, 8px);
  overflow: hidden;
}
.dash-sys-row {
  flex: 1 1 0;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(7rem, 14rem) 1fr auto;
  align-items: center;
  gap: 0.75rem;
  padding: clamp(0.35rem, 1cqh, 0.875rem) clamp(0.5rem, 1.5cqi, 1.25rem);
  background: #fff;
  border: 1px solid #e4e4e7;
  border-radius: 1rem;
  overflow: hidden;
}
```

- [ ] **Step 2: Density tier rules**

```css
.dash__systems[data-density="compact"] .dash-sys-row { padding: 0.35rem 0.75rem; }
.dash__systems[data-density="dense"] .dash-mod__label { max-width: 5ch; overflow: hidden; text-overflow: ellipsis; }
.dash__systems[data-density="minimal"] .dash-mod__label { display: none; }
.dash__systems[data-density="minimal"] .dash-mod { width: 10px; height: 10px; padding: 0; border-radius: 50%; }
.dash__systems[data-density="micro"] .dash-sys-row__name { display: none; }
.dash__systems[data-density="micro"] .dash-attention { display: none !important; }
```

- [ ] **Step 3: Mobile card internal stack (`@media max-width: 767px`)**

```css
@media (max-width: 767px) {
  .dash-sys-row {
    grid-template-columns: 1fr auto;
    grid-template-rows: auto auto;
  }
  .dash-sys-row__identity { grid-column: 1; }
  .dash-sys-row__badge { grid-column: 2; grid-row: 1; }
  .dash-sys-row__modules { grid-column: 1 / -1; }
}
```

No `flex-wrap` on modules row — `overflow: hidden` only.

- [ ] **Step 4: Hero, stats, drawer, motion tokens** per spec §2.

---

### Task 5: `dashboard.html` shell rewrite

**Files:**
- Modify: `app/web/templates/dashboard.html`

- [ ] **Step 1: Replace content block**

Structure:

```html
<link rel="stylesheet" href="/static/dashboard.css?v=1">
<div class="dash" x-data="{ drawerOpen: false }" ...>
  <div id="dash-host-kpi" hx-get="..." hx-trigger="load, dash-refresh from:body" ...></div>
  <div id="dash-host-matrix" class="dash-host-matrix" hx-get="..." ...></div>
  <div id="dash-error" class="hidden">...</div>
  <div class="dash-drawer" x-show="drawerOpen" ...>...</div>
</div>
```

Remove: all inline `<style>`, cytoscape script tags, legend pills (status conveyed by cards), `#dash-date` separate span (date in hero).

- [ ] **Step 2: Scripts block**

```html
<script src="https://unpkg.com/htmx.org@2.0.4" defer></script>
<script src="https://unpkg.com/alpinejs@3.14.8/dist/cdn.min.js" defer></script>
<script src="/static/dashboard.js?v=14" defer></script>
```

- [ ] **Step 3: Verify page loads without 404 on `dashboard.css`**

---

### Task 6: `dashboard.js` rewrite

**Files:**
- Modify: `app/web/static/dashboard.js`

**Interfaces:**
- Consumes: `#dash__systems` or `#dash-zone-matrix`, `data-system-count`
- Produces: `computeDensityTier(rowH) -> string`, `updateDashboardDensity()`, `animateCountUp(el, target)`

- [ ] **Step 1: Delete all Cytoscape code** (`buildElements`, `renderMatrixFromPayload`, `matrixCy`, cytoscape imports)

- [ ] **Step 2: Implement density module**

```javascript
const DENSITY_GAP_PX = 8;

export function computeDensityTier(rowH) {
  if (rowH >= 72) return "comfortable";
  if (rowH >= 56) return "compact";
  if (rowH >= 44) return "dense";
  if (rowH >= 32) return "minimal";
  return "micro";
}

function updateDashboardDensity() {
  const container = document.getElementById("dash-zone-matrix");
  if (!container) return;
  const n = Number(container.dataset.systemCount || container.querySelectorAll(".dash-sys-row").length) || 1;
  const h = container.clientHeight;
  const gap = DENSITY_GAP_PX * Math.max(0, n - 1);
  const rowH = (h - gap) / n;
  container.dataset.density = computeDensityTier(rowH);
  // attention strip: show if container.parentElement has enough room
  toggleAttentionStrip();
}
```

Wire `ResizeObserver` on `#dash-host-matrix` and window `resize`. Call after each HTMX `afterSwap` on matrix/kpi zones.

- [ ] **Step 3: Interactions**

- Row click → `openDrawer(systemCode)` (existing HTMX ajax pattern)
- Module link click → `event.stopPropagation()` via delegated listener on `.dash-mod--link`
- Count-up on `.dash-hero__rate[data-target]` when not reduced-motion
- Refresh button → dispatch `dash-refresh` (remove separate `loadDateLabel` fetch — date comes from kpi fragment)

- [ ] **Step 4: Attention strip visibility**

```javascript
function toggleAttentionStrip() {
  const strip = document.getElementById("dash-zone-attention");
  if (!strip) return;
  const dash = document.querySelector(".dash");
  const used = /* sum offsetHeights of hero + stats */;
  const free = dash.clientHeight - used;
  strip.hidden = free < 80;
}
```

---

### Task 7: Drawer panel Premium Light styling

**Files:**
- Modify: `app/web/templates/dashboard/partials/system_panel.html`

- [ ] **Step 1: Update classes** to use `dash-panel` styles from `dashboard.css` (white surface, `#e4e4e7` borders, tone dots unchanged)

- [ ] **Step 2: Smoke test** — click system row → drawer shows module list

---

### Task 8: HTTP fragment contract tests

**Files:**
- Create: `tests/test_dashboard_fragments_http.py`

- [ ] **Step 1: Write tests with FastAPI TestClient + fake `DailyDashboardQueries`**

```python
@pytest.mark.spec("SPEC-UI-004", "AC-005")
def test_matrix_fragment_renders_card_rows(client):
    res = client.get("/api/dashboard/daily/fragments/matrix")
    assert res.status_code == 200
    assert "dash-sys-row" in res.text
    assert "cytoscape" not in res.text
    assert "dash-matrix-chart" not in res.text


@pytest.mark.spec("SPEC-UI-004", "AC-006")
def test_kpi_fragment_renders_hero(client):
    res = client.get("/api/dashboard/daily/fragments/kpi")
    assert "오늘의 점검 현황" in res.text
    assert "dash-hero__rate" in res.text
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/test_dashboard_fragments_http.py -q`

---

### Task 9: Playwright viewport no-scroll tests

**Files:**
- Create: `tests/test_dashboard_viewport.py`

**Interfaces:**
- Consumes: live app on `127.0.0.1` ephemeral port with seeded user + 6-system dashboard data

- [ ] **Step 1: Add `live_server` pytest fixture** (thread + uvicorn on port 0, or use existing `scripts/run_local.py` pattern)

Fixture seeds:
- User `user@test.local` / password via in-memory auth OR mock `get_current_user` dependency on test app mounting full routes

- [ ] **Step 2: Write viewport tests**

```python
VIEWPORTS = [(320, 568), (390, 844), (1280, 720), (1920, 1080)]


@pytest.mark.spec("SPEC-UI-004", "AC-001")
@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_dashboard_no_scroll(page, live_server, width, height):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-sys-row")
    metrics = page.evaluate("""() => ({
      sh: document.documentElement.scrollHeight,
      ih: window.innerHeight,
      sw: document.documentElement.scrollWidth,
      iw: window.innerWidth,
    })""")
    assert metrics["sh"] <= metrics["ih"]
    assert metrics["sw"] <= metrics["iw"]
```

Mark with `@pytest.mark.browser` if CI should skip without chromium — document in test docstring. Run `playwright install chromium` in dev setup.

- [ ] **Step 3: Run tests locally**

Run: `python3 -m pytest tests/test_dashboard_viewport.py -v`

---

### Task 10: Docs + CI verification

**Files:**
- Modify: `docs/specs/dashboard/01-daily-dashboard.md`
- Modify: `docs/specs/dashboard/04-premium-light-redesign.md` (status stays `approved`)

- [ ] **Step 1: Add to `01-daily-dashboard.md` §3:**

```markdown
> **UI 리디자인:** 시각·레이아웃은 `SPEC-UI-004`가 SSOT. API·집계는 본 Spec 유지.
```

- [ ] **Step 2: Run full CI gates**

Run: `python3 scripts/ci/run_all_gates.py --profile full`

- [ ] **Step 3: Manual demo checklist**

| Viewport | No scroll | Density tier | Cards clickable |
| --- | --- | --- | --- |
| 320×568 | ☐ | micro/minimal | ☐ |
| 390×844 | ☐ | minimal/dense | ☐ |
| 1280×720 | ☐ | dense/compact | ☐ |
| 1920×1080 | ☐ | comfortable | ☐ |

---

## Spec Coverage Self-Review

| Spec section | Task |
| --- | --- |
| §2 Design system | Task 4 |
| §3 Viewport shell | Task 4, 5 |
| §3.4–3.5 Density + all viewports | Task 4, 6, 9 |
| FR-001 Hero | Task 3 |
| FR-002 Stats | Task 3 |
| FR-003 System cards | Task 1, 2 |
| FR-004 Attention | Task 3, 6 |
| FR-005 Refresh | Task 5, 6 |
| FR-006 Drawer | Task 7 |
| §6 Cytoscape removal | Task 5, 6 |
| AC-001–005 No scroll | Task 9 |
| AC-006 Interactions | Task 6, 8 |
| AC-007 a11y motion | Task 4, 6 |
| NFR-002 JS weight | Task 5, 6 |

No gaps found.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-08-15-premium-light-dashboard.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks
2. **Inline Execution** — implement all tasks in this session with checkpoints

Which approach?
