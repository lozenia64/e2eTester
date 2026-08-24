# Cycle 0: 상태 팔레트 통일 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 같은 상태가 화면마다 다른 색으로 보이는 것을 없앤다 — 상태 색이 전 화면에서 `app/core/status_colors.py` 의 `PALETTE` 하나로 수렴한다.

**Architecture:** 인라인 `<style>` 을 든 템플릿 7개가 `--st-passed` 같은 **짧은 이름**을 각자 정의하고 있다. 이름은 SSOT 와 같은데 값이 다르다. 그런데 SSOT(`tokens.generated.css`)가 내보내는 것은 `--st-passed-solid` 이지 `--st-passed` 가 아니므로, 정의를 지우기만 하면 색이 상속되는 것이 아니라 **사라진다.** 따라서 짧은 이름을 SSOT 토큰으로 이어 붙이는 한시적 별칭 파일을 신설하고, 템플릿에서는 정의만 지운다. 사용처 약 51곳은 건드리지 않는다. 마지막으로 이 사각지대가 다시 생기지 않도록 FG-002 의 스캔 범위를 `templates/` 와 `static/*.js` 까지 넓힌다.

**Tech Stack:** CSS 커스텀 프로퍼티, Vite(다중 엔트리), Jinja2 템플릿, pytest, 자체 게이트 스크립트(`scripts/check_frontend_gates.py`)

**Spec:** `docs/superpowers/specs/2026-08-24-execute-promotion-design.md` (§1.1 문제 · §4.1 Cycle 0 · D9 · D10)

## Global Constraints

- **색 SSOT 는 `app/core/status_colors.py` 의 `PALETTE`.** 어떤 파일도 상태 색 hex 를 새로 적지 않는다. 이 계획에서 hex 를 **추가**하는 단계는 없다.
- **톤 목록 SSOT 는 `app/core/status_labels.py` 의 `STATUS_TONES`** — `passed · anomaly · error · running · waiting_input · blocked · skipped · cancelled · pending` 9종. `idle` · `not_inspected` · `not_checked` 는 톤이 **아니다.**
- **UI·로그·README 문자열은 한국어**(AGENTS.md).
- **`app/web/frontend/styles/tokens.generated.css` 는 자동 생성물** — 직접 수정 금지. 출처는 `scripts/gen_frontend_tokens.py`.
- **화면 마크업과 `var(--…)` 사용처는 이 사이클에서 건드리지 않는다.** 예외는 Task 2 의 `admin/index.html:203` 두 줄뿐이며, 그 이유는 해당 자리가 전경색이 아니라 배경이라 별칭 하나로 덮이지 않기 때문이다.
- **PR 전 필수:** `python3 scripts/ci/run_all_gates.py --profile full`
- Windows 셸에서 `.sh` 실행 시 `bash <path>.sh`.

## File Structure

| 파일 | 책임 | 상태 |
| --- | --- | --- |
| `app/web/frontend/styles/legacy-aliases.css` | 짧은 상태 이름 → SSOT 토큰 별칭. 소멸 조건을 자기 안에 적는다 | **신규** |
| `app/web/frontend/styles/base.css` | 전역 CSS 임포트 체인 | 수정(1줄 추가) |
| `app/web/templates/{anomalies,insights,presets,schedules,self_healing}.html` | 화면별 인라인 스타일 | 수정(토큰 정의만 삭제) |
| `app/web/templates/admin/{index,runs}.html` | 관리자 화면 인라인 스타일 | 수정(정의 삭제 + `index` 히트맵 배경 2줄) |
| `app/web/static/admin-runs.js` | 관리자 Run 이력 화면 스크립트 | 수정(Chart.js 색 4개) |
| `app/web/static/admin-dashboard.js` | 관리자 대시보드 스크립트 | 수정(중복 hex 1개 제거) |
| `scripts/check_frontend_gates.py` | 프론트엔드 게이트 FG-001~007 | 수정(FG-002 범위 확장) |
| `tests/frontend/test_legacy_aliases.py` | 별칭이 실재하는 SSOT 토큰을 가리키는지 | **신규** |
| `tests/frontend/test_status_palette_single_source.py` | 템플릿·레거시 JS 에 로그 팔레트가 없는지 | **신규** |
| `tests/frontend/test_frontend_gates.py` | 게이트 단위 테스트 | 수정(FG-002 케이스 추가) |
| `docs/CI.md` | 게이트 목록 문서 | 수정(FG-002 설명 1줄) |

