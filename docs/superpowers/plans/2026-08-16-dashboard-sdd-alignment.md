# Dashboard SDD Alignment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 리뷰에서 지적된 5건(미커밋 partition/inset 커밋, UI-007 tier 알고리즘 SSOT 정합, UI-005 폐기 AC·pytest 태그 정리, UI-007 AC-006 테스트, UI-005 AC-009 accent 이관)을 한 번에 반영해 Spec·구현·테스트 추적성을 맞춘다.

**Architecture:** 구현 코드는 **유지**하고 SSOT 문서를 실제 `dashboard.js` 알고리즘(`TIER_MIN_H` + `containerFits` 루프 + `syncRowPartition` 실측 보정)에 맞춘다. UI-005에서 UI-007로 superseded된 AC는 본문에 명시 표기하고 pytest `@pytest.mark.spec` 태그를 UI-007로 교체한다. accent는 `border-left` 대신 UI-007 §3.3의 `inset box-shadow`를 AC로 승격한다.

**Tech Stack:** vanilla JS (`dashboard.js`), CSS (`dashboard.css`), Jinja fragments, pytest + Playwright Chromium, SDD spec markdown.

**Spec:** `docs/specs/dashboard/05-hierarchy-polish.md`, `docs/specs/dashboard/07-viewport-fit-no-scroll.md`

## Global Constraints

- **Spec SSOT 우선순위:** 무스크롤·partition·density는 `SPEC-UI-007` > `SPEC-UI-006` > `SPEC-UI-005`.
- **API·집계 불변:** `daily_dashboard.py` 응답 스키마 변경 금지.
- **Zone C 스크롤 금지:** `.dash__systems`에 `overflow: auto|scroll`·`data-scrollable="true"` 금지.
- **한국어 UI 문자열 불변.**
- **Windows `.sh`:** `bash <path>.sh` 형태만 사용.
- **검증:** `python3 -m pytest tests/test_dashboard_viewport.py tests/test_dashboard_fragments_http.py -q` + `python3 -m pytest tests/test_spec_traceability.py -q`
- **PR 전 (선택):** `python3 scripts/ci/run_all_gates.py --profile full`
- **Tier 알고리즘 결정:** naive `row_h >= 72 ? comfortable` 단일 분기로 **코드를 되돌리지 않는다** — 1280×720에서 콘텐츠 오버플로우가 재발함. **스펙을 구현에 맞춘다.**

---

## File Map

| File | Action | Responsibility |
| --- | --- | --- |
| `app/web/static/dashboard.js` | Verify (no change expected) | `TIER_MIN_H`, `pickTierForRowH`, `fitAndPartition`, `syncRowPartition` |
| `app/web/static/dashboard.css` | Verify (committed in Task 1) | `inset box-shadow` accent, partition-safe frame |
| `app/web/templates/dashboard.html` | Verify (committed in Task 1) | cache bust `css?v=7`, `js?v=22` |
| `docs/specs/dashboard/07-viewport-fit-no-scroll.md` | **Modify** | §3.4 알고리즘 SSOT, AC-008 accent, NFR cache bust, §9 테스트 표 |
| `docs/specs/dashboard/05-hierarchy-polish.md` | **Modify** | AC-005/006/009 superseded, §6 폐기 표 확장 |
| `tests/test_dashboard_viewport.py` | **Modify** | UI-007 AC-001/006 태그, AC-006·AC-008 신규 테스트 |
| `tests/test_dashboard_fragments_http.py` | **Modify** | AC-009 태그 → UI-007 AC-008 |

**Do not touch:** fragment templates, `daily_dashboard.py`, `base.html`.

---

## Interfaces (cross-task contract)

```javascript
// dashboard.js — 이미 구현됨, Task 2 문서화 대상
const TIER_ORDER = ["comfortable", "compact", "dense", "minimal", "micro"];
const TIER_MIN_H = { comfortable: 92, compact: 83, dense: 70, minimal: 56, micro: 50 };

function pickTierForRowH(rowH) → tier   // largest tier where TIER_MIN_H[tier] <= rowH - 2
function containerFits(container) → boolean  // scrollHeight <= clientHeight + 1
function fitAndPartition(container, n) → void  // tier pick + containerFits upgrade loop (max 4)
function syncRowPartition(container, n, gapHint) → void  // measure + ±4px correction
```

