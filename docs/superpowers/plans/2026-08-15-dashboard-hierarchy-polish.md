# Dashboard Hierarchy Polish (SPEC-UI-005) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the daily dashboard’s collapsed information hierarchy (hero context, system identity, card whitespace, status monotony) per SPEC-UI-005 P0–P2 in one pass.

**Architecture:** Keep HTMX fragment endpoints and `daily_dashboard.py` unchanged. Evolve templates (`zone_a_kpi.html`, `_macros.html`), `dashboard.css`, and `dashboard.js` only. Replace equal-height row splitting with content-based card heights + Zone C internal scroll. Add fragment HTTP tests first, then Playwright viewport ACs.

**Tech Stack:** Jinja2 macros, HTMX 2.x, Alpine 3.x (drawer), vanilla JS (`ResizeObserver`), CSS container queries + `max()` typography floors, pytest + Playwright.

**Spec:** `docs/specs/dashboard/05-hierarchy-polish.md`

## Global Constraints

- **Document no-scroll:** `document.documentElement.scrollHeight <= innerHeight` at `320×568`, `1280×720`, `1920×1080`.
- **Zone C may scroll internally:** `.dash__systems { overflow-y: auto }` — only allowed scroll region.
- **API frozen:** Do not change `/api/dashboard/daily` JSON or `daily_dashboard.py` aggregation.
- **Korean UI copy:** Hero title `오늘의 점검 현황`; pass-rate label `통과율`; attention link `전체 보기` → `/anomalies`; CTA `점검 실행` → `/runs/execute`.
- **Typography floors:** system name ≥ 14px; module chip ≥ 12px; stat label ≥ 12px; page title ≥ 16px — use `max(rem, clamp(...))`.
- **Density row min-heights:** comfortable 88, compact 76, dense 64, minimal 56, micro 48 (px).
- **System name never `display:none`:** remove `micro` rule that hides `.dash-sys-row__name`.
- **Attention strip:** show when `data.attention` non-empty; never hide via JS height check; compact mode at `320×568` shows 1 item + `+N건`.
- **`prefers-reduced-motion`:** no count-up, pulse, or hover `translateY`.
- **Cache bust:** `dashboard.html` → `dashboard.css?v=2`, `dashboard.js?v=15`.

---

## File Map

| File | Action | Responsibility |
| --- | --- | --- |
| `app/web/templates/dashboard/partials/zone_a_kpi.html` | **Modify** | Hero 2-col grid, `통과율` label, `dash-hero__summary`, attention strip always visible |
| `app/web/templates/dashboard/partials/_macros.html` | **Modify** | `module_glyph`, `module_segment_bar`, 3-row `system_row`, chevron, CTA, `data-priority` |
| `app/web/templates/dashboard/partials/zone_b_matrix.html` | **Verify** | No change if macros suffice |
| `app/web/static/dashboard.css` | **Modify** | Tokens, hero grid, typography floors, card 3-row grid, Zone C scroll, accent bar, density tier fixes |
| `app/web/static/dashboard.js` | **Modify** | Viewport-based density, `data-scrollable`, attention compact class, segment/CTA click routing |
| `app/web/templates/dashboard.html` | **Modify** | Cache-bust query strings |
| `tests/test_dashboard_fragments_http.py` | **Modify** | UI-005 fragment contract tests (AC-002, AC-004, AC-007, AC-009) |
| `tests/test_dashboard_viewport.py` | **Modify** | UI-005 Playwright ACs; keep document no-scroll |
| `docs/specs/dashboard/05-hierarchy-polish.md` | **No code** | SSOT (already written) |

---

### Task 1: Fragment HTTP contract tests (TDD baseline)

**Files:**
- Modify: `tests/test_dashboard_fragments_http.py`

**Interfaces:**
- Consumes: existing `FakeDailyDashboardQueries`, `_build_realistic_six_system_dashboard`, `TestClient`
- Produces: failing tests tagged `@pytest.mark.spec("SPEC-UI-005", ...)`