---

### Task 1: 별칭 파일 신설

짧은 이름을 SSOT 토큰으로 이어 붙인다. **이 태스크만으로는 화면이 바뀌지 않는다** — 템플릿의 로그 정의가 아직 살아 있어 더 좁은 스코프(`.inbox` 등)로 이기기 때문이다. Task 2 가 그 정의를 지우면 이 별칭이 드러난다.

**Files:**
- Create: `app/web/frontend/styles/legacy-aliases.css`
- Modify: `app/web/frontend/styles/base.css`
- Test: `tests/frontend/test_legacy_aliases.py`

**Interfaces:**
- Consumes: `app/web/frontend/styles/tokens.generated.css` 의 `--st-{tone}-solid` (tone ∈ `STATUS_TONES`), `app/web/frontend/styles/primitives.css` 의 `--c-gray-200` · `--c-indigo-600` · `--ease-out`
- Produces: 전역 `:root` 에 `--st-passed` · `--st-anomaly` · `--st-error` · `--st-running` · `--st-cancelled` · `--st-blocked` · `--st-idle` · `--st-track` · `--st-active` · `--ease-spring` 10개. Task 2 가 템플릿 정의를 지운 뒤 이 값들이 실효를 갖는다

- [x] **Step 1: 실패하는 테스트를 쓴다**

`tests/frontend/test_legacy_aliases.py` 를 만든다.

```python
"""레거시 짧은 별칭이 실재하는 SSOT 토큰을 가리키는지.

별칭은 이름만 이어 붙인다. 대상 토큰이 사라지거나 이름이 바뀌면 `var()` 가
미정의가 되고, CSS 는 그 선언을 통째로 무효화한다 — 화면에서 색이 조용히
사라진다. 그 순간을 여기서 잡는다.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLES = REPO_ROOT / "app/web/frontend/styles"
ALIAS_CSS = STYLES / "legacy-aliases.css"
BASE_CSS = STYLES / "base.css"
SOURCES = (STYLES / "tokens.generated.css", STYLES / "primitives.css")

# `--이름: var(--대상);` — 별칭 선언만 잡는다.
_ALIAS_RE = re.compile(r"^\s*(--[\w-]+)\s*:\s*var\(\s*(--[\w-]+)\s*\)\s*;")
# `--이름:` — 정의 선언(값 종류 무관).
_DEFINE_RE = re.compile(r"^\s*(--[\w-]+)\s*:")


def _aliases() -> dict[str, str]:
    pairs = {}
    for line in ALIAS_CSS.read_text(encoding="utf-8").splitlines():
        match = _ALIAS_RE.match(line)
        if match:
            pairs[match.group(1)] = match.group(2)
    return pairs


def _defined_elsewhere() -> set[str]:
    names = set()
    for path in SOURCES:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _DEFINE_RE.match(line)
            if match:
                names.add(match.group(1))
    return names


def test_alias_file_exists() -> None:
    assert ALIAS_CSS.exists(), "legacy-aliases.css 가 없다"


def test_every_alias_target_is_defined() -> None:
    """대상 토큰이 사라지면 화면 색이 조용히 사라진다."""
    aliases = _aliases()
    assert aliases, "별칭 선언이 하나도 파싱되지 않았다"
    defined = _defined_elsewhere()
    dangling = {name: target for name, target in aliases.items() if target not in defined}
    assert not dangling, f"가리키는 토큰이 없는 별칭: {dangling}"


def test_alias_file_has_no_hex() -> None:
    """별칭 파일은 이어 붙이기만 한다 — 여기서 색을 새로 발명하면 SSOT 가 둘이 된다."""
    hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", ALIAS_CSS.read_text(encoding="utf-8"))
    assert not hexes, f"별칭 파일에 hex: {hexes}"


def test_status_aliases_point_at_solid_variants() -> None:
    """상태 별칭은 배지가 아니라 점·막대에 쓰이므로 solid 변형이어야 한다."""
    aliases = _aliases()
    for tone in ("passed", "anomaly", "error", "running", "cancelled", "blocked"):
        assert aliases[f"--st-{tone}"] == f"--st-{tone}-solid"


def test_base_css_imports_the_alias_file() -> None:
    """임포트가 빠지면 파일은 있는데 아무 화면에도 닿지 않는다."""
    text = BASE_CSS.read_text(encoding="utf-8")
    assert '@import "./legacy-aliases.css";' in text
```