**Superseded mapping:**

| UI-005 AC | UI-007 AC | 비고 |
| --- | --- | --- |
| AC-005 Zone C scroll | AC-001 + AC-002 | 문서·Zone C 무스크롤 |
| AC-006 card height bounds | AC-003 | 균등 분할 모델로 대체 |
| AC-009 border-left accent | AC-008 (신규) | inset box-shadow |

---

### Task 1: Commit partition/inset WIP

**Files:**
- Stage: `app/web/static/dashboard.js`, `app/web/static/dashboard.css`, `app/web/templates/dashboard.html`, `docs/specs/dashboard/07-viewport-fit-no-scroll.md` (§3.3 구현 노트만 — Task 2에서 §3.4 대폭 수정 예정이면 Task 1 커밋에 §3.3 노트 포함 가능)

**Interfaces:**
- Produces: clean working tree baseline for docs/test tasks

- [ ] **Step 1: Confirm working tree matches intended partition fix**

Run:

```bash
git status
git diff app/web/static/dashboard.js app/web/static/dashboard.css app/web/templates/dashboard.html
```

Expected: `measureFlexColumnGap`, `measurePartitionSum`, `distributeRowHeights`, `applyRowFlexBasis`, rewritten `syncRowPartition`; CSS `inset box-shadow` on `.dash-sys-row`; cache bust `dashboard.css?v=7`, `dashboard.js?v=22`.

- [ ] **Step 2: Run partition regression tests**

Run:

```bash
python3 -m pytest tests/test_dashboard_viewport.py::test_system_rows_equal_partition_1280x720 tests/test_dashboard_viewport.py::test_dashboard_zone_c_fits_without_scroll -v
```

Expected: **PASS**

- [ ] **Step 3: Stage and commit (user requests commit)**

```bash
git add app/web/static/dashboard.js app/web/static/dashboard.css app/web/templates/dashboard.html docs/specs/dashboard/07-viewport-fit-no-scroll.md
git commit -m "$(cat <<'EOF'
fix(dashboard): SPEC-UI-007 partition fill and inset card frame

Measure flex gap and correct row heights after apply so sum(heights)+gaps
matches Zone C clientHeight within ±4px. Use inset box-shadow instead of
border to avoid partition AC-003 regression.
EOF
)"
```

- [ ] **Step 4: Verify clean tree**

Run: `git status`

Expected: working tree clean (except plan file from this session until Task 5 commit).

---

### Task 2: UI-007 §3.4 — TIER_MIN_H + containerFits SSOT 갱신

**Files:**
- Modify: `docs/specs/dashboard/07-viewport-fit-no-scroll.md` §3.4, §8 NFR, §9, §11

**Interfaces:**
- Consumes: `app/web/static/dashboard.js` (`TIER_MIN_H`, `fitAndPartition`, `pickTierForRowH`)
- Produces: spec text that matches runtime tier selection

- [ ] **Step 1: Replace §3.4 algorithm block**

`docs/specs/dashboard/07-viewport-fit-no-scroll.md` §3.4에서 기존 단일 `row_h >= 72` 분기 코드 블록을 아래로 **교체**:

```markdown
### 3.4 Density tier — content budget + row_h (SSOT)

`ResizeObserver` → `#dash-zone-matrix`(= `.dash__systems`)에 `data-density` 설정.

**1단계 — row_h 계산 (tier 후보):**

```javascript
const gap = readContainerGapPx(container);
const rowH = (container.clientHeight - gap * Math.max(0, n - 1)) / Math.max(n, 1);
```

**2단계 — 콘텐츠 예산으로 초기 tier (`pickTierForRowH`):**

각 tier가 한 행에 필요로 하는 **최소 콘텐츠 높이(px)**:

| tier | `TIER_MIN_H` |
| --- | --- |
| comfortable | 92 |
| compact | 83 |
| dense | 70 |
| minimal | 56 |
| micro | 50 |

```javascript
const TIER_ORDER = ["comfortable", "compact", "dense", "minimal", "micro"];
function pickTierForRowH(rowH) {
  for (const tier of TIER_ORDER) {
    if (TIER_MIN_H[tier] <= rowH - 2) return tier;
  }
  return "micro";
}
```

`rowH - 2`는 partition 반올림 여유(≤2px spread)이다.

**3단계 — overflow 시 tier 상향 (`containerFits` 루프):**

```javascript
function containerFits(container) {
  return container.scrollHeight <= container.clientHeight + 1;
}
// fitAndPartition: applyDensityLayout 후 containerFits false이면
// tierIdx += 1 (최대 4회) — 스크롤 대신 더 압축된 tier 적용
```

**4단계 — CSS tier 밴드 (표시·스타일 참조용):**

| tier | 대표 row_h 밴드 | Zone C UI |
| --- | --- | --- |
| comfortable | ≥ 72px | segment + chip labels |
| compact | 56–71px | segment 3px, chip ellipsis |
| dense | 44–55px | segment 숨김 |
| minimal | 32–43px | chips → dots |
| micro | < 32px | dots only, summary 숨김 |

> **참고:** 2단계 `TIER_MIN_H`가 4단계 row_h 밴드보다 **보수적**이다. 동일 row_h에서도 콘텐츠가 넘치면 3단계가 tier를 한 단계 더 내린다.
```

- [ ] **Step 2: Update FR-003 compress ladder bullet 1**

§4 FR-003 1번 항목을 다음으로 수정:

```markdown
1. density tier 하향 — `pickTierForRowH(row_h)` + `containerFits` 상향 루프 (comfortable → micro)
```

- [ ] **Step 3: Relax NFR-001 and fix cache bust NFR-002**

§8 표:

```markdown
| NFR-001 | density 파이프라인(`fitAndPartition` + helpers) 단일 모듈 유지 — 임의 30줄 제한 폐기 |
| NFR-002 | `dashboard.css?v=7`, `dashboard.js?v=22` cache bust (`dashboard.html`과 동기) |
```

- [ ] **Step 4: Add §11 changelog row**

```markdown
| 2026-08-16 | §3.4 TIER_MIN_H + containerFits SSOT; AC-008 accent 이관 | AI |
```

- [ ] **Step 5: Verify no code change needed**

Run:

```bash
python3 -m pytest tests/test_dashboard_viewport.py -q --tb=no
```

Expected: all passed (docs-only task).

- [ ] **Step 6: Commit**

```bash
git add docs/specs/dashboard/07-viewport-fit-no-scroll.md
git commit -m "$(cat <<'EOF'
docs(dashboard): align SPEC-UI-007 §3.4 with TIER_MIN_H tier pipeline

Document content-budget tier pick and containerFits upgrade loop as SSOT
instead of naive row_h threshold-only algorithm.
EOF
)"
```

---

### Task 3: UI-005 superseded AC 표기 + §6 폐기 표 확장

**Files:**
- Modify: `docs/specs/dashboard/05-hierarchy-polish.md` §6, §7 AC-005/006/009

**Interfaces:**
- Produces: superseded banners on UI-005 AC bodies

- [ ] **Step 1: Extend §6 deprecation table**

`docs/specs/dashboard/05-hierarchy-polish.md` §6 표 하단에 추가:

```markdown
| AC-005 Zone C `overflow-y: auto` | **폐기** → `SPEC-UI-007` AC-001·AC-002 |
| AC-006 콘텐츠 기반 행 높이 88–120px | **폐기** → `SPEC-UI-007` AC-003 균등 분할 |
| AC-009 `border-left-width: 3px` accent | **폐기** → `SPEC-UI-007` AC-008 inset box-shadow |
| §3.4 `data-scrollable` + fade mask | **폐기** → `SPEC-UI-007` |
| FR-004 Zone C 내부 스크롤 | **폐기** → `SPEC-UI-007` FR-001 |
```

- [ ] **Step 2: Add superseded banner to AC-005**

AC-005 제목 바로 아래 삽입:

```markdown
> **SUPERSEDED by `SPEC-UI-007` AC-001·AC-002** — Zone C 내부 스크롤·`data-scrollable` 폐기. 아래 Gherkin은 역사 기록용.
```

- [ ] **Step 3: Add superseded banner to AC-006**

```markdown
> **SUPERSEDED by `SPEC-UI-007` AC-003** — 균등 분할 모델로 대체. 아래 Gherkin은 역사 기록용.
```

- [ ] **Step 4: Add superseded banner to AC-009**

```markdown
> **SUPERSEDED by `SPEC-UI-007` AC-008** — `border-left` 대신 inset `box-shadow` accent. 아래 Gherkin은 역사 기록용.
```

- [ ] **Step 5: Commit**

```bash
git add docs/specs/dashboard/05-hierarchy-polish.md
git commit -m "$(cat <<'EOF'
docs(dashboard): mark SPEC-UI-005 AC-005/006/009 superseded by UI-007