- [ ] **Step 1: Add helper for all-not-inspected payload**

```python
def _build_all_not_inspected_dashboard(registry: ModuleRegistry) -> dict:
    systems = registry.list_systems()
    return build_daily_dashboard(
        systems,
        runs=[],
        generated_at=GEN_AT,
        date_label="2026-08-15",
    )
```

- [ ] **Step 2: Write failing tests**

```python
@pytest.mark.spec("SPEC-UI-005", "AC-002")
def test_kpi_fragment_renders_empty_day_summary(client: TestClient, registry: ModuleRegistry) -> None:
    data = _build_all_not_inspected_dashboard(registry)
    user = User(
        user_id="u", email="u@t.local", name="U", role="user",
        hashed_password="x", is_active=True,
        allowed_system_codes=[s.system_code for s in registry.list_systems()],
        created_at=GEN_AT,
    )
    app = _build_app(user=user, dashboard_data=data, registry=registry)
    with TestClient(app) as c:
        html = c.get("/api/dashboard/daily/fragments/kpi").text
    assert "dash-hero__rate-label" in html
    assert "통과율" in html
    assert "dash-hero__summary" in html
    assert "아직 점검이 시작되지 않았습니다" in html


@pytest.mark.spec("SPEC-UI-005", "AC-004")
def test_kpi_fragment_always_four_stat_tiles(client: TestClient) -> None:
    html = client.get("/api/dashboard/daily/fragments/kpi").text
    assert html.count('class="dash-stats__tile"') == 4
    assert "이상징후" in html


@pytest.mark.spec("SPEC-UI-005", "AC-007")
def test_matrix_fragment_renders_segment_and_chevron(client: TestClient) -> None:
    html = client.get("/api/dashboard/daily/fragments/matrix").text
    assert "dash-sys-row__segment" in html
    assert "dash-sys-row__chevron" in html
    assert "dash-mod__glyph" in html


@pytest.mark.spec("SPEC-UI-005", "AC-009")
def test_matrix_fragment_error_system_has_attention_priority(client: TestClient) -> None:
    html = client.get("/api/dashboard/daily/fragments/matrix").text
    # hom has ERROR in _build_realistic_six_system_dashboard
    assert 'data-system-code="hom"' in html
    idx = html.index('data-system-code="hom"')
    row_chunk = html[idx : idx + 800]
    assert 'data-priority="attention"' in row_chunk
```

- [ ] **Step 3: Run tests — expect FAIL**

Run: `python3 -m pytest tests/test_dashboard_fragments_http.py -v -k "UI-005 or empty_day or four_stat or segment or attention_priority"`

Expected: FAIL — missing `dash-hero__rate-label`, `dash-sys-row__segment`, etc.

---

### Task 2: Hero template — rate block + summary (P0)

**Files:**
- Modify: `app/web/templates/dashboard/partials/zone_a_kpi.html`

**Interfaces:**
- Produces: `#dash-zone-hero` with `.dash-hero__rate-block`, `.dash-hero__rate-label`, `.dash-hero__summary`

- [ ] **Step 1: Restructure hero DOM**

Replace the hero section with:

```jinja
{# Zone A hero + Zone B stats + attention strip #}
{% set t = data.totals %}
<section id="dash-zone-hero" class="dash-hero">
  <div class="dash-hero__text">
    <h1 class="dash-hero__title">오늘의 점검 현황</h1>
    <p class="dash-hero__meta">
      {{ data.date_label }} · {{ t.passed }}/{{ t.modules }} 모듈 정상
      {% if data.generated_at %}
      · 갱신 {{ data.generated_at[11:16] }}
      {% endif %}
    </p>
    {% if t.modules > 0 %}
      {% if t.error > 0 %}
    <p class="dash-hero__summary">점검실패 {{ t.error }}건 — 우선 확인이 필요합니다.</p>
      {% elif t.anomaly > 0 %}
    <p class="dash-hero__summary">이상징후 {{ t.anomaly }}건이 감지되었습니다.</p>
      {% elif t.running > 0 %}
    <p class="dash-hero__summary">{{ t.running }}개 모듈이 진행 중입니다.</p>
      {% elif t.not_inspected == t.modules %}
    <p class="dash-hero__summary">오늘 아직 점검이 시작되지 않았습니다.</p>
      {% else %}
    <p class="dash-hero__summary">오늘 점검이 정상적으로 완료되었습니다.</p>
      {% endif %}
    {% endif %}
  </div>
  <div class="dash-hero__rate-block">
    <span class="dash-hero__rate-label">통과율</span>
    <div class="dash-hero__rate-wrap">
      <span class="dash-hero__rate dash-kpi__value" data-target="{{ t.pass_rate }}">{{ t.pass_rate }}</span><span class="dash-hero__pct">%</span>
    </div>
  </div>
  <div class="dash-hero__actions">
    <button id="dash-refresh" type="button" class="dash-refresh" aria-label="새로고침">
      <svg class="dash-refresh__icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
      새로고침
    </button>
    <span id="dash-htmx-busy" class="dash-htmx-indicator">갱신…</span>
  </div>
</section>
```

- [ ] **Step 2: Fix attention strip — remove `hidden`, add inbox link**

```jinja
{% if data.attention %}
<section id="dash-zone-attention" class="dash-attention">
  <div class="dash-attention__item" data-tone="{{ data.attention[0].tone }}">
    <span class="dash-attention__dot" aria-hidden="true"></span>
    <span class="dash-attention__text">
      <strong>{{ data.attention[0].system_name }}</strong>
      {% if data.attention[0].module_name %} · {{ data.attention[0].module_name }}{% endif %}
      · {{ data.attention[0].status_label }}
    </span>
    {% if data.attention[0].run_id %}
    <a href="/runs/{{ data.attention[0].run_id }}" class="dash-attention__link">Run</a>
    {% endif %}
  </div>
  {% if data.attention|length > 1 %}
  <span class="dash-attention__more">+{{ data.attention|length - 1 }}건</span>
  {% endif %}
  <a href="/anomalies" class="dash-attention__inbox">전체 보기</a>
</section>
{% endif %}
```

- [ ] **Step 3: Run fragment tests for AC-002, AC-004**

Run: `python3 -m pytest tests/test_dashboard_fragments_http.py::test_kpi_fragment_renders_empty_day_summary tests/test_dashboard_fragments_http.py::test_kpi_fragment_always_four_stat_tiles -v`

Expected: PASS (matrix tests still FAIL until Task 4).

---

### Task 3: Hero + Stats CSS (P0)

**Files:**
- Modify: `app/web/static/dashboard.css` — Zone A/B sections (~lines 96–224)

**Interfaces:**
- Consumes: DOM from Task 2
- Produces: visible hero title at 1280×720; stat tiles `min-height: 56px`

- [ ] **Step 1: Add design tokens at `.dash` block**

```css
.dash {
  --pl-accent: #6366f1;
  --pl-shadow-sm: 0 1px 3px rgb(0 0 0 / 0.06), 0 1px 2px rgb(0 0 0 / 0.04);
  --pl-shadow-md: 0 8px 30px -8px rgb(0 0 0 / 0.12);
}
```

- [ ] **Step 2: Replace `.dash-hero` grid**

```css
.dash-hero {
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto;
  align-items: end;
  gap: 0.5rem 1.25rem;
}

.dash-hero__text {
  grid-column: 1;
  grid-row: 1 / 3;
  min-width: 0;
}

.dash-hero__rate-block {
  grid-column: 2;
  grid-row: 1;
  text-align: right;
}

.dash-hero__actions {
  grid-column: 2;
  grid-row: 2;
  justify-self: end;
}

.dash-hero__rate-label {
  display: block;
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--pl-text-muted);
}

.dash-hero__summary {
  margin: 0.35rem 0 0;
  font-size: max(0.75rem, clamp(0.7rem, 1.4cqh, 0.875rem));
  font-weight: 600;
  color: var(--pl-text-muted);
}

.dash-hero__title {
  font-size: max(1rem, clamp(1rem, 3cqh, 2rem));
}
```