- [x] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_legacy_aliases.py -v`
Expected: FAIL — `test_alias_file_exists` 가 `AssertionError: legacy-aliases.css 가 없다`, 나머지는 `FileNotFoundError`

- [x] **Step 3: 별칭 파일을 만든다**

`app/web/frontend/styles/legacy-aliases.css`:

```css
/* 레거시 화면이 쓰는 짧은 상태 별칭 — 한시적 파일.

   인라인 <style> 을 든 화면 7개가 `--st-passed` 같은 짧은 이름을 각자 정의하고
   있었다. 이름은 SSOT 와 같은데 값이 달라서(#0ca30c vs #10b981) 같은 상태가
   화면마다 다른 색으로 보였다.

   정의를 지우기만 하면 짧은 이름이 미정의가 되어 색이 사라진다 — SSOT 가
   내보내는 것은 `--st-passed-solid` 이지 `--st-passed` 가 아니다. 그래서
   여기서 이어 붙인다. 사용처(약 51곳)는 건드리지 않는다.

   소멸 조건: 화면별 승격 사이클이 인라인 <style> 을 컴포넌트 CSS 로 옮기면
   그 화면의 사용처가 사라진다. 마지막 화면이 끝나면 이 파일과 base.css 의
   @import 한 줄을 함께 지운다.

   현재 사용처: anomalies · insights · presets · schedules · self_healing
                · admin/index · admin/runs */
:root {
  --st-passed: var(--st-passed-solid);
  --st-anomaly: var(--st-anomaly-solid);
  --st-error: var(--st-error-solid);
  --st-running: var(--st-running-solid);
  --st-cancelled: var(--st-cancelled-solid);
  --st-blocked: var(--st-blocked-solid);

  /* STATUS_TONES 에 `idle` 은 없다. 의미가 "아직 점검하지 않음" 이므로
     pending 톤에 붙인다(설계 D10). */
  --st-idle: var(--st-pending-solid);

  /* 아래 둘은 애초에 상태색이 아니다 — 링·막대의 트랙 배경과 선택 강조인데
     이름만 --st-* 였다(설계 D10). */
  --st-track: var(--c-gray-200);
  --st-active: var(--c-indigo-600);

  /* 7벌 중복이던 이징. primitives.css 의 --ease-out 과 같은 곡선이다. */
  --ease-spring: var(--ease-out);
}
```

- [x] **Step 4: base.css 에 임포트를 넣는다**

`app/web/frontend/styles/base.css` 의 `@import "./tokens.generated.css";` 바로 다음 줄에 추가한다. 순서가 중요하다 — 별칭이 가리키는 토큰이 먼저 정의돼 있어야 한다.

```css
@import "tailwindcss";
@import "./primitives.css";
@import "./tokens.generated.css";
@import "./legacy-aliases.css";
@import "./app.css";
@import "./dashboard.css";
```

- [x] **Step 5: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/frontend/test_legacy_aliases.py -v`
Expected: PASS (5 passed)

- [x] **Step 6: 빌드가 깨지지 않는지 확인한다**

Run: `npm run build`
Expected: 성공. `app/web/static/dist/assets/main-*.css` 가 재생성된다.

- [x] **Step 7: 커밋**

```bash
git add app/web/frontend/styles/legacy-aliases.css app/web/frontend/styles/base.css tests/frontend/test_legacy_aliases.py
git commit -m "feat(styles): 레거시 짧은 상태 별칭을 SSOT 토큰에 연결"
```

---

### Task 2: 템플릿 7개의 로그 팔레트 정의 제거

Task 1 의 별칭이 실효를 갖게 하는 단계다. **여기서 화면 색이 실제로 바뀐다.**

**Files:**
- Modify: `app/web/templates/anomalies.html:9-13`, `app/web/templates/insights.html:9-15`, `app/web/templates/presets.html:9`, `app/web/templates/schedules.html:9-14`, `app/web/templates/self_healing.html:9-13`, `app/web/templates/admin/index.html:8-16`, `app/web/templates/admin/index.html:203`, `app/web/templates/admin/runs.html:8-12`
- Test: `tests/frontend/test_status_palette_single_source.py`

**Interfaces:**
- Consumes: Task 1 이 만든 전역 별칭 10개
- Produces: 템플릿에 상태 토큰 정의 0건. 이후 Task 4 의 FG-002 확장이 이 상태를 잠근다

- [x] **Step 1: 실패하는 테스트를 쓴다**