Add superseded banners and extend §6 deprecation table for SDD traceability.
EOF
)"
```

---

### Task 4: pytest `@pytest.mark.spec` 태그 UI-007로 교체

**Files:**
- Modify: `tests/test_dashboard_viewport.py:285-306`

**Interfaces:**
- Consumes: Task 3 superseded mapping

- [ ] **Step 1: Replace misleading UI-005 AC-005 tags**

`tests/test_dashboard_viewport.py`에서 아래 3개 테스트의 데코레이터를 변경:

**Before:**

```python
@pytest.mark.spec("SPEC-UI-004", "AC-001")
@pytest.mark.spec("SPEC-UI-005", "AC-005")
```

**After (`test_dashboard_no_scroll_mobile`):**

```python
@pytest.mark.spec("SPEC-UI-004", "AC-001")
@pytest.mark.spec("SPEC-UI-007", "AC-001")
@pytest.mark.spec("SPEC-UI-007", "AC-002")
```

**After (`test_dashboard_no_scroll_1280x720`):**

```python
@pytest.mark.spec("SPEC-UI-004", "AC-002")
@pytest.mark.spec("SPEC-UI-007", "AC-001")
@pytest.mark.spec("SPEC-UI-007", "AC-002")
```

**After (`test_dashboard_no_scroll_1920x1080`):**

```python
@pytest.mark.spec("SPEC-UI-004", "AC-003")
@pytest.mark.spec("SPEC-UI-007", "AC-001")
@pytest.mark.spec("SPEC-UI-007", "AC-002")
```

- [ ] **Step 2: Run viewport + traceability tests**

Run:

```bash
python3 -m pytest tests/test_dashboard_viewport.py tests/test_spec_traceability.py -q
```

Expected: all passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_dashboard_viewport.py
git commit -m "$(cat <<'EOF'
test(dashboard): retag no-scroll tests to SPEC-UI-007 AC-001/002

Remove misleading SPEC-UI-005 AC-005 markers superseded by viewport-fit SSOT.
EOF
)"
```

---

### Task 5: UI-007 AC-006 Playwright 테스트 추가

**Files:**
- Modify: `tests/test_dashboard_viewport.py` (append after `test_no_data_scrollable_dataset`)
- Modify: `docs/specs/dashboard/07-viewport-fit-no-scroll.md` §9 테스트 표 (AC-006 행에 테스트명 명시)

**Interfaces:**
- Consumes: `_load_dashboard_and_assert_no_scroll` pattern, `_wait_for_density_stable`

- [ ] **Step 1: Write failing test (red check — should pass immediately if impl OK)**

`tests/test_dashboard_viewport.py`에 추가:

```python
@pytest.mark.spec("SPEC-UI-007", "AC-006")
def test_density_downgrades_on_resize_to_568(page, live_server: str) -> None:
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{live_server}/")
    page.wait_for_selector("#dash-zone-matrix[data-system-count='6']", timeout=15000)
    _wait_for_density_stable(page)
    density_tall = page.evaluate(
        "() => document.querySelector('.dash__systems')?.dataset.density || ''"
    )
    assert density_tall in ("comfortable", "compact"), density_tall

    page.set_viewport_size({"width": 1920, "height": 568})
    page.wait_for_function(
        """() => {
            const d = document.querySelector('.dash__systems')?.dataset.density || '';
            return ['dense', 'minimal', 'micro'].includes(d);
        }""",
        timeout=20000,
    )
    _wait_for_density_stable(page)

    metrics = page.evaluate(
        """() => {
            const sys = document.querySelector('.dash__systems');
            const de = document.documentElement;
            return {
                density: sys?.dataset.density || '',
                docOk: de.scrollHeight <= window.innerHeight + 1,
                zoneOk: sys && sys.scrollHeight <= sys.clientHeight + 1,
                overflowY: sys ? getComputedStyle(sys).overflowY : '',
            };
        }"""
    )
    assert metrics["density"] in ("dense", "minimal", "micro"), metrics
    assert metrics["docOk"], metrics
    assert metrics["zoneOk"], metrics
    assert metrics["overflowY"] == "hidden", metrics
```

- [ ] **Step 2: Run new test**

Run:

```bash
python3 -m pytest tests/test_dashboard_viewport.py::test_density_downgrades_on_resize_to_568 -v
```

Expected: **PASS**

- [ ] **Step 3: Update spec §9 table**

`docs/specs/dashboard/07-viewport-fit-no-scroll.md` §9:

```markdown
| Playwright | `tests/test_dashboard_viewport.py` | AC-001~008; `test_density_downgrades_on_resize_to_568` = AC-006 |
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_dashboard_viewport.py docs/specs/dashboard/07-viewport-fit-no-scroll.md
git commit -m "$(cat <<'EOF'
test(dashboard): add SPEC-UI-007 AC-006 resize density Playwright test

Assert tier downgrades to dense/minimal/micro at 1920x568 with no scroll.
EOF
)"
```

---

### Task 6: UI-005 AC-009 → UI-007 AC-008 accent 이관

**Files:**
- Modify: `docs/specs/dashboard/07-viewport-fit-no-scroll.md` §7 (AC-008 insert before AC-007 or renumber — **AC-008 신규, AC-007 유지**)
- Modify: `tests/test_dashboard_fragments_http.py`
- Modify: `tests/test_dashboard_viewport.py` (Playwright accent test)

**Interfaces:**
- Produces: `SPEC-UI-007 AC-008` gherkin + tests

- [ ] **Step 1: Add UI-007 AC-008 to spec (after AC-006, before AC-007)**

`docs/specs/dashboard/07-viewport-fit-no-scroll.md` §7에 삽입:

```markdown
### AC-008: Attention accent inset (UI-005 AC-009 이관)

```gherkin
Given system with representative badge tone "error" (e.g. hom)
When dashboard matrix loaded at 1280×720
Then its ".dash-sys-row" has data-priority "attention"
  And computed box-shadow contains "inset" and "3px"
  And box-shadow does not use border-left for accent (border-width 0 or border none)
```
```

§3.3 구현 노트와 교차 참조 유지.

- [ ] **Step 2: Retag fragment test**

`tests/test_dashboard_fragments_http.py`:

```python
@pytest.mark.spec("SPEC-UI-007", "AC-008")
@pytest.mark.spec("SPEC-UI-005", "AC-009")  # historical — optional; prefer UI-007 only
def test_matrix_fragment_error_system_has_attention_priority(client: TestClient) -> None:
```

**권장:** UI-005 태그 제거, UI-007 AC-008만 유지.

- [ ] **Step 3: Add Playwright accent computed-style test**

`tests/test_dashboard_viewport.py`:

```python
@pytest.mark.spec("SPEC-UI-007", "AC-008")
def test_attention_row_inset_accent_1280x720(page, live_server: str) -> None:
    _load_dashboard_1280x720(page, live_server)
    result = page.evaluate(
        """() => {
            const row = document.querySelector('.dash-sys-row[data-system-code="hom"]');
            if (!row) return { ok: false, reason: 'no hom row' };
            const cs = getComputedStyle(row);
            const shadow = cs.boxShadow || '';
            const borderLeft = cs.borderLeftWidth;
            return {
                ok: row.dataset.priority === 'attention'
                    && shadow.includes('inset')
                    && shadow.includes('3px')
                    && (borderLeft === '0px' || cs.borderStyle === 'none'),
                priority: row.dataset.priority,
                boxShadow: shadow,
                borderLeftWidth: borderLeft,
            };
        }"""
    )
    assert result["ok"], result
```

- [ ] **Step 4: Run accent + fragment tests**

Run:

```bash
python3 -m pytest tests/test_dashboard_viewport.py::test_attention_row_inset_accent_1280x720 tests/test_dashboard_fragments_http.py::test_matrix_fragment_error_system_has_attention_priority -v
```

Expected: **PASS**

- [ ] **Step 5: Full dashboard test suite**

Run:

```bash
python3 -m pytest tests/test_dashboard_viewport.py tests/test_dashboard_fragments_http.py tests/test_spec_traceability.py -q
```

Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add docs/specs/dashboard/07-viewport-fit-no-scroll.md tests/test_dashboard_viewport.py tests/test_dashboard_fragments_http.py
git commit -m "$(cat <<'EOF'
docs(test): migrate attention accent AC to SPEC-UI-007 AC-008

Add inset box-shadow Playwright assert; retag fragment test from UI-005 AC-009.
EOF
)"
```

---

## Self-Review

| Spec requirement | Task |
| --- | --- |
| 1. partition/inset 커밋 | Task 1 |
| 2. UI-007 §3.4 TIER_MIN_H SSOT | Task 2 |
| 3. UI-005 superseded AC + pytest tags | Task 3 + Task 4 |
| 4. UI-007 AC-006 Playwright | Task 5 |
| 5. UI-005 AC-009 → UI-007 accent | Task 6 |
| §3.3 syncRowPartition ±4px | Task 1 (already implemented) |
| API 불변 | no tasks touch API |
| Zone C no scroll | regression via Tasks 4–6 tests |

**Placeholder scan:** none.

**Risk:** `test_density_downgrades_on_resize_to_568` assumes 1920×1080 starts at `comfortable` or `compact`. If fixture data yields `dense` at 1080p, relax assertion to `not in ("", "micro")` only for tall state — document in test comment if flaky.

---

## Definition of Done

- [ ] Task 1: partition/inset committed; `test_system_rows_equal_partition_1280x720` PASS
- [ ] Task 2: UI-007 §3.4 documents `TIER_MIN_H` + `containerFits`; NFR cache bust updated
- [ ] Task 3: UI-005 AC-005/006/009 superseded banners + §6 table
- [ ] Task 4: no `SPEC-UI-005 AC-005` on no-scroll tests; UI-007 AC-001/002 tagged
- [ ] Task 5: `test_density_downgrades_on_resize_to_568` PASS
- [ ] Task 6: UI-007 AC-008 spec + Playwright + fragment retag PASS
- [ ] `python3 -m pytest tests/test_dashboard_viewport.py tests/test_dashboard_fragments_http.py tests/test_spec_traceability.py -q` green

---

## Commit Summary (expected 5 commits)

1. `fix(dashboard): SPEC-UI-007 partition fill and inset card frame`
2. `docs(dashboard): align SPEC-UI-007 §3.4 with TIER_MIN_H tier pipeline`
3. `docs(dashboard): mark SPEC-UI-005 AC-005/006/009 superseded by UI-007`
4. `test(dashboard): retag no-scroll tests to SPEC-UI-007 AC-001/002`
5. `test(dashboard): add SPEC-UI-007 AC-006 resize density test`
6. `docs(test): migrate attention accent AC to SPEC-UI-007 AC-008`

(Task 5+6 can squash to one commit if preferred: `test(dashboard): UI-007 AC-006/008 Playwright coverage`)