- [ ] **Step 3: Stats strip floors**

```css
.dash-stats__tile {
  min-height: 56px;
}

.dash-stats__label {
  font-size: max(0.75rem, clamp(0.625rem, 1.2cqh, 0.8125rem));
  font-weight: 700;
}

.dash-stats__value {
  font-size: max(1.25rem, clamp(1.25rem, 2.5cqh, 2rem));
}
```

- [ ] **Step 4: Attention strip styles**

```css
.dash-attention__inbox {
  flex-shrink: 0;
  margin-left: auto;
  font-size: max(0.75rem, clamp(0.6rem, 1.2cqh, 0.75rem));
  font-weight: 700;
  color: var(--pl-accent);
  text-decoration: none;
}

.dash-attention--compact {
  padding: 0.25rem 0.5rem;
}

.dash-attention--compact .dash-attention__text {
  font-size: 0.65rem;
}
```

- [ ] **Step 5: Remove mobile hero override that breaks grid** (lines ~582–595) — align with new 2-col grid; keep `dash-hero__text` spanning rows.

- [ ] **Step 6: Delete `.dash:has(.dash__systems[data-density="micro"]) .dash-attention { display: none }`** rule.

---

### Task 4: Macros — glyphs, segment bar, 3-row system card (P1/P2)

**Files:**
- Modify: `app/web/templates/dashboard/partials/_macros.html`

**Interfaces:**
- Produces:
  - `module_glyph(tone: str) -> str` (Jinja macro)
  - `module_segment_bar(sys) -> HTML`
  - `system_row(sys)` with `data-priority`, chevron, CTA, segment, glyphs

- [ ] **Step 1: Add `module_glyph` macro**

```jinja
{% macro module_glyph(tone) -%}
{% set g = {
  'passed': '✓', 'anomaly': '!', 'error': '×',
  'running': '●', 'waiting_input': '●',
  'not_inspected': '○', 'pending': '○',
  'blocked': '—', 'skipped': '—', 'cancelled': '—'
} %}
<span class="dash-mod__glyph" aria-hidden="true">{{ g.get(tone, '○') }}</span>
{%- endmacro %}
```

- [ ] **Step 2: Update `module_pill` — inject glyph before label**

```jinja
{{ module_glyph(tone) }}<span class="dash-mod__label">{{ mod.name }}</span>
```

- [ ] **Step 3: Add `module_segment_bar` macro**

```jinja
{% macro module_segment_bar(sys) -%}
<div class="dash-sys-row__segment" role="presentation">
  {% for mod in sys.modules %}
  {% set tone = mod.tone or 'not_inspected' %}
  {% set tip = mod.name ~ ' · ' ~ (mod.status_label or '') %}
  {%- if mod.run_id -%}
  <a href="/runs/{{ mod.run_id }}" class="dash-seg dash-seg--link" data-tone="{{ tone }}" title="{{ tip }}" aria-label="{{ mod.name }}"></a>
  {%- else -%}
  <span class="dash-seg" data-tone="{{ tone }}" title="{{ tip }}"></span>
  {%- endif -%}
  {% endfor %}
</div>
{%- endmacro %}
```

- [ ] **Step 4: Rewrite `system_row`**