`tests/frontend/test_status_palette_single_source.py` 를 만든다.

```python
"""상태 팔레트가 하나인지 — 템플릿과 레거시 JS 에 사본이 없는지.

발견 당시 실측: 템플릿 7개가 `--st-passed` 등을 각자 정의했고, 값이 SSOT 와
달랐다(#0ca30c vs #10b981). 이름이 같아서 화면 안에서는 일관돼 보이고 화면을
넘어갈 때만 어긋난다 — 눈으로 잡기 가장 어려운 형태였다.

FG-002 는 hex 자체를 막는다(범위가 넓다). 이 테스트는 **상태 팔레트의 사본**
이라는 특정 병만 본다(범위가 좁고 메시지가 구체적이다). 둘 다 필요하다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.status_colors import PALETTE

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "app/web/templates"
STATIC_DIR = REPO_ROOT / "app/web/static"

# 화면들이 각자 정의하던 짧은 이름. `--st-passed:` 처럼 콜론이 붙은 정의만 잡는다
# (`var(--st-passed)` 사용처는 이 사이클의 대상이 아니다).
SHORT_TOKENS = (
    "--st-passed",
    "--st-anomaly",
    "--st-error",
    "--st-running",
    "--st-cancelled",
    "--st-blocked",
    "--st-idle",
    "--st-track",
    "--st-active",
    "--ease-spring",
)

# 발견 당시 로그 팔레트의 실제 값. 되살아나면 잡는다.
ROGUE_HEX = ("#0ca30c", "#fab219", "#d03b3b", "#2a78d6", "#ec835a", "#b6b4ad", "#ecebe6")


def _templates() -> list[Path]:
    return sorted(TEMPLATE_DIR.rglob("*.html"))


def _legacy_scripts() -> list[Path]:
    """static/ 최상위의 손으로 쓴 스크립트만. dist/ 는 빌드 산출물이라 제외한다."""
    return sorted(STATIC_DIR.glob("*.js"))


@pytest.mark.parametrize("token", SHORT_TOKENS)
def test_no_template_defines_a_short_status_token(token: str) -> None:
    pattern = re.compile(rf"^\s*{re.escape(token)}\s*:")
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno}"
        for path in _templates()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.match(line)
    ]
    assert not offenders, f"{token} 을 정의하는 템플릿: {offenders}"


@pytest.mark.parametrize("value", ROGUE_HEX)
def test_rogue_palette_value_is_gone(value: str) -> None:
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno}"
        for path in [*_templates(), *_legacy_scripts()]
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if value in line
    ]
    assert not offenders, f"로그 팔레트 값 {value}: {offenders}"


def test_ssot_values_are_not_copied_into_templates() -> None:
    """SSOT 값을 템플릿에 '올바르게' 베껴 넣는 것도 사본이다 — 다음 변경 때 갈라진다."""
    ssot_values = {variants["solid"] for variants in PALETTE.values()}
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno} {value}"
        for path in _templates()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for value in ssot_values
        if value in line
    ]
    assert not offenders, f"SSOT 색을 베낀 자리: {offenders}"
```

- [x] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_status_palette_single_source.py -v`
Expected: FAIL — `--st-passed` · `--st-anomaly` · `--st-error` · `--st-idle` · `--ease-spring` 등이 템플릿에서 검출되고, `#0ca30c` 등 로그 hex 도 검출된다. `test_ssot_values_are_not_copied_into_templates` 는 PASS 여야 한다(베낀 자리는 없다).

- [x] **Step 3: 템플릿 5개에서 정의를 지운다**

각 파일에서 **토큰 정의 줄만** 지운다. 셀렉터 블록 자체와 다른 선언은 남긴다.

`app/web/templates/anomalies.html` — `.inbox { … }` 안의 5줄을 지우고 빈 블록이 되므로 셀렉터까지 제거한다:

```jinja
{# 지우기 전 #}
  .inbox {
    --st-passed: #0ca30c;
    --st-anomaly: #fab219;
    --st-error: #d03b3b;
    --st-idle: #b6b4ad;
    --ease-spring: cubic-bezier(.22, 1, .36, 1);
  }
  .inbox-tone-anomaly { color: var(--st-anomaly); }

{# 지운 뒤 — 블록이 통째로 사라진다 #}
  .inbox-tone-anomaly { color: var(--st-anomaly); }
```

`self_healing.html` 의 `.heal { … }`, `presets.html` 의 `.prset { … }` 도 같은 형태다 — 정의만 들어 있으므로 블록째 사라진다.

