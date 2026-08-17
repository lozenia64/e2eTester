# Sync Row Partition Fill (P1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `syncRowPartition`가 Zone C(`.dash__systems`)의 `clientHeight`를 실측 `sum(row heights) + gaps`로 ±4px 이내 채우도록 수정하여 SPEC-UI-007 AC-003을 만족한다.

**Architecture:** `dashboard.js`의 partition 파이프라인을 **계산 → flex 적용 → 실측 보정** 3단으로 재구성한다. gap은 `getComputedStyle` 파싱값을 fallback으로만 쓰고, 우선 행 offset으로 실측한다. remainder 정수 픽셀은 앞쪽 행에 균등 +1px 분배한다(마지막 행만 stretch하지 않음 — spread ≤ 2px 유지). KPI/attention 압축 후 `offsetHeight` flush 뒤 partition을 실행한다.

**Tech Stack:** vanilla JS (`ResizeObserver`, flex inline styles), CSS flex column + `gap: clamp(...)`, pytest + Playwright Chromium.

**Spec:** `docs/specs/dashboard/07-viewport-fit-no-scroll.md` — AC-003 (균등 분할), AC-002 (Zone C 무스크롤) 회귀 방지.

## Global Constraints

- **Spec SSOT:** 무스크롤·partition은 `SPEC-UI-007` 우선. UI-005 AC-005(Zone C scroll)는 폐기 — `overflow: hidden` 유지.
- **No API / 집계 변경:** `daily_dashboard.py`, fragment endpoint, 템플릿 마크업 구조 불변.
- **No Zone C scroll:** `.dash__systems`에 `overflow: auto|scroll` 금지. `data-scrollable="true"` 금지.
- **균등 분할:** `max(rowH) - min(rowH) <= 2px`. 마지막 행만 stretch **금지**.
- **한국어 UI 문자열 불변.**
- **Cache bust:** `dashboard.js?v=21` (`dashboard.html` 현재 `?v=20`).
- **검증:** `python3 -m pytest tests/test_dashboard_viewport.py -q` green + `python3 scripts/ci/run_all_gates.py --profile full` (PR 전).
- **Windows `.sh`:** `bash <path>.sh` 형태만 사용.

---

## Trigger (confirmed failure)

```text
FAILED tests/test_dashboard_viewport.py::test_system_rows_equal_partition_1280x720
heights=[82,82,82,82,82,82], spread=0, sum=512.9522, container=524
assert abs(sum - container) <= 4  → delta ≈ 11px
```

**Root cause:** `syncRowPartition`이 이론 `clientHeight − gap×(n−1)`만 사용하고 적용 후 실측 보정 없음. gap sub-pixel·partition 시점 `clientHeight` 불일치(KPI compress 전/후)로 하단 빈 공간 발생.

---

## File Map

| File | Action | Responsibility |
| --- | --- | --- |
| `app/web/static/dashboard.js` | **Modify** | `measureFlexColumnGap`, `measurePartitionSum`, `distributeRowHeights`, `syncRowPartition` 재구현 |
| `app/web/templates/dashboard.html` | **Modify** | `dashboard.js?v=21` cache bust |
| `tests/test_dashboard_viewport.py` | **Modify** (optional) | partition helper JS를 테스트와 구현이 동일 좌표계 쓰는지 주석 보강 |
| `docs/specs/dashboard/07-viewport-fit-no-scroll.md` | **Modify** (optional) | §3.3에 “적용 후 실측 ±4px 보정” 1줄 |

**Do not touch:** `dashboard.css` (1차), fragment templates, `daily_dashboard.py`.

---

## Interfaces (cross-task contract)

모든 헬퍼는 `dashboard.js` IIFE 내부, `readContainerGapPx` 아래에 정의.