```jinja
{% macro system_row(sys) -%}
{% set badge = system_summary_badge(sys) %}
{% set code_label = sys.system_code | upper %}
{% set attention_tones = ['error', 'anomaly', 'running', 'waiting_input', 'blocked'] %}
{% set priority = 'attention' if badge.tone in attention_tones else 'normal' %}
{% set show_cta = badge.tone == 'not_inspected' and sys.inspected == 0 %}
<div class="dash-sys-row"
     data-system-code="{{ sys.system_code }}"
     data-priority="{{ priority }}"
     data-accent-tone="{{ badge.tone }}"
     tabindex="0"
     role="button"
     aria-label="{{ sys.system_name }} 상세 보기">
  <div class="dash-sys-row__identity">
    <span class="dash-sys-row__icon" data-tone="{{ badge.tone }}">{{ code_label }}</span>
    <div class="dash-sys-row__text">
      <span class="dash-sys-row__name">{{ sys.system_name }}</span>
      <span class="dash-sys-row__meta">{{ sys.inspected }}/{{ sys.module_total }} 모듈</span>
    </div>
  </div>
  <span class="dash-sys-row__badge" data-tone="{{ badge.tone }}">{{ badge.label }}</span>
  {% if show_cta %}
  <a href="/runs/execute" class="dash-sys-row__cta" data-action="execute">점검 실행</a>
  {% endif %}
  <span class="dash-sys-row__chevron" aria-hidden="true">›</span>
  {{ module_segment_bar(sys) }}
  <div class="dash-sys-row__modules">
    {% for mod in sys.modules %}
    {{ module_pill(mod) }}
    {% endfor %}
  </div>
</div>
{%- endmacro %}
```

- [ ] **Step 5: Run matrix fragment tests**

Run: `python3 -m pytest tests/test_dashboard_fragments_http.py::test_matrix_fragment_renders_segment_and_chevron tests/test_dashboard_fragments_http.py::test_matrix_fragment_error_system_has_attention_priority -v`

Expected: PASS

---

### Task 5: System card + Zone C scroll CSS (P1)

**Files:**
- Modify: `app/web/static/dashboard.css` — Zone C + density sections

- [ ] **Step 1: Zone C scroll container**

```css
.dash__systems {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: clamp(4px, 0.6cqh, 8px);
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  scrollbar-gutter: stable;
}

.dash__systems[data-scrollable="true"] {
  mask-image: linear-gradient(to bottom, #000 0%, #000 92%, transparent 100%);
}
```

- [ ] **Step 2: Card row — no equal flex stretch**

```css
.dash-sys-row {
  flex: 0 0 auto;
  min-height: var(--dash-row-min-h, 88px);
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  grid-template-rows: auto auto auto;
  align-items: center;
  gap: 0.35rem 0.5rem;
  box-shadow: var(--pl-shadow-sm);
}

.dash-sys-row[data-priority="attention"] {
  border-left: 3px solid var(--st-error);
  padding-left: calc(clamp(0.5rem, 1.5cqi, 1.25rem) - 3px);
}

.dash-sys-row[data-priority="attention"][data-accent-tone="anomaly"] { border-left-color: var(--st-anomaly); }
.dash-sys-row[data-priority="attention"][data-accent-tone="running"],
.dash-sys-row[data-priority="attention"][data-accent-tone="waiting_input"] { border-left-color: var(--st-running); }
.dash-sys-row[data-priority="attention"][data-accent-tone="blocked"] { border-left-color: var(--st-blocked); }

.dash-sys-row__identity { grid-column: 1; grid-row: 1; min-width: 0; }
.dash-sys-row__badge { grid-column: 2; grid-row: 1; }
.dash-sys-row__cta { grid-column: 3; grid-row: 1; }
.dash-sys-row__chevron { grid-column: 4; grid-row: 1; font-size: 1.25rem; opacity: 0.35; }
.dash-sys-row:hover .dash-sys-row__chevron { opacity: 0.7; }
.dash-sys-row__segment { grid-column: 1 / -1; grid-row: 2; }
.dash-sys-row__modules { grid-column: 1 / -1; grid-row: 3; }
```

- [ ] **Step 3: Typography floors for identity + chips**