`insights.html` 의 `.insight { … }` 와 `schedules.html` 의 `.schedc { … }` 도 정의만 들어 있으므로 블록째 사라진다. `schedules.html` 은 `--st-active` 가 포함된 6줄이다.

- [x] **Step 4: admin 템플릿 2개를 고친다**

`app/web/templates/admin/runs.html` — `.adm-runs { … }` 는 정의 5줄만 있으므로 블록째 제거한다.

`app/web/templates/admin/index.html` — `.adm-dash { … }` 는 레이아웃 변수 2개가 남으므로 **블록을 남기고 8줄만** 지운다:

```css
/* 지운 뒤 */
  .adm-dash {
    --adm-cell-size: 1.75rem;
    --adm-label-col: 8.5rem;
  }
```

같은 파일 `:203` 은 별칭 하나로 덮이지 않는다. `--st-idle` 은 전경(점·글자)용 `--st-pending-solid`(`#a1a1aa`)로 가는데, 이 자리는 히트맵 빈 칸의 **배경**이라 그 값이면 너무 어둡다. 배경·테두리 변형을 직접 쓴다:

```css
/* 바꾸기 전 */
  .adm-cell[data-tone="not_checked"] { background: var(--st-idle); border-color: #e5e7eb; }

/* 바꾼 뒤 — surface 는 배경, border 는 테두리용 변형이다 */
  .adm-cell[data-tone="not_checked"] { background: var(--st-pending-surface); border-color: var(--st-pending-border); }
```

`:375` 의 범례 점(`style="background:var(--st-idle)"`)은 전경이므로 별칭 그대로 둔다.