```javascript
/** flex column gap — layout 측정 우선, computed fallback */
function measureFlexColumnGap(container, rows) → number

/** 테스트 AC-003과 동일 좌표계 */
function measurePartitionSum(container, rows, gap) → { sum: number, container: number, delta: number }

/** totalRowPixels를 n행에 정수 균등 분배 → number[] heights */
function distributeRowHeights(n, totalRowPixels) → number[]

/** 기존 시그니처 유지, 내부만 교체 */
function syncRowPartition(container, n, gapHint) → void
```

`fitAndPartition(container, n)`은 기존 tier 로직 유지. `gapHint`는 `readContainerGapPx(container)` 결과.

---

### Task 1: Confirm red test (AC-003 partition sum)

**Files:**
- Test: `tests/test_dashboard_viewport.py:346-366`

**Interfaces:**
- Consumes: 기존 `live_server` fixture, `_load_dashboard_1280x720`, `_wait_for_density_stable`

- [ ] **Step 1: Run failing test**

Run:

```bash
python3 -m pytest tests/test_dashboard_viewport.py::test_system_rows_equal_partition_1280x720 -v
```

Expected: **FAIL** — `assert abs(metrics["sum"] - metrics["container"]) <= 4` with delta ≈ 11px.

- [ ] **Step 2: Record baseline metrics**

Note `heights`, `sum`, `container`, `spread` from failure output for post-fix comparison.

---

### Task 2: Add partition measurement helpers

**Files:**
- Modify: `app/web/static/dashboard.js` (insert after `readContainerGapPx`, before `pickTierForRowH`)

**Interfaces:**
- Consumes: `readContainerGapPx(container)`
- Produces: `measureFlexColumnGap`, `measurePartitionSum`, `distributeRowHeights`

- [ ] **Step 1: Add `measureFlexColumnGap`**

```javascript
function measureFlexColumnGap(container, rows) {
  const fallback = readContainerGapPx(container);
  if (!rows.length) return fallback;
  if (rows.length < 2) return fallback;
  const first = rows[0];
  const second = rows[1];
  const measured = second.offsetTop - first.offsetTop - first.offsetHeight;
  if (!Number.isFinite(measured) || measured < 0) return fallback;
  return measured;
}
```

- [ ] **Step 2: Add `measurePartitionSum`**

```javascript
function measurePartitionSum(container, rows, gap) {
  const heights = [...rows].map((row) => row.clientHeight);
  const sum =
    heights.reduce((acc, h) => acc + h, 0) +
    gap * Math.max(0, heights.length - 1);
  const containerH = container.clientHeight;
  return { sum, container: containerH, delta: containerH - sum };
}
```

- [ ] **Step 3: Add `distributeRowHeights`**

```javascript
function distributeRowHeights(n, totalRowPixels) {
  const count = Math.max(1, n);
  const available = Math.max(0, Math.floor(totalRowPixels));
  const base = Math.floor(available / count);
  const remainder = available - base * count;
  const heights = [];
  for (let i = 0; i < count; i += 1) {
    heights.push(base + (i < remainder ? 1 : 0));
  }
  return heights;
}
```

- [ ] **Step 4: Smoke — no syntax error**

Run:

```bash
node --check app/web/static/dashboard.js
```

Expected: no output (exit 0). If `node` unavailable, skip — pytest in Task 4 validates.

---

### Task 3: Rewrite `syncRowPartition` with post-apply correction

**Files:**
- Modify: `app/web/static/dashboard.js:53-65` (replace `syncRowPartition` body)

**Interfaces:**
- Consumes: Task 2 helpers, `readContainerGapPx`
- Produces: updated `syncRowPartition(container, n, gapHint)`

- [ ] **Step 1: Replace `syncRowPartition`**