```css
.dash-sys-row__name {
  font-size: max(0.875rem, clamp(0.75rem, 1.8cqh, 1rem));
}

.dash-mod {
  font-size: max(0.75rem, clamp(0.6rem, 1.4cqh, 0.8125rem));
}

.dash-mod__glyph {
  font-size: 0.85em;
  opacity: 0.9;
  margin-right: 0.2em;
}
```

- [ ] **Step 4: Segment bar styles**

```css
.dash-sys-row__segment {
  display: flex;
  gap: 1px;
  height: 4px;
  border-radius: 2px;
  overflow: hidden;
}

.dash-seg {
  flex: 1;
  min-width: 0;
  border-radius: 2px;
  background: var(--st-idle);
}

.dash-seg[data-tone="passed"] { background: var(--st-passed); }
.dash-seg[data-tone="anomaly"] { background: var(--st-anomaly); }
.dash-seg[data-tone="error"] { background: var(--st-error); }
.dash-seg[data-tone="running"],
.dash-seg[data-tone="waiting_input"] { background: var(--st-running); }
.dash-seg--link { display: block; text-decoration: none; }
```

- [ ] **Step 5: CTA link style**

```css
.dash-sys-row__cta {
  flex-shrink: 0;
  font-size: max(0.75rem, 0.75rem);
  font-weight: 700;
  color: var(--pl-accent);
  text-decoration: none;
  white-space: nowrap;
}
```

- [ ] **Step 6: Density tier CSS variables + hide segment at minimal/micro**

```css
.dash__systems[data-density="comfortable"] { --dash-row-min-h: 88px; }
.dash__systems[data-density="compact"] { --dash-row-min-h: 76px; }
.dash__systems[data-density="dense"] { --dash-row-min-h: 64px; }
.dash__systems[data-density="minimal"] { --dash-row-min-h: 56px; }
.dash__systems[data-density="micro"] { --dash-row-min-h: 48px; }

.dash__systems[data-density="minimal"] .dash-sys-row__segment,
.dash__systems[data-density="micro"] .dash-sys-row__segment {
  display: none;
}

.dash__systems[data-density="compact"] .dash-sys-row__segment {
  height: 3px;
}
```

- [ ] **Step 7: Remove rules that hide system name**

Delete:
```css
.dash__systems[data-density="micro"] .dash-sys-row__name { display: none; }
```

- [ ] **Step 8: Update mobile card grid** (`@media max-width 767px`) to match 3-row internal layout (identity+badge top, modules bottom full width).

---

### Task 6: `dashboard.js` — density, scrollable, attention compact (P1/P2)

**Files:**
- Modify: `app/web/static/dashboard.js`

**Interfaces:**
- Produces:
  - `ROW_MIN_H = { comfortable: 88, compact: 76, dense: 64, minimal: 56, micro: 48 }`
  - `computeDensityTier(zoneCAvail, systemCount) -> string`
  - `container.dataset.density`, `container.dataset.scrollable`
  - `syncAttentionCompact()` — adds `dash-attention--compact` when `root.clientWidth < 400`

- [ ] **Step 1: Replace density algorithm**