- [x] **Step 5: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/frontend/test_status_palette_single_source.py -v`
Expected: 템플릿 관련 전부 PASS. **`test_rogue_palette_value_is_gone[#0ca30c]` 등 4건은 아직 FAIL** — `admin-runs.js` 가 같은 hex 를 들고 있다(Task 3 이 처리).

- [x] **Step 6: 눈으로 확인한다**

Run: `npm run build`

그다음 앱을 띄워 `/anomalies` · `/insights` · `/schedules` · `/self-healing` · `/presets` 다섯 화면에서 상태 색이 **보이는지**(사라지지 않았는지) 확인한다. 실행 방법은 `docs/INSTALL.md`.

확인 항목: 녹색·주황·빨강이 각각 `#10b981` · `#f59e0b` · `#ef4444` 로 보이고, 어떤 요소도 색이 빠져 투명·검정으로 떨어지지 않는다.

- [x] **Step 7: 커밋**

```bash
git add app/web/templates tests/frontend/test_status_palette_single_source.py
git commit -m "fix(web): 템플릿 7개의 로그 상태 팔레트 제거 — SSOT 로 수렴"
```

---

### Task 3: 레거시 JS 의 상태 색을 SSOT 에서 읽는다

CSS 별칭이 닿지 않는 유일한 자리다 — Chart.js 는 JS 값으로 색을 받는다.

**Files:**
- Modify: `app/web/static/admin-runs.js:645-680`
- Modify: `app/web/static/admin-dashboard.js:75-79`
- Test: `tests/frontend/test_status_palette_single_source.py` (Task 2 에서 만든 것, 수정 없음)

**Interfaces:**
- Consumes: `:root` 에 정의된 `--st-{tone}-solid` (Task 1 의 별칭이 아니라 SSOT 토큰을 직접 읽는다 — 별칭은 소멸 예정이므로 새 코드가 의존하면 안 된다)
- Produces: 없음(내부 변경)

- [x] **Step 1: 실패를 다시 확인한다**

Run: `python3 -m pytest "tests/frontend/test_status_palette_single_source.py::test_rogue_palette_value_is_gone" -v`
Expected: FAIL 4건 — `#0ca30c` · `#fab219` · `#d03b3b` 이 `admin-runs.js` 에서, `#b6b4ad` 는 이미 통과

- [x] **Step 2: admin-runs.js 의 차트 색을 토큰에서 읽는다**

`app/web/static/admin-runs.js` 의 `state.trendChart = new Chart(...)` 블록 **위**에 헬퍼를 추가한다. 같은 파일 계열이 이미 쓰는 방식(`admin-dashboard.js:23` 의 `toneVar`)과 같은 모양이되, Chart.js 는 `var(...)` 문자열을 해석하지 못하므로 계산된 값을 넘긴다.

```javascript
  // Chart.js 는 CSS 변수를 해석하지 못한다 — 계산된 값을 넘겨야 한다.
  // 토큰은 tokens.generated.css 가 :root 에 싣는다(SSOT: app/core/status_colors.py).
  function statusSolid(tone) {
    const value = getComputedStyle(document.documentElement)
      .getPropertyValue(`--st-${tone}-solid`)
      .trim();
    return value || "transparent";
  }
```

그다음 데이터셋 4개의 `backgroundColor` 를 바꾼다:

```javascript
        datasets: [
          {
            label: "정상",
            data: trend.map((d) => d.passed),
            backgroundColor: statusSolid("passed"),
            stack: "status",
          },
          {
            label: "이상징후",
            data: trend.map((d) => d.anomaly),
            backgroundColor: statusSolid("anomaly"),
            stack: "status",
          },
          {
            label: "점검실패",
            data: trend.map((d) => d.error),
            backgroundColor: statusSolid("error"),
            stack: "status",
          },
          {
            label: "취소",
            data: trend.map((d) => d.cancelled),
            backgroundColor: statusSolid("cancelled"),
            stack: "status",
          },
        ],
```

- [x] **Step 3: admin-dashboard.js 의 중복 분기를 지운다**

`app/web/static/admin-dashboard.js:75-79` 의 `systemDotColor` 는 `not_checked` 를 특별 취급하는데, `TONE_VARS` (`:21`)가 이미 `not_checked: "var(--st-idle)"` 를 담고 있어 결과가 같다. `#9ca3af` 리터럴만 남기는 죽은 분기다.

```javascript
/* 바꾸기 전 */
  function systemDotColor(tone) {
    if (tone === "not_checked") return "var(--st-idle)";
    if (tone === "passed") return "var(--st-passed)";
    return toneVar(tone);
  }

/* 바꾼 뒤 — TONE_VARS 가 세 경우를 모두 담고 있다 */
  function systemDotColor(tone) {
    return toneVar(tone);
  }
```

`:175` 의 `const color = tone === "not_checked" ? "#9ca3af" : toneVar(tone);` 도 같은 이유로 `const color = toneVar(tone);` 로 줄인다.

- [x] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/frontend/test_status_palette_single_source.py -v`
Expected: PASS (전부)

- [x] **Step 5: 차트를 눈으로 확인한다**

앱을 admin 계정으로 띄워 `/admin/runs` 의 추이 막대 차트가 **색을 갖는지** 확인한다. `statusSolid` 가 빈 문자열을 받으면 막대가 투명해지므로, 색이 보이면 토큰 해석이 성공한 것이다.

확인 근거(사용자 제공, 2026-08-24): `main-BWo2x1nu.css`에 `--st-passed-solid:#10b981`·`--st-anomaly-solid:#f59e0b`·`--st-error-solid:#ef4444`·`--st-cancelled-solid:#71717a`가 `:root` SSOT 값으로 실려 있어 `statusSolid()`의 빈 문자열 fallback은 발생하지 않는다.

- [x] **Step 6: 커밋**

```bash
git add app/web/static/admin-runs.js app/web/static/admin-dashboard.js
git commit -m "fix(web): 레거시 차트 색을 상태 토큰에서 읽도록"
```

---

### Task 4: FG-002 스캔 범위를 templates/ · static/*.js 로 확장

사각지대를 닫는다. 이것이 없으면 다음 화면이 같은 사본을 다시 만든다.

**Files:**
- Modify: `scripts/check_frontend_gates.py`
- Test: `tests/frontend/test_frontend_gates.py`

**Interfaces:**
- Consumes: 기존 `_iter` · `_rel` · `_HEX` · `GENERATED_FILES`
- Produces: `FG002_ALLOWLIST` (문자열 집합, 저장소 상대경로). 이후 사이클이 화면을 승격할 때마다 한 줄씩 지운다

- [x] **Step 1: 실패하는 테스트를 쓴다**

`tests/frontend/test_frontend_gates.py` 의 FG-002 섹션에 추가한다. 기존 `_write(root, rel, text)` 헬퍼를 그대로 쓴다.

```python
def test_fg002_flags_hex_in_template(tmp_path):
    """templates/ 는 어떤 색 게이트도 보지 않던 사각지대였다."""
    _write(tmp_path, "app/web/templates/x.html", "<style>.a { color: #0ca30c; }</style>")
    problems = check_fg002_no_hex(tmp_path)
    assert len(problems) == 1
    assert "#0ca30c" in problems[0]


def test_fg002_flags_hex_in_legacy_script(tmp_path):
    _write(tmp_path, "app/web/static/legacy.js", 'const c = "#d03b3b";')
    problems = check_fg002_no_hex(tmp_path)
    assert len(problems) == 1
    assert "#d03b3b" in problems[0]


def test_fg002_ignores_built_bundles(tmp_path):
    """static/dist 는 빌드 산출물이다 — 우리가 쓴 코드가 아니다."""
    _write(tmp_path, "app/web/static/dist/assets/main-abc.js", 'var x="#123456";')
    assert check_fg002_no_hex(tmp_path) == []


def test_fg002_allows_theme_color_meta(tmp_path):
    """<meta name="theme-color"> 는 CSS 변수를 쓸 수 없다 — 브라우저가 리터럴로 읽는다.

    파일 allowlist 로 처리하면 base.html·admin/base.html·login.html 이 영구
    항목으로 남아 "allowlist 가 비면 완성" 전제가 깨진다(FG-006 이 겪은 실패).
    """
    _write(
        tmp_path,
        "app/web/templates/base.html",
        '<meta name="theme-color" content="#4f46e5">',
    )
    assert check_fg002_no_hex(tmp_path) == []


def test_fg002_allowlisted_template_is_skipped(tmp_path):
    import scripts.check_frontend_gates as gates

    _write(tmp_path, "app/web/templates/insights.html", "<style>.a { color: #123456; }</style>")
    original = gates.FG002_ALLOWLIST
    gates.FG002_ALLOWLIST = {"app/web/templates/insights.html"}
    try:
        assert check_fg002_no_hex(tmp_path) == []
    finally:
        gates.FG002_ALLOWLIST = original


def test_fg002_allowlist_only_holds_files_that_still_have_hex():
    """유예 목록이 실효를 잃은 줄을 품고 있으면 '비면 완성' 신호가 거짓이 된다."""
    import re

    import scripts.check_frontend_gates as gates

    stale = []
    for rel in gates.FG002_ALLOWLIST:
        path = gates.REPO_ROOT / rel
        assert path.exists(), f"allowlist 가 없는 파일을 가리킨다: {rel}"
        if not re.search(r"#[0-9a-fA-F]{3,8}\b", path.read_text(encoding="utf-8")):
            stale.append(rel)
    assert not stale, f"hex 가 남아 있지 않은 allowlist 항목 — 지우세요: {stale}"
```

- [x] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_frontend_gates.py -k fg002 -v`
Expected: FAIL — 새 테스트 5건이 `AttributeError: module has no attribute 'FG002_ALLOWLIST'` 또는 `assert len(problems) == 1` 에서 `0 == 1`

- [x] **Step 3: 게이트를 고친다**

`scripts/check_frontend_gates.py` 상단, `MAIL_RENDERER` 정의 아래에 추가한다:

```python
STATIC_DIR = "app/web/static"
```

`FG005_ALLOWLIST` 블록 **위**에 유예 목록을 추가한다:

```python
# FG-002 가 templates/ · static/*.js 까지 보게 되며 생긴 유예 목록.
# 인라인 <style> 에 색 리터럴을 든 화면들이다(실측 277건). 화면별 승격
# 사이클이 인라인 스타일을 컴포넌트 CSS 로 옮길 때마다 여기서 한 줄씩
# 지운다. 비면 FG-002 가 완성된다.
FG002_ALLOWLIST = {
    "app/web/templates/admin/runs.html",
    "app/web/templates/admin/index.html",
    "app/web/templates/schedules.html",
    "app/web/templates/mobile_trigger.html",
    "app/web/templates/self_healing.html",
    "app/web/templates/insights.html",
    "app/web/templates/presets.html",
    "app/web/templates/anomalies.html",
}
```

`_MAIL_STATUS_CONST_RE` 아래에 예외 규칙을 추가한다:

```python
# <meta name="theme-color" content="#4f46e5"> 는 CSS 변수를 쓸 수 없다 —
# 브라우저가 문서 헤드에서 리터럴 색으로 읽는다. 파일 allowlist 로 처리하면
# base.html·admin/base.html·login.html 이 영구 항목이 되어 "allowlist 가
# 비면 완성" 전제가 깨진다(FG-006 이 그 실패를 겪었다). 규칙에서 제외한다.
_THEME_COLOR_META = re.compile(r"""<meta\s+name=["']theme-color["']""", re.IGNORECASE)
```

`_iter_component_markup` 아래에 최상위 스크립트 순회기를 추가한다:

```python
def _iter_legacy_scripts(root: Path):
    """static/ **최상위**의 손으로 쓴 스크립트만.

    rglob 을 쓰면 static/dist/ 의 빌드 산출물(plotly 4.6MB 등)이 딸려 들어와
    hex 수만 건으로 게이트가 무의미해진다. 우리가 쓴 파일만 본다.
    """
    base = root / STATIC_DIR
    if not base.exists():
        return []
    return sorted(path for path in base.glob("*.js") if path.is_file())
```

`check_fg002_no_hex` 를 교체한다:

```python
def check_fg002_no_hex(root: Path = REPO_ROOT) -> list[str]:
    """FG-002: 하드코딩 hex 금지(생성물·유예 목록 제외).

    frontend/ 만 보던 동안 templates/ 와 static/*.js 는 **어떤 색 게이트도**
    보지 않았다. 그 사각지대에서 상태 팔레트 사본 7벌이 자랐고, 같은 상태가
    화면마다 다른 색으로 보였다(#0ca30c vs SSOT #10b981).
    """
    problems: list[str] = []
    sources = chain(
        _iter(root, FRONTEND_DIR, ".css", ".ts", ".jinja"),
        _iter(root, TEMPLATE_DIR, ".html"),
        _iter_legacy_scripts(root),
    )
    for path in sources:
        rel = _rel(path, root)
        if rel in GENERATED_FILES or rel in FG002_ALLOWLIST:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _THEME_COLOR_META.search(line):
                continue
            for hex_value in _HEX.findall(line):
                problems.append(
                    f"[FG-002] {rel}:{lineno} 하드코딩 색 `{hex_value}` — "
                    "var(--st-*) 또는 var(--c-*) 토큰을 쓰세요."
                )
    return problems
```

- [x] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/frontend/test_frontend_gates.py -v`
Expected: PASS (기존 + 신규 전부)

- [x] **Step 5: 게이트를 실제 저장소에 돌린다**

Run: `python3 scripts/check_frontend_gates.py`
Expected: `프론트엔드 게이트 통과 (FG-001~007)`

실패하면 메시지가 가리키는 파일을 본다. allowlist 에 없는 템플릿에서 hex 가 나왔다면 Task 2 가 놓친 자리이거나 목록에 빠진 파일이다.

- [x] **Step 6: 커밋**

```bash
git add scripts/check_frontend_gates.py tests/frontend/test_frontend_gates.py
git commit -m "feat(ci): FG-002 를 templates/ · static/*.js 까지 확장"
```

---

### Task 5: 문서 갱신과 전체 게이트

**Files:**
- Modify: `docs/CI.md:50`

**Interfaces:**
- Consumes: Task 4 의 확장된 FG-002
- Produces: 없음(문서)

- [x] **Step 1: CI.md 의 FG-002 설명을 고친다**

```markdown
| FG-002 | `app/web/frontend/` · `app/web/templates/` · `app/web/static/*.js` 내 하드코딩 hex 금지 (생성물·`theme-color` meta 제외, allowlist 축소형) |
```

- [x] **Step 2: 전체 게이트를 돌린다**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 통과

`check_docs_consistency.py` 가 실패하면 `docs/CI.md` 의 표현이 게이트 스크립트의 docstring 과 어긋난 것이므로 양쪽을 맞춘다.

- [x] **Step 3: 프론트엔드 테스트도 확인한다**

Run: `npm run test && npm run typecheck && npm run lint`
Expected: 전부 통과. 이 사이클은 TS 를 건드리지 않으므로 변화가 없어야 한다.

- [x] **Step 4: 커밋**

```bash
git add docs/CI.md
git commit -m "docs(ci): FG-002 확장 범위 반영"
```

---

## 완료 확인

- [x] `python3 scripts/ci/run_all_gates.py --profile full` 통과
- [x] 템플릿에 `--st-*` · `--ease-spring` 정의 0건
- [x] `app/web/static/*.js` 에 상태 hex 0건
- [x] `FG002_ALLOWLIST` 8줄 — 이후 사이클이 한 줄씩 지운다
- [x] 7개 화면에서 상태 색이 보이고, SSOT 값(`#10b981` · `#f59e0b` · `#ef4444`)과 일치
- [x] `/admin/runs` 추이 차트 막대에 색이 있다