```javascript
function applyRowFlexBasis(rows, heights) {
  rows.forEach((row, index) => {
    const h = heights[index] ?? heights[heights.length - 1] ?? 0;
    row.style.flexGrow = "0";
    row.style.flexShrink = "0";
    row.style.flexBasis = `${h}px`;
    row.style.flex = `0 0 ${h}px`;
  });
}

function syncRowPartition(container, n, gapHint) {
  const rows = container.querySelectorAll(".dash-sys-row");
  if (!rows.length) return;

  const rowCount = Math.min(Math.max(1, n), rows.length);
  void container.offsetHeight;

  let gap = measureFlexColumnGap(container, rows);
  if (!Number.isFinite(gap) || gap < 0) {
    gap = gapHint ?? readContainerGapPx(container);
  }

  const totalGap = gap * Math.max(0, rowCount - 1);
  const available = Math.max(0, container.clientHeight - totalGap);
  let heights = distributeRowHeights(rowCount, available);
  applyRowFlexBasis(rows, heights);
  void container.offsetHeight;

  for (let attempt = 0; attempt < 2; attempt += 1) {
    gap = measureFlexColumnGap(container, rows);
    const { delta } = measurePartitionSum(container, rows, gap);
    if (Math.abs(delta) <= 4) break;

    if (delta > 0) {
      const bump = Math.min(Math.floor(delta), rowCount);
      heights = heights.map((h, i) => (i < bump ? h + 1 : h));
      applyRowFlexBasis(rows, heights);
      void container.offsetHeight;
      continue;
    }

    // delta < 0 — shrink from last rows (overflow prevention)
    let excess = Math.min(Math.floor(-delta), rowCount);
    heights = heights.map((h, i) => {
      const idx = rowCount - 1 - i;
      if (excess > 0 && idx < rowCount && heights[idx] > 1) {
        excess -= 1;
        return heights[idx] - 1;
      }
      return h;
    });
    applyRowFlexBasis(rows, heights);
    void container.offsetHeight;
  }
}
```

- [ ] **Step 2: Update `applyDensityLayout` call**

`applyDensityLayout`는 그대로 `syncRowPartition(container, n, gap)` 호출. `gap`은 `readContainerGapPx` 결과 — 변경 없음.

- [ ] **Step 3: Run partition test (expect green or closer)**

Run:

```bash
python3 -m pytest tests/test_dashboard_viewport.py::test_system_rows_equal_partition_1280x720 -v
```

Expected: **PASS** (`abs(sum - container) <= 4`, `spread <= 2`).

---

### Task 4: Stabilize `fitAndPartition` layout flush order

**Files:**
- Modify: `app/web/static/dashboard.js:78-97` (`fitAndPartition`)

**Interfaces:**
- Consumes: `syncKpiCompress`, `syncAttentionCompact`, `syncRowPartition`
- Produces: partition runs after KPI host height settled

- [ ] **Step 1: Ensure flush before tier + partition**

`fitAndPartition` 시작부가 아래 순서인지 확인·정리:

```javascript
function fitAndPartition(container, n) {
  syncKpiCompress();
  syncAttentionCompact();
  void container.offsetHeight; // KPI compress reflected in matrix clientHeight

  const gap = readContainerGapPx(container);
  const rowH = (container.clientHeight - gap * Math.max(0, n - 1)) / Math.max(n, 1);
  let tierIdx = tierIndex(pickTierForRowH(rowH));

  applyDensityLayout(container, TIER_ORDER[tierIdx], n, gap);
  void container.offsetHeight;

  let retries = 0;
  while (!containerFits(container) && tierIdx < TIER_ORDER.length - 1 && retries < 4) {
    tierIdx += 1;
    applyDensityLayout(container, TIER_ORDER[tierIdx], n, gap);
    void container.offsetHeight;
    retries += 1;
  }
}
```

(이미 동일하면 diff 없음 — **검증만** 수행.)

- [ ] **Step 2: Run full viewport suite**

Run:

```bash
python3 -m pytest tests/test_dashboard_viewport.py -q
```

Expected: **all passed** (Chromium required; skip if not installed).

---

### Task 5: Cache bust + regression gates

**Files:**
- Modify: `app/web/templates/dashboard.html:55`

- [ ] **Step 1: Bump JS cache bust**

Change:

```html
<script src="/static/dashboard.js?v=20" defer></script>
```

to:

```html
<script src="/static/dashboard.js?v=21" defer></script>
```

- [ ] **Step 2: Run dashboard-related tests**

Run:

```bash
python3 -m pytest tests/test_dashboard_viewport.py tests/test_dashboard_fragments_http.py tests/test_daily_dashboard.py -q
```

Expected: all passed.

- [ ] **Step 3: Spec traceability**

Run:

```bash
python3 -m pytest tests/test_spec_traceability.py -q
```

Expected: passed.

- [ ] **Step 4: Commit (when user requests)**

```bash
git add app/web/static/dashboard.js app/web/templates/dashboard.html
git commit -m "$(cat <<'EOF'
fix(dashboard): SPEC-UI-007 partition fills Zone C within ±4px

Measure flex gap from layout and correct row heights after apply so
sum(heights)+gaps matches .dash__systems clientHeight (AC-003).
EOF
)"
```

---

### Task 6 (optional): Spec §3.3 one-line clarification

**Files:**
- Modify: `docs/specs/dashboard/07-viewport-fit-no-scroll.md` §3.3

- [ ] **Step 1: Add implementation note after row_h formula**

Append:

```markdown
**구현:** `syncRowPartition`은 flex basis 적용 후 실측 `sum + gaps`로 ±4px 보정 루프(최대 2회)를 수행한다. remainder는 앞쪽 행에 +1px 균등 분배(spread ≤ 2px).
```

- [ ] **Step 2: Commit with docs prefix if committed separately**

---

## Self-Review (plan vs spec)

| Spec requirement | Task |
| --- | --- |
| AC-003 spread ≤ 2px | Task 3 — 균등 +1px bump, no last-row stretch |
| AC-003 sum ± 4px | Task 3 — `measurePartitionSum` + correction loop |
| AC-002 no Zone C scroll | Task 3 delta < 0 shrink branch; Task 4 `containerFits` loop |
| AC-007 no `data-scrollable` | unchanged — `delete container.dataset.scrollable` in `applyDensityLayout` |
| §3.3 row_h formula | Task 4 tier pick still uses `(clientHeight - gap*(n-1))/n` |
| UI-006 visibility | no template/CSS changes — regression via Task 5 |
| UI-008 sidebar inset | no `dashboard.css` changes — regression via Task 5 |

**Placeholder scan:** none.

---

## Manual smoke (1280×720)

DevTools console after load:

```javascript
(() => {
  const sys = document.querySelector(".dash__systems");
  const rows = [...document.querySelectorAll(".dash-sys-row")];
  const gap = parseFloat(getComputedStyle(sys).gap);
  const heights = rows.map((r) => r.clientHeight);
  const sum = heights.reduce((a, b) => a + b, 0) + gap * Math.max(0, rows.length - 1);
  return {
    container: sys.clientHeight,
    sum,
    delta: sys.clientHeight - sum,
    spread: Math.max(...heights) - Math.min(...heights),
  };
})();
```

Expected: `Math.abs(delta) <= 4`, `spread <= 2`.

---

## Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Correction loop causes overflow | `containerFits` + delta < 0 shrink branch; tier upgrade loop unchanged |
| `offsetTop` gap wrong during animation | `_wait_for_density_stable` in tests; `animation: none` under reduced-motion |
| Playwright Chromium missing | `pytest.importorskip`; CI installs Chromium |
| spread > 2 after bump | bump only `floor(delta)` rows by +1px once per attempt |

---

## Definition of Done

- [ ] `test_system_rows_equal_partition_1280x720` PASS
- [ ] `tests/test_dashboard_viewport.py` full PASS
- [ ] `tests/test_dashboard_fragments_http.py` + `tests/test_daily_dashboard.py` PASS
- [ ] Manual smoke: `abs(delta) <= 4`, `spread <= 2` at 1280×720
- [ ] `dashboard.js?v=21` in `dashboard.html`
- [ ] (PR) `python3 scripts/ci/run_all_gates.py --profile full` PASS