```javascript
const ROW_MIN_H = {
  comfortable: 88,
  compact: 76,
  dense: 64,
  minimal: 56,
  micro: 48,
};
const TIER_ORDER = ["comfortable", "compact", "dense", "minimal", "micro"];
const DENSITY_GAP_PX = 8;

function computeDensityTier(zoneCAvail, systemCount) {
  const n = Math.max(systemCount, 1);
  const gaps = DENSITY_GAP_PX * Math.max(0, n - 1);
  for (const tier of TIER_ORDER) {
    const required = n * ROW_MIN_H[tier] + gaps;
    if (required <= zoneCAvail) return tier;
  }
  return "micro";
}

function measureZoneCAvail() {
  const hero = $("#dash-zone-hero", root);
  const stats = $("#dash-zone-stats", root);
  const attention = $("#dash-zone-attention", root);
  const dashStyle = getComputedStyle(root);
  const pad =
    parseFloat(dashStyle.paddingTop) + parseFloat(dashStyle.paddingBottom);
  const gap = parseFloat(dashStyle.rowGap || dashStyle.gap) || 0;
  const fixed =
    (hero?.offsetHeight || 0) +
    (stats?.offsetHeight || 0) +
    (attention?.offsetHeight || 0) +
    pad +
    gap * (attention ? 3 : 2);
  return Math.max(0, root.clientHeight - fixed);
}

function updateDashboardDensity() {
  const container = $("#dash-zone-matrix", root);
  if (!container) return;

  const n =
    Number(container.dataset.systemCount) ||
    container.querySelectorAll(".dash-sys-row").length ||
    1;
  const zoneCAvail = measureZoneCAvail();
  const tier = computeDensityTier(zoneCAvail, n);
  container.dataset.density = tier;

  const needsScroll =
    container.scrollHeight > container.clientHeight + 1;
  container.dataset.scrollable = needsScroll ? "true" : "false";
  syncAttentionCompact();
}
```

- [ ] **Step 2: Replace `toggleAttentionStrip` with `syncAttentionCompact`**

```javascript
function syncAttentionCompact() {
  const strip = $("#dash-zone-attention", root);
  if (!strip) return;
  strip.classList.toggle("dash-attention--compact", root.clientWidth < 400);
}
```

Remove all `strip.hidden = true` logic from old `toggleAttentionStrip`. Update `onAfterSwap` to call `syncAttentionCompact()` instead of `toggleAttentionStrip()`.

- [ ] **Step 3: Click routing — CTA + segment links**

In `root.addEventListener("click", ...)` add before row handler:

```javascript
const cta = ev.target.closest(".dash-sys-row__cta");
if (cta) {
  ev.stopPropagation();
  return;
}

const segLink = ev.target.closest(".dash-seg--link");
if (segLink) {
  ev.stopPropagation();
  return;
}
```

- [ ] **Step 4: Manual smoke**

Run server, open `/`, resize window — verify `data-density` and `data-scrollable` update in DevTools.

---

### Task 7: Playwright viewport tests (P0/P1/P2 AC)

**Files:**
- Modify: `tests/test_dashboard_viewport.py`

- [ ] **Step 1: Add helper for all-not-inspected live data fixture**

```python
@pytest.fixture(scope="module")
def empty_day_data(registry: ModuleRegistry) -> dict:
    return build_daily_dashboard(
        registry.list_systems(),
        runs=[],
        generated_at=GEN_AT,
        date_label="2026-08-15",
    )
```

Add second `live_server` fixture or parametrize existing one — simplest: add `test_dashboard_hero_visible_1280x720` using existing realistic data.

- [ ] **Step 2: AC-001 hero visibility test**

```python
@pytest.mark.spec("SPEC-UI-005", "AC-001")
def test_dashboard_hero_visible_1280x720(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-hero__title")
    title = page.locator(".dash-hero__title")
    assert title.is_visible()
    assert title.inner_text() == "오늘의 점검 현황"
    label = page.locator(".dash-hero__rate-label")
    assert label.is_visible()
    assert label.inner_text() == "통과율"
    box = title.bounding_box()
    assert box is not None and box["height"] >= 16 and box["width"] >= 120
```

- [ ] **Step 3: AC-005 Zone C scroll + document no-scroll**

```python
@pytest.mark.spec("SPEC-UI-005", "AC-005")
def test_dashboard_zone_c_internal_scroll_document_fixed(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector("#dash-zone-matrix")
    overflow = page.eval_on_selector(".dash__systems", "el => getComputedStyle(el).overflowY")
    assert overflow == "auto"
    metrics = page.evaluate(
        "() => ({ sh: document.documentElement.scrollHeight, ih: window.innerHeight })"
    )
    assert metrics["sh"] <= metrics["ih"]
```

- [ ] **Step 4: AC-003 system name font-size**

```python
@pytest.mark.spec("SPEC-UI-005", "AC-003")
def test_dashboard_system_name_min_font(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(f"{live_server}/")
    page.wait_for_selector(".dash-sys-row__name")
    fs = page.eval_on_selector(
        ".dash-sys-row__name",
        "el => parseFloat(getComputedStyle(el).fontSize)",
    )
    assert fs >= 14
```

- [ ] **Step 5: AC-008 attention on mobile**

Add fixture server with attention items (use realistic data — already has anomalies). Test:

```python
@pytest.mark.spec("SPEC-UI-005", "AC-008")
def test_dashboard_attention_visible_mobile(page, live_server: str) -> None:
    page.set_viewport_size({"width": 320, "height": 568})
    page.goto(f"{live_server}/")
    page.wait_for_selector("#dash-zone-attention")
    assert page.locator("#dash-zone-attention").is_visible()
    assert page.locator('a.dash-attention__inbox[href="/anomalies"]').count() == 1
```

- [ ] **Step 6: Keep existing no-scroll tests** — update `@pytest.mark.spec` to also reference `SPEC-UI-005` AC-005 (document-level only).

- [ ] **Step 7: Run Playwright suite**

Run: `python3 -m pytest tests/test_dashboard_viewport.py -v`

Skip acceptable if Chromium not installed.

---

### Task 8: Cache bust + CI gate

**Files:**
- Modify: `app/web/templates/dashboard.html`

- [ ] **Step 1: Bump asset versions**

```html
<link rel="stylesheet" href="/static/dashboard.css?v=2">
...
<script src="/static/dashboard.js?v=15" defer></script>
```

- [ ] **Step 2: Run full CI gates**

Run: `python3 scripts/ci/run_all_gates.py --profile full`

Or minimum:

```bash
python3 -m pytest tests/test_daily_dashboard.py tests/test_dashboard_fragments_http.py tests/test_dashboard_viewport.py -q
python3 -m ruff check app/web/static/dashboard.js
```

- [ ] **Step 3: Manual QA** — `docs/specs/dashboard/05-hierarchy-polish.md` §10.2 checklist

---

## Spec Coverage Self-Review

| Spec requirement | Task |
| --- | --- |
| P0-1 Hero title/rate label/summary | Task 2, 3 |
| P0-2 System identity visibility | Task 4, 5, 7 |
| P0-3 KPI 4 tiles | Task 2 (already 4), test Task 1 |
| P1-1 Zone C scroll | Task 5, 6 |
| P1-2 2/3-row card layout | Task 4, 5 |
| P1-3 Segment bar | Task 4, 5 |
| P1-4 Typography floors | Task 3, 5 |
| P2-1 Accent bar | Task 4, 5 |
| P2-2 Attention + inbox link | Task 2, 3, 6 |
| P2-3 Chevron, CTA, elevation | Task 4, 5 |
| P2-4 Module glyphs | Task 4 |
| AC-006 card height bounds | Task 5 row min-h; optional Playwright add later |
| AC-010 reduced-motion glyphs | Task 4 (glyph always in DOM; no JS) |
| AC-011 aggregation unchanged | No `daily_dashboard.py` edits |

---

## Suggested Commit Sequence

1. `test: add SPEC-UI-005 fragment contract tests`
2. `feat(dashboard): hero rate label and contextual summary`
3. `feat(dashboard): system card 3-row layout with segment bar and glyphs`
4. `feat(dashboard): zone C content-height scroll and density rewrite`
5. `test: add SPEC-UI-005 viewport Playwright ACs`

---

## Execution Handoff

**Plan saved to `docs/superpowers/plans/2026-08-15-dashboard-hierarchy-polish.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** — one fresh subagent per task, review between tasks
2. **Inline Execution** — implement tasks in this session with checkpoints after Tasks 2, 5, 7

Which approach do you want?
