# P3-4 강제력 완성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 게이트에 뚫어둔 예외 3개를 없애 CDN 의존 0 · 템플릿 상태 매핑 중복 0 · 메일 색 SSOT 일치를 달성하고, 리포트에서 상황판으로 가는 링크를 연다.

**Architecture:** 차트 라이브러리는 npm 으로 당기되 **레거시 JS 를 고치지 않는다** — 라이브러리당 두 줄짜리 Vite 엔트리가 전역에 얹는다. 상태 색 팔레트를 빌드 스크립트에서 `app/core/` 로 옮겨 화면과 메일이 같은 출처를 보게 하고, 템플릿의 상태→표현 맵은 Jinja 전역 함수로 대체한다.

**Tech Stack:** Python 3.13 · pytest · Vite 6 다중 엔트리 · TypeScript 5.6 · Jinja2

**Spec:** `docs/superpowers/specs/2026-08-22-frontend-elevation-p3-4-enforcement-design.md`

## Global Constraints

- UI·로그·주석 문자열은 **한국어**. (`AGENTS.md`)
- **한국어 상태 라벨을 하드코딩하지 않는다.** `app/core/status_labels.py` 에서 가져온다.
- **차트 라이브러리 버전을 올리지 않는다.** CDN 과 정확히 동일하게 고정: `chart.js@4.4.7` · `echarts@5.5.1` · `plotly.js-dist-min@2.35.2`. 캐럿(`^`) 금지 — 이 계획은 "같은 것을 다른 경로로 배달"할 뿐이다.
- **`app/web/static/*.js` 를 한 줄도 고치지 않는다.** 그것은 P4 의 몫이다.
- **`report_renderer.py` 의 메일 레이아웃 색 7개**(`PAGE_BG` `CARD_BG` `INK` `MUTED` `BORDER` `SOFT_BG` `LABEL_BG`)**는 건드리지 않는다.** 상태 색 10개만 대상이다.
- **딥링크는 기본 꺼짐.** `E2E_PUBLIC_BASE_URL` 기본값은 빈 문자열이다.
- 새 환경변수는 **`.env.example` 과 `docs/INSTALL.md` 양쪽에** 적는다 — `docs_consistency` 게이트가 코드↔문서를 양방향으로 대조한다.
- 각 태스크 끝에서 `python3 scripts/ci/run_all_gates.py --gate frontend_gates` 가 통과해야 한다.

---

## File Structure

| 파일 | 책임 | 태스크 |
| --- | --- | --- |
| `app/web/frontend/entries/vendor-{chart,echarts,plotly}.ts` | 차트 라이브러리를 전역에 얹는 과도기 브리지. **P4 가 삭제한다** | 1 |
| `app/web/frontend/types/plotly.d.ts` | `plotly.js-dist-min` 은 타입을 동봉하지 않는다 — 최소 ambient 선언 | 1 |
| `app/web/frontend/types/vendor-globals.d.ts` | `Window` 에 세 전역 선언. P4 가 삭제한다 | 1 |
| `app/core/status_colors.py` (신규) | 상태 톤의 **색·글리프 SSOT**. 화면 토큰 생성기와 메일 렌더러가 함께 쓴다 | 3·6 |
| `app/web/status_view.py` (기존) | 템플릿이 쓰는 상태 표현 해석 — 여기에 글리프·필터 목록·모바일 맵을 더한다 | 6·7·8 |
| `scripts/check_frontend_gates.py` | FG-001 예외 삭제 · FG-006 탐지 수정 · FG-007 신설 | 2·4·5·8 |
| `app/notifications/report_renderer.py` | 메일 상태 색을 SSOT 파생으로. 레이아웃 색은 불변 | 4·9 |
| `app/core/settings.py` | `public_base_url` 추가 | 9 |

**Jinja 전역 등록 위치 (2곳):** `app/api/routes_dashboard.py:30-33` 과 `app/api/routes_trigger.py:31-33`. 이 저장소는 라우트 모듈마다 `Jinja2Templates` 인스턴스를 따로 두고 전역을 각자 등록한다(`status_badge_view` 가 그 선례). 라우트 핸들러의 컨텍스트 딕셔너리를 건드리지 말고 전역으로 등록하라 — 렌더 호출부가 여러 곳이라 컨텍스트 방식은 누락이 생긴다.

---

## Task 1: 차트 라이브러리 3종 self-host — 빌드 관문

이 태스크는 **설계 §6 이 지정한 첫 관문**이다. rollup 이 사전 번들된 거대 UMD 를 처리하지 못하면 설계 전체를 재검토해야 하므로, 다른 무엇보다 먼저 확인한다. 빌드가 깨지면 **우회를 즉흥으로 만들지 말고 보고하라.**

**Files:**
- Modify: `package.json` (`dependencies`)
- Modify: `vite.config.ts:16-23` (`rollupOptions.input`)
- Create: `app/web/frontend/entries/vendor-chart.ts`
- Create: `app/web/frontend/entries/vendor-echarts.ts`
- Create: `app/web/frontend/entries/vendor-plotly.ts`
- Create: `app/web/frontend/types/plotly.d.ts`
- Create: `app/web/frontend/types/vendor-globals.d.ts`
- Test: `tests/frontend/test_vendor_bundles.py`

**Interfaces:**
- Produces: Vite 엔트리 키 `entries/vendor-chart.ts` · `entries/vendor-echarts.ts` · `entries/vendor-plotly.ts`. Task 2 가 템플릿에서 `assets.asset_script("entries/vendor-plotly.ts")` 로 참조한다.

- [ ] **Step 1: 실패 테스트를 작성한다**

`tests/frontend/test_vendor_bundles.py` 를 새로 만든다. `tests/frontend/test_wall_assets.py` 가 같은 형태의 선례다.

```python
"""차트 라이브러리 self-host — 번들이 실제로 만들어지고 격리되는가.

CDN 을 npm 으로 바꾸는 변경의 실패 양상은 둘이다.
1) rollup 이 사전 번들된 거대 UMD 를 처리하지 못해 빌드가 깨진다 — 빌드가 잡는다
2) 빌드는 되는데 import 가 트리셰이킹돼 빈 번들이 나온다 — 화면이 조용히 차트를 잃는다

2)는 빌드가 잡지 못한다. 크기 하한 단언이 유일한 방어선이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.web.asset_manifest import AssetManifest

DIST = Path("app/web/static/dist")
MANIFEST = DIST / ".vite/manifest.json"
ASSET_MANIFEST = AssetManifest(MANIFEST, base_url="/static/dist")

VENDOR_ENTRIES = (
    "entries/vendor-chart.ts",
    "entries/vendor-echarts.ts",
    "entries/vendor-plotly.ts",
)


@pytest.fixture(scope="module")
def manifest() -> dict:
    assert MANIFEST.exists(), f"{MANIFEST} 가 없습니다. `npm run build` 를 먼저 실행하세요."
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _js_closure(manifest: dict, entry: str) -> set[str]:
    """엔트리가 실제로 끌어오는 JS 파일 집합(정적 import 폐포)."""
    seen: set[str] = set()

    def walk(key: str) -> None:
        if key in seen or key not in manifest:
            return
        seen.add(key)
        for imported in manifest[key].get("imports", []):
            walk(imported)

    walk(entry)
    return {manifest[key]["file"] for key in seen}


@pytest.mark.parametrize("entry", VENDOR_ENTRIES)
def test_vendor_entry_resolves_in_manifest(entry: str) -> None:
    assert ASSET_MANIFEST.js_url(entry).startswith("/static/dist/assets/")


@pytest.mark.parametrize(
    ("entry", "min_bytes"),
    [
        ("entries/vendor-chart.ts", 100_000),
        ("entries/vendor-echarts.ts", 300_000),
        ("entries/vendor-plotly.ts", 500_000),
    ],
)
def test_vendor_bundle_actually_contains_the_library(
    manifest: dict, entry: str, min_bytes: int
) -> None:
    """import 가 트리셰이킹으로 사라지면 빈 번들이 나온다 — 크기로 잡는다."""
    size = (DIST / manifest[entry]["file"]).stat().st_size
    assert size > min_bytes, (
        f"{entry} 번들이 {size}B 로 너무 작습니다 — 라이브러리가 안 실렸습니다."
    )


@pytest.mark.parametrize("entry", VENDOR_ENTRIES)
def test_main_bundle_does_not_include_vendor_entry(manifest: dict, entry: str) -> None:
    """일간 현황·로그인 등 일반 페이지가 차트 무게를 받지 않는다(설계 §3.1)."""
    assert manifest[entry]["file"] not in _js_closure(manifest, "entries/main.ts")


@pytest.mark.parametrize("entry", VENDOR_ENTRIES)
def test_wall_bundle_does_not_include_vendor_entry(manifest: dict, entry: str) -> None:
    """상황판은 3~5m 거리용 표시 화면이다 — 차트 라이브러리를 받을 이유가 없다."""
    assert manifest[entry]["file"] not in _js_closure(manifest, "entries/wall.ts")
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_vendor_bundles.py -v`
Expected: FAIL — `ManifestMissingError` 또는 `KeyError: 'entries/vendor-chart.ts'` (manifest 에 엔트리가 없다)

- [ ] **Step 3: npm 의존성을 정확한 버전으로 고정해 추가한다**

`package.json` 의 `dependencies` 를 알파벳 순서를 지켜 다음처럼 만든다.

```json
  "dependencies": {
    "@tailwindcss/postcss": "^4.0.0",
    "alpinejs": "^3.14.8",
    "chart.js": "4.4.7",
    "echarts": "5.5.1",
    "htmx.org": "^2.0.4",
    "plotly.js-dist-min": "2.35.2",
    "pretendard": "^1.3.9",
    "tailwindcss": "^4.0.0"
  },
```

캐럿을 붙이지 않는다 — CDN 이 배달하던 것과 **정확히 같은 코드**여야 이 변경이 무해하다.

Run: `npm install`

- [ ] **Step 4: 타입 선언 2개를 만든다**

`plotly.js-dist-min` 은 타입을 동봉하지 않는다(`npm view plotly.js-dist-min types` → 빈 값). `tsconfig.json` 이 `strict: true` 이므로 선언 없이는 `tsc --noEmit` 이 TS7016 으로 깨진다. `echarts` 와 `chart.js` 는 타입을 동봉하므로 선언이 필요 없다.

`app/web/frontend/types/plotly.d.ts`:

```ts
// plotly.js-dist-min 은 자체 타입 선언을 제공하지 않는다.
// @types/plotly.js 는 dist-min 빌드와 형태가 달라 맞지 않으므로
// alpinejs.d.ts 와 같은 최소 ambient 선언으로 처리한다.
declare module "plotly.js-dist-min";
```

`app/web/frontend/types/vendor-globals.d.ts`:

```ts
// 차트 라이브러리는 레거시 페이지 스크립트(app/web/static/*.js)가 전역으로 쓴다.
// 그 스크립트들을 고치지 않기 위한 과도기 선언이다(P3-4 §3.1).
// P4 가 admin-runs.js·insights.js·admin-stats.js 를 이관하면
// 이 파일과 entries/vendor-*.ts 를 함께 삭제한다.
export {};

declare global {
  interface Window {
    Chart: unknown;
    echarts: unknown;
    Plotly: unknown;
  }
}
```

- [ ] **Step 5: 브리지 엔트리 3개를 만든다**

`app/web/frontend/entries/vendor-chart.ts`:

```ts
// 과도기 장치 — admin-runs.js 가 전역 `Chart` 를 쓴다(P3-4 §3.1).
// chart.js/auto 는 UMD 빌드와 동일하게 전 컨트롤러를 자동 등록한다.
// P4 가 admin-runs.js 를 이관하면 이 파일을 삭제한다.
import Chart from "chart.js/auto";

window.Chart = Chart;
```

`app/web/frontend/entries/vendor-echarts.ts`:

```ts
// 과도기 장치 — admin-runs.js 가 전역 `echarts` 를 쓴다(P3-4 §3.1).
// P4 가 admin-runs.js 를 이관하면 이 파일을 삭제한다.
import * as echarts from "echarts";

window.echarts = echarts;
```

`app/web/frontend/entries/vendor-plotly.ts`:

```ts
// 과도기 장치 — insights.js·admin-stats.js 가 전역 `Plotly` 를 쓴다(P3-4 §3.1).
// 서버가 Python plotly.graph_objects 로 figure JSON 을 만들어 내려보내므로
// 라이브러리를 교체할 수 없다(설계 D1).
// P4 가 두 파일을 모두 이관하면 이 파일을 삭제한다.
import Plotly from "plotly.js-dist-min";

window.Plotly = Plotly;
```

- [ ] **Step 6: Vite 에 엔트리를 등록한다**

`vite.config.ts` 의 `rollupOptions.input` 을 다음으로 바꾼다.

```ts
      input: {
        main: resolve(__dirname, "app/web/frontend/entries/main.ts"),
        // 상황판은 사이드바·Alpine·컴포넌트 TS 가 필요 없는 독립 화면이라
        // 별 엔트리로 둔다 — 일반 페이지 번들에 상황판 CSS 를 얹지 않기 위함.
        wall: resolve(__dirname, "app/web/frontend/entries/wall.ts"),
        // 차트 라이브러리 self-host(P3-4 §3.1). 레거시 페이지 스크립트가
        // 전역으로 쓰므로 브리지 엔트리로 얹는다 — 해당 화면이 P4 에서
        // 이관되는 시점에 이 세 줄과 엔트리 파일을 함께 지운다.
        "vendor-chart": resolve(__dirname, "app/web/frontend/entries/vendor-chart.ts"),
        "vendor-echarts": resolve(__dirname, "app/web/frontend/entries/vendor-echarts.ts"),
        "vendor-plotly": resolve(__dirname, "app/web/frontend/entries/vendor-plotly.ts"),
      },
```

- [ ] **Step 7: 빌드한다 — 이 태스크의 관문**

Run: `npm run build`
Expected: 성공. `app/web/static/dist/.vite/manifest.json` 에 `entries/vendor-*.ts` 세 키가 생긴다.

**실패하면 여기서 멈추고 보고한다.** rollup 이 거대 UMD 를 처리하지 못하는 것은 설계 §6 이 예상한 리스크이며, 대응은 설계 재검토이지 즉흥 우회가 아니다. 오류 전문과 어느 라이브러리인지를 함께 보고하라.

- [ ] **Step 8: 타입·린트를 확인한다**

Run: `npm run typecheck && npm run lint`
Expected: 둘 다 통과. `typecheck` 가 `plotly.js-dist-min` 에서 TS7016 을 내면 Step 4 의 `plotly.d.ts` 가 `tsconfig.json` 의 `include` (`app/web/frontend/**/*.ts`) 안에 있는지 확인하라 — `.d.ts` 도 그 glob 에 걸린다.

- [ ] **Step 9: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/frontend/test_vendor_bundles.py -v`
Expected: 전부 PASS

크기 단언이 실패하면 트리셰이킹으로 라이브러리가 날아간 것이다. `window.X = X` 는 부수효과라 rollup 이 보존해야 정상이므로, 이 경우도 보고 대상이다.

- [ ] **Step 10: 커밋**

```bash
git add package.json package-lock.json vite.config.ts app/web/frontend/entries/vendor-*.ts app/web/frontend/types/plotly.d.ts app/web/frontend/types/vendor-globals.d.ts tests/frontend/test_vendor_bundles.py
git commit -m "feat(frontend): 차트 라이브러리 3종 self-host — 브리지 엔트리로 레거시 JS 불변"
```

---

## Task 2: 템플릿의 CDN 제거 + FG-001 예외 삭제

**Files:**
- Modify: `app/web/templates/admin/runs.html:833-837`
- Modify: `app/web/templates/admin/stats.html:188-191`
- Modify: `app/web/templates/insights.html:266-269`
- Modify: `scripts/check_frontend_gates.py` (`FG001_EXCEPTIONS` 삭제, `check_fg001_no_cdn`)
- Modify: `tests/frontend/test_frontend_gates.py:33-67` (예외 테스트 3개 → 1개로 교체)

**Interfaces:**
- Consumes: Task 1 의 Vite 엔트리 키 `entries/vendor-chart.ts` · `entries/vendor-echarts.ts` · `entries/vendor-plotly.ts`

- [ ] **Step 1: 실패 테스트를 작성한다**

`tests/frontend/test_frontend_gates.py` 에서 예외 관련 테스트 3개를 **삭제**한다: `test_fg001_allows_exact_allow_listed_chart_cdn` · `test_fg001_flags_different_url_in_exception_file` · `test_fg001_flags_exception_url_in_different_file`. 그 자리에 다음을 넣는다.

```python
def test_fg001_flags_chart_cdn_without_exception(tmp_path):
    """차트 라이브러리 예외는 P3-4 가 self-host 로 바꾸며 없앴다 — 이제 걸려야 한다."""
    _write(
        tmp_path,
        "app/web/templates/insights.html",
        '<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js" '
        'crossorigin="anonymous"></script>',
    )
    problems = check_fg001_no_cdn(tmp_path)
    assert len(problems) == 1
    assert "plotly" in problems[0]


def test_fg001_has_no_exception_mechanism():
    """예외 딕셔너리가 되살아나면 이 게이트는 다시 조용히 새기 시작한다."""
    import scripts.check_frontend_gates as gates

    assert not hasattr(gates, "FG001_EXCEPTIONS")
```

`tests/frontend/test_vendor_bundles.py` 에는 템플릿이 실제로 벤더 엔트리를 로드하는지 단언을 더한다.

```python
TEMPLATES = Path("app/web/templates")

VENDOR_TEMPLATE_REFS = {
    "admin/runs.html": ("entries/vendor-chart.ts", "entries/vendor-echarts.ts"),
    "admin/stats.html": ("entries/vendor-plotly.ts",),
    "insights.html": ("entries/vendor-plotly.ts",),
}


@pytest.mark.parametrize(("template", "entries"), sorted(VENDOR_TEMPLATE_REFS.items()))
def test_template_loads_its_vendor_entries(template: str, entries: tuple[str, ...]) -> None:
    """빌드만 되고 템플릿이 안 부르면 화면에서 차트가 사라진다.

    P3-2 에서 wall.ts 가 kpi-card CSS 를 import 하지 않아 상황판이 무스타일로
    나갔던 것과 같은 종류의 누락이다.
    """
    source = (TEMPLATES / template).read_text(encoding="utf-8")
    for entry in entries:
        assert entry in source, f"{template} 이 {entry} 를 로드하지 않습니다."


@pytest.mark.parametrize("template", sorted(VENDOR_TEMPLATE_REFS))
def test_template_has_no_cdn_script(template: str) -> None:
    source = (TEMPLATES / template).read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net" not in source
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_vendor_bundles.py tests/frontend/test_frontend_gates.py -v -k "vendor_entries or cdn or exception"`
Expected: FAIL — 템플릿에 아직 CDN 이 있고 `FG001_EXCEPTIONS` 도 존재한다

- [ ] **Step 3: `admin/runs.html` 의 스크립트 블록을 바꾼다**

`app/web/templates/admin/runs.html` 의 `{% block scripts %}` 를 다음으로 교체한다. `admin/base.html` 이 `_assets.html` 을 import 하지만 **매크로 import 는 자식 템플릿 스코프로 상속되지 않으므로** 블록 안에서 다시 import 해야 한다.

```html
{% block scripts %}
{% import "_assets.html" as assets %}
{{ assets.asset_script("entries/vendor-chart.ts") }}
{{ assets.asset_script("entries/vendor-echarts.ts") }}
<script src="/static/admin-runs.js?v=14" defer></script>
{% endblock %}
```

벤더 엔트리를 레거시 스크립트보다 **위에** 둔다. `type="module"` 과 `defer` 는 같은 실행 목록에 들어가 문서 순서를 지킨다. `/static/admin-runs.js?v=14` 는 그대로 둔다 — 그 파일 이관은 P4 의 몫이다.

- [ ] **Step 4: `admin/stats.html` 과 `insights.html` 을 바꾼다**

`app/web/templates/admin/stats.html`:

```html
{% block scripts %}
{% import "_assets.html" as assets %}
{{ assets.asset_script("entries/vendor-plotly.ts") }}
<script src="/static/admin-stats.js" defer></script>
{% endblock %}
```

`app/web/templates/insights.html`:

```html
{% block scripts %}
{% import "_assets.html" as assets %}
{{ assets.asset_script("entries/vendor-plotly.ts") }}
<script src="/static/insights.js?v=1" defer></script>
{% endblock %}
```

- [ ] **Step 5: FG-001 의 예외 장치를 삭제한다**

`scripts/check_frontend_gates.py` 에서 `FG001_EXCEPTIONS` 딕셔너리와 그 위의 주석 블록을 **통째로 지우고**, 함수를 다음으로 바꾼다.

```python
def check_fg001_no_cdn(root: Path = REPO_ROOT) -> list[str]:
    """FG-001: 템플릿에 외부 CDN script/link 금지. 예외 없음.

    차트 라이브러리 3종(Chart.js·ECharts·Plotly)에 예외를 두었던 이유는
    "vite.config.ts 가 단일 엔트리만 지원한다" 였다. P3-2 가 wall 엔트리를
    추가하며 그 전제가 소멸했고, P3-4 가 self-host 로 바꾸며 예외를 없앴다.
    """
    problems: list[str] = []
    for path in chain(_iter(root, TEMPLATE_DIR, ".html"), _iter_component_markup(root)):
        rel = _rel(path, root)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for url in _EXTERNAL_URL.findall(line):
                problems.append(
                    f"[FG-001] {rel}:{lineno} 외부 자산 참조 `{url}` — "
                    "npm 으로 self-host 하고 asset 매크로를 쓰세요."
                )
    return problems
```

- [ ] **Step 6: 빌드하고 테스트가 통과하는지 확인한다**

Run: `npm run build && python3 -m pytest tests/frontend/ -v`
Expected: 전부 PASS

Run: `python3 scripts/ci/run_all_gates.py --gate frontend_gates`
Expected: `{"passed": true, ...}` — CDN 위반 0건

- [ ] **Step 7: 커밋**

```bash
git add app/web/templates/admin/runs.html app/web/templates/admin/stats.html app/web/templates/insights.html scripts/check_frontend_gates.py tests/frontend/test_frontend_gates.py tests/frontend/test_vendor_bundles.py
git commit -m "feat(frontend): 템플릿 CDN 제거 + FG-001 예외 삭제 — 외부 의존 0"
```

---

## Task 3: 팔레트를 `app/core/status_colors.py` 로 이사

순수 이사다. **생성물이 바이트 동일해야 한다** — 달라지면 이사가 아니라 변경이다.

**Files:**
- Create: `app/core/status_colors.py`
- Modify: `scripts/gen_frontend_tokens.py:47-66` (`PALETTE` 정의 삭제, import 로 대체)
- Test: `tests/test_status_colors_ssot.py`

**Interfaces:**
- Produces:
  ```python
  # app/core/status_colors.py
  PALETTE: dict[str, dict[str, str]]  # 톤 → {"solid","surface","text","border"} → hex
  ```
  Task 4 가 `PALETTE["passed"]["text"]` 형태로, Task 6 이 같은 모듈의 `TONE_GLYPHS` 를 쓴다.

- [ ] **Step 1: 실패 테스트를 작성한다**

`tests/test_status_colors_ssot.py`:

```python
"""상태 색 SSOT — 화면과 메일이 같은 출처를 본다.

팔레트가 scripts/gen_frontend_tokens.py 안에 있던 동안 메일은 그 값을 쓸 수 없었다
(앱이 빌드 스크립트를 import 하는 것은 방향이 거꾸로다). 그래서 메일이 자기 hex 를
따로 들고 있었고, 같은 상태를 화면과 다른 색으로 말했다.
"""

from __future__ import annotations

import re

from app.core.status_colors import PALETTE
from app.core.status_labels import STATUS_TONES

_HEX = re.compile(r"^#[0-9a-f]{6}$")
_VARIANTS = ("solid", "surface", "text", "border")


def test_palette_covers_every_tone() -> None:
    """톤이 하나 늘었는데 색이 없으면 화면이 조용히 회색으로 떨어진다."""
    missing = [tone for tone in STATUS_TONES if tone not in PALETTE]
    assert not missing, f"PALETTE 에 없는 톤: {missing}"


def test_palette_has_no_extra_tones() -> None:
    extra = [tone for tone in PALETTE if tone not in STATUS_TONES]
    assert not extra, f"STATUS_TONES 에 없는 톤: {extra}"


def test_every_tone_has_all_four_variants() -> None:
    for tone, variants in PALETTE.items():
        assert set(variants) == set(_VARIANTS), tone


def test_every_value_is_a_lowercase_six_digit_hex() -> None:
    """생성기가 CSS 로 그대로 찍으므로 형식이 어긋나면 토큰이 깨진다."""
    for tone, variants in PALETTE.items():
        for name, value in variants.items():
            assert _HEX.match(value), f"{tone}.{name} = {value!r}"


def test_generator_reads_the_shared_palette() -> None:
    """생성기가 자기 사본을 되살리면 SSOT 가 다시 둘로 갈라진다."""
    import scripts.gen_frontend_tokens as generator

    assert generator.PALETTE is PALETTE
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `python3 -m pytest tests/test_status_colors_ssot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.status_colors'`

- [ ] **Step 3: 현재 생성물을 기준으로 보관한다**

이사 전후 비교용이다.

Run: `cp app/web/frontend/styles/tokens.generated.css /tmp/tokens.before.css`

- [ ] **Step 4: `app/core/status_colors.py` 를 만든다**

`scripts/gen_frontend_tokens.py:47-66` 의 `PALETTE` 를 **값을 하나도 바꾸지 않고** 옮긴다.

```python
"""상태 톤의 색 SSOT — 화면 토큰과 메일이 같은 출처를 본다.

이 값이 scripts/gen_frontend_tokens.py 안에 있던 동안 메일 렌더러는 쓸 수 없었다.
"정상은 초록" 은 도메인 지식이지 빌드 도구의 소관이 아니다(P3-4 설계 D4).

톤 축은 app/core/status_labels.py 의 STATUS_TONES 가 정의한다 — 여기에 톤을
더하거나 빼지 말고 그쪽을 고친 뒤 맞춘다.
"""

from __future__ import annotations

PALETTE: dict[str, dict[str, str]] = {
    "passed": {"solid": "#10b981", "surface": "#d1fae5", "text": "#047857", "border": "#6ee7b7"},
    "anomaly": {"solid": "#f59e0b", "surface": "#fef3c7", "text": "#b45309", "border": "#fcd34d"},
    "error": {"solid": "#ef4444", "surface": "#fee2e2", "text": "#b91c1c", "border": "#fca5a5"},
    "running": {"solid": "#3b82f6", "surface": "#dbeafe", "text": "#1d4ed8", "border": "#93c5fd"},
    "waiting_input": {
        "solid": "#8b5cf6",
        "surface": "#ede9fe",
        "text": "#6d28d9",
        "border": "#c4b5fd",
    },
    "blocked": {"solid": "#f97316", "surface": "#ffedd5", "text": "#c2410c", "border": "#fdba74"},
    "skipped": {"solid": "#94a3b8", "surface": "#f1f5f9", "text": "#475569", "border": "#cbd5e1"},
    "cancelled": {"solid": "#71717a", "surface": "#f4f4f5", "text": "#52525b", "border": "#d4d4d8"},
    "pending": {"solid": "#a1a1aa", "surface": "#f4f4f5", "text": "#6b7280", "border": "#e4e4e7"},
}
```

값을 옮길 때 `scripts/gen_frontend_tokens.py` 의 원본을 그대로 복사하라. 손으로 다시 타이핑하지 마라.

- [ ] **Step 5: 생성기가 공유 팔레트를 import 하게 한다**

`scripts/gen_frontend_tokens.py` 에서 `PALETTE` 정의를 지우고, 기존 `from app.core.status_labels import (...)` 아래에 다음을 더한다.

```python
from app.core.status_colors import PALETTE
```

생성기의 `_assert_palette_covers_tones()` · `render_css()` 는 그대로 둔다 — 이름이 같으므로 나머지 코드는 손댈 것이 없다.

- [ ] **Step 6: 생성물이 바이트 동일한지 확인한다**

Run: `python3 scripts/gen_frontend_tokens.py && diff /tmp/tokens.before.css app/web/frontend/styles/tokens.generated.css && echo "동일"`
Expected: `동일` — 차이가 있으면 이사 중 값이 바뀐 것이다. 되돌리고 다시 복사하라.

- [ ] **Step 7: 테스트와 게이트를 확인한다**

Run: `python3 -m pytest tests/test_status_colors_ssot.py tests/frontend/test_gen_frontend_tokens.py -v`
Expected: 전부 PASS

Run: `python3 scripts/ci/run_all_gates.py --gate frontend_tokens && python3 scripts/ci/run_all_gates.py --gate import_contracts`
Expected: 둘 다 `{"passed": true, ...}`

- [ ] **Step 8: 커밋**

```bash
git add app/core/status_colors.py scripts/gen_frontend_tokens.py tests/test_status_colors_ssot.py
git commit -m "refactor(core): 상태 색 팔레트를 빌드 스크립트에서 app/core 로 이사"
```

---

## Task 4: 메일 상태 색을 SSOT 파생으로 + FG-007

**Files:**
- Modify: `app/notifications/report_renderer.py:39-49` (상태 색 상수 10개)
- Modify: `scripts/check_frontend_gates.py` (`check_fg007_*` 신설, `CHECKS` 튜플, `main()` 출력 문구)
- Test: `tests/test_report_status_colors.py` (기존 파일에 추가)
- Test: `tests/frontend/test_frontend_gates.py` (FG-007 테스트 추가)

**Interfaces:**
- Consumes: Task 3 의 `app.core.status_colors.PALETTE`

- [ ] **Step 1: 실패 테스트를 작성한다**

`tests/test_report_status_colors.py` 끝에 추가한다.

```python
def test_mail_status_colors_are_derived_from_the_shared_palette() -> None:
    """화면과 메일이 같은 상태를 다른 색으로 말하지 않는다(P3-4 §3.2).

    메일의 (글자색, 옅은 배경) 쌍은 웹 팔레트의 (text, surface) 축에 대응한다.
    """
    from app.core.status_colors import PALETTE
    from app.notifications import report_renderer as renderer

    expected = {
        "PASS": "passed",
        "FAIL": "error",
        "WARN": "anomaly",
        "NEUTRAL": "pending",
        "INFO": "running",
    }
    for prefix, tone in expected.items():
        assert getattr(renderer, f"{prefix}_COLOR") == PALETTE[tone]["text"], prefix
        assert getattr(renderer, f"{prefix}_SOFT_BG") == PALETTE[tone]["surface"], prefix


def test_mail_layout_colors_are_untouched() -> None:
    """레이아웃 색은 상태와 무관하다 — 팔레트 통일이 메일 크롬까지 바꾸면 안 된다."""
    from app.notifications import report_renderer as renderer

    assert renderer.PAGE_BG == "#f4f5f7"
    assert renderer.CARD_BG == "#ffffff"
    assert renderer.INK == "#1f2328"
    assert renderer.MUTED == "#6b7280"
    assert renderer.BORDER == "#e5e7eb"
    assert renderer.SOFT_BG == "#f7f8fa"
    assert renderer.LABEL_BG == "#f4f6f8"
```

`tests/frontend/test_frontend_gates.py` 에 추가한다(파일 상단 import 에 `check_fg007_mail_status_colors_from_ssot` 를 더한다).

```python
def test_fg007_flags_hardcoded_mail_status_color(tmp_path):
    _write(
        tmp_path,
        "app/notifications/report_renderer.py",
        'PAGE_BG = "#f4f5f7"\nPASS_COLOR = "#2f8f4e"\n',
    )
    problems = check_fg007_mail_status_colors_from_ssot(tmp_path)
    assert len(problems) == 1
    assert "PASS_COLOR" in problems[0]


def test_fg007_allows_palette_derived_status_color(tmp_path):
    _write(
        tmp_path,
        "app/notifications/report_renderer.py",
        'PAGE_BG = "#f4f5f7"\nPASS_COLOR = PALETTE["passed"]["text"]\n',
    )
    assert check_fg007_mail_status_colors_from_ssot(tmp_path) == []


def test_fg007_ignores_layout_colors(tmp_path):
    """레이아웃 색은 상태와 무관하므로 hex 리터럴이 정당하다."""
    _write(
        tmp_path,
        "app/notifications/report_renderer.py",
        'PAGE_BG = "#f4f5f7"\nINK = "#1f2328"\nBORDER = "#e5e7eb"\n',
    )
    assert check_fg007_mail_status_colors_from_ssot(tmp_path) == []
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `python3 -m pytest tests/test_report_status_colors.py tests/frontend/test_frontend_gates.py -v -k "derived or layout_colors or fg007"`
Expected: FAIL — `ImportError: cannot import name 'check_fg007_mail_status_colors_from_ssot'` 및 색 값 불일치

- [ ] **Step 3: 메일 상태 색을 팔레트 파생으로 바꾼다**

`app/notifications/report_renderer.py` 의 import 구역에 다음을 더한다.

```python
from app.core.status_colors import PALETTE
```

상태 색 상수 10개(`PASS_COLOR` ~ `INFO_SOFT_BG`)를 다음으로 교체한다. **레이아웃 색 7개는 그대로 둔다.**

```python
# 상태 색은 화면과 같은 팔레트에서 파생한다(P3-4 §3.2).
# 메일의 (글자색, 옅은 배경) 쌍이 웹 팔레트의 (text, surface) 축에 대응한다.
# 값을 여기에 직접 적지 마라 — FG-007 이 막는다.
PASS_COLOR = PALETTE["passed"]["text"]
PASS_SOFT_BG = PALETTE["passed"]["surface"]
FAIL_COLOR = PALETTE["error"]["text"]
FAIL_SOFT_BG = PALETTE["error"]["surface"]
WARN_COLOR = PALETTE["anomaly"]["text"]
WARN_SOFT_BG = PALETTE["anomaly"]["surface"]
NEUTRAL_COLOR = PALETTE["pending"]["text"]
NEUTRAL_SOFT_BG = PALETTE["pending"]["surface"]
INFO_COLOR = PALETTE["running"]["text"]
INFO_SOFT_BG = PALETTE["running"]["surface"]
```

- [ ] **Step 4: FG-007 을 만든다**

`scripts/check_frontend_gates.py` 의 `check_fg006_*` 아래에 추가한다. 상수는 파일 상단 상수 구역에 둔다.

```python
MAIL_RENDERER = "app/notifications/report_renderer.py"

# 메일 상태 색 상수의 이름 규약. 레이아웃 색(PAGE_BG·INK·BORDER 등)은 상태와
# 무관하므로 대상이 아니다 — 이름으로 갈리므로 값 allowlist 가 필요 없다.
_MAIL_STATUS_CONST_RE = re.compile(r"^(PASS|FAIL|WARN|NEUTRAL|INFO)_(COLOR|SOFT_BG)\s*=\s*['\"]#")
```

```python
def check_fg007_mail_status_colors_from_ssot(root: Path = REPO_ROOT) -> list[str]:
    """FG-007: 메일 상태 색은 status_colors.PALETTE 파생만.

    화면과 메일이 같은 상태를 다른 색으로 말하던 것을 P3-4 가 통일했다.
    되돌아가는 유일한 경로가 "여기에 hex 를 다시 적는 것" 이므로 그것만 막는다.
    """
    path = root / MAIL_RENDERER
    if not path.exists():
        return []
    problems: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if _MAIL_STATUS_CONST_RE.match(line):
            name = line.split("=", 1)[0].strip()
            problems.append(
                f"[FG-007] {MAIL_RENDERER}:{lineno} 상태 색 `{name}` 이 hex 리터럴 — "
                "app/core/status_colors.py 의 PALETTE 에서 파생시키세요."
            )
    return problems
```

`CHECKS` 튜플과 `main()` 의 출력 문구를 갱신한다.

```python
CHECKS = (
    check_fg001_no_cdn,
    check_fg002_no_hex,
    check_fg003_status_source,
    check_fg004_file_size,
    check_fg005_no_static_ref,
    check_fg006_no_template_status_literals,
    check_fg007_mail_status_colors_from_ssot,
)
```

`main()` 의 마지막 print 를 `print("프론트엔드 게이트 통과 (FG-001~007)")` 로 바꾼다.

- [ ] **Step 5: `docs/CI.md` 의 게이트 표에 FG-007 을 더한다**

`docs/CI.md:54` 아래에 한 줄 추가한다.

```markdown
| FG-007 | 메일 상태 색이 `app/core/status_colors.py` 의 `PALETTE` 파생인지 (레이아웃 색 제외) |
```

- [ ] **Step 6: 테스트와 게이트를 확인한다**

Run: `python3 -m pytest tests/test_report_status_colors.py tests/test_daily_report_render.py tests/frontend/test_frontend_gates.py -v`
Expected: 전부 PASS

Run: `python3 scripts/ci/run_all_gates.py --gate frontend_gates && python3 scripts/ci/run_all_gates.py --gate docs_consistency`
Expected: 둘 다 `{"passed": true, ...}`

- [ ] **Step 7: 메일 실물을 눈으로 확인한다**

```bash
PYTHONIOENCODING=utf-8 python3 - <<'PY'
import sys; sys.path.insert(0, '.')
from app.notifications.daily_report import build_daily_report
from app.notifications.report_renderer import render_daily_report_html

summary = {
    "cards": [],
    "totals": {"modules": 6, "passed": 5, "pass_rate": 83, "error": 1,
               "anomaly": 0, "running": 0, "not_inspected": 0},
    "attention": [],
    "systems": [{"system_code": "HOM", "system_name": "홈페이지", "module_total": 3,
                 "counts": {"passed": 3, "error": 0, "anomaly": 0,
                            "running": 0, "not_inspected": 0}}],
    "date_label": "2026-08-21",
    "generated_at": "2026-08-22T08:00:00+00:00",
}
report = build_daily_report(summary, date_label="2026-08-21")
open("/tmp/daily_report.html", "w", encoding="utf-8").write(render_daily_report_html(report))
print("wrote /tmp/daily_report.html")
PY
```

브라우저로 열어 **레이아웃(테두리·본문 글자·카드 배경)은 그대로이고 상태 색만 바뀌었는지** 확인한다. 설계 §3.2 가 예고한 대로 정상 배경이 연녹(`#e9f6ee`)에서 민트(`#d1fae5`)로 진해진다 — 이는 의도된 변경이다.

- [ ] **Step 8: 커밋**

```bash
git add app/notifications/report_renderer.py scripts/check_frontend_gates.py docs/CI.md tests/test_report_status_colors.py tests/frontend/test_frontend_gates.py
git commit -m "feat(notifications): 메일 상태 색을 웹과 같은 SSOT 파생으로 + FG-007"
```

---

## Task 5: FG-006 탐지 규칙을 블록 단위로 고친다

**allowlist 는 아직 건드리지 않는다.** 규칙을 먼저 고쳐야 이후 태스크의 청소가 실제로 검증된다.

**Files:**
- Modify: `scripts/check_frontend_gates.py` (`_STATUS_MAP_KEY_RE` · `_DOMAIN_LABELS` · `check_fg006_*`)
- Test: `tests/frontend/test_frontend_gates.py`

- [ ] **Step 1: 실패 테스트를 작성한다**

`tests/frontend/test_frontend_gates.py` 에 추가한다.

```python
def test_fg006_flags_map_written_one_entry_per_line(tmp_path):
    """줄당 항목이 하나인 맵도 잡아야 한다.

    규칙이 "한 줄에 상태 키 2개 이상" 이던 동안 mobile_trigger.html 의
    8개짜리 STATUS_VIEW 가 통째로 보이지 않았다(설계 §3.3).
    """
    _write(
        tmp_path,
        "app/web/templates/x.html",
        "<script>\n"
        "const STATUS_VIEW = {\n"
        '    PENDING: { label: "대기" },\n'
        '    RUNNING: { label: "실행 중" },\n'
        '    PASSED: { label: "정상" },\n'
        "};\n"
        "</script>\n",
    )
    assert check_fg006_no_template_status_literals(tmp_path)


def test_fg006_flags_cancelled_label(tmp_path):
    _write(
        tmp_path,
        "app/web/templates/x.html",
        '<option value="CANCELLED">취소</option>',
    )
    problems = check_fg006_no_template_status_literals(tmp_path)
    assert len(problems) == 1
    assert "CANCELLED" in problems[0]


def test_fg006_allows_cancel_button_without_enum(tmp_path):
    """'취소' 는 버튼 문구로도 흔하다 — enum 값이 없으면 걸리지 않아야 한다."""
    _write(
        tmp_path,
        "app/web/templates/x.html",
        '<button type="button" class="btn">취소</button>',
    )
    assert check_fg006_no_template_status_literals(tmp_path) == []


def test_fg006_allows_unrelated_keys_far_apart(tmp_path):
    """블록 단위로 넓히면서 무관한 단어가 우연히 묶이지 않아야 한다."""
    lines = ['<div class="error-banner">']
    lines += ["  <p>줄</p>"] * 40
    lines += ['  <span data-state="running"></span>', "</div>"]
    _write(tmp_path, "app/web/templates/x.html", "\n".join(lines))
    assert check_fg006_no_template_status_literals(tmp_path) == []
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_frontend_gates.py -v -k "one_entry_per_line or cancelled_label or cancel_button"`
Expected: 앞의 둘 FAIL(안 잡힌다), `cancel_button` 은 PASS

- [ ] **Step 3: 탐지 규칙을 블록 단위로 바꾼다**

`scripts/check_frontend_gates.py` 의 상수 구역에서 `_STATUS_MAP_KEY_RE` 를 대소문자 무시로 바꾸고, 창 크기 상수를 더하고, `_DOMAIN_LABELS` 에 `취소` 를 넣는다.

```python
_STATUS_MAP_KEY_RE = [
    re.compile(rf"['\"]?{key}['\"]?\s*:", re.IGNORECASE) for key in _STATUS_MAP_KEYS
]
# 맵 판정 창. 줄 단위로 보던 동안 "줄당 한 항목" 으로 쓴 맵이 통째로 보이지 않았다.
# 12줄이면 8개짜리 STATUS_VIEW 를 덮으면서, 무관한 단어 두 개가 우연히 묶일 만큼
# 넓지는 않다 — Step 5 에서 전체 템플릿 오탐 0 을 실측해 정한 값이다.
_STATUS_MAP_WINDOW = 12
```

```python
_DOMAIN_LABELS = ("이상징후", "점검실패", "입력 대기", "정상", "취소")
```

`check_fg006_no_template_status_literals` 의 본문을 다음으로 바꾼다.

```python
def check_fg006_no_template_status_literals(root: Path = REPO_ROOT) -> list[str]:
    """FG-006: 템플릿이 상태→표현 매핑을 중복으로 들고 있는 것을 막는다.

    run.html 이 자체 status_pill 맵을 들고 있어 ANOMALY/ERROR 배지가 회색·영문으로
    렌더되던 사고(P3-1)를 막는다.

    맵 판정은 **블록 단위**다. 줄 단위이던 동안 한 줄에 한 항목씩 쓴 맵
    (mobile_trigger.html 의 STATUS_VIEW 8개)이 통째로 보이지 않았다(P3-4 §3.3).
    """
    problems: list[str] = []
    for path in _iter(root, TEMPLATE_DIR, ".html"):
        rel = _rel(path, root)
        if rel in FG006_ALLOWLIST:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        flagged_windows: list[int] = []
        for lineno, line in enumerate(lines, 1):
            window = "\n".join(lines[lineno - 1 : lineno - 1 + _STATUS_MAP_WINDOW])
            matched = [
                key
                for key, pattern in zip(_STATUS_MAP_KEYS, _STATUS_MAP_KEY_RE, strict=True)
                if pattern.search(window)
            ]
            if len(matched) >= _STATUS_MAP_MIN_KEYS:
                # 같은 맵이 창을 옮겨가며 여러 번 잡히는 것을 막는다 — 블록당 1건.
                if flagged_windows and lineno - flagged_windows[-1] < _STATUS_MAP_WINDOW:
                    continue
                flagged_windows.append(lineno)
                keys = ", ".join(matched[:4])
                problems.append(
                    f"[FG-006] {rel}:{lineno} 상태 키 맵 리터럴 (`{keys}`) — "
                    "components/status-badge/macro.jinja 의 status_badge 와 "
                    "status_badge_view(status) 를 쓰세요."
                )
                continue
            enum_hit = next((e for e in _ENUM_VALUES if e in line), None)
            label_hit = next((label for label in _DOMAIN_LABELS if label in line), None)
            if enum_hit and label_hit:
                problems.append(
                    f"[FG-006] {rel}:{lineno} enum 값 `{enum_hit}` 과 라벨 `{label_hit}` 이 "
                    "같은 줄에 하드코딩 — lib/status.generated.ts 또는 "
                    "status_badge_view(status).label 을 쓰세요."
                )
    return problems
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/frontend/test_frontend_gates.py -v`
Expected: 전부 PASS (기존 FG-006 테스트 포함)

- [ ] **Step 5: 전체 템플릿에 돌려 오탐 0 을 실측한다**

P3-1 이 FG-006 을 구조 탐지로 바꿀 때 밟은 절차와 같다. **오탐이 있으면 채택하지 않는다.**

```bash
PYTHONIOENCODING=utf-8 python3 -c "
import sys; sys.path.insert(0,'.')
import scripts.check_frontend_gates as g
saved = set(g.FG006_ALLOWLIST); g.FG006_ALLOWLIST.clear()
from collections import Counter
v = g.check_fg006_no_template_status_literals()
g.FG006_ALLOWLIST.update(saved)
print(f'allowlist 없이 위반 {len(v)}건')
for f, n in Counter(x.split(':')[0].replace('[FG-006] ','') for x in v).most_common():
    print(f'  {n:3}  {f}')
"
```

Expected: 파일이 정확히 넷 — `_macros.html` · `admin/runs.html` · `mobile_trigger.html` · `schedules.html`. **다섯 번째 파일이 나오면 오탐이다.** 그 줄을 직접 열어 확인하고, 실제 중복이 아니면 `_STATUS_MAP_WINDOW` 를 줄이거나 `_STATUS_MAP_MIN_KEYS` 를 올린 뒤 다시 측정한다. 조정 결과를 상수 주석에 실측값과 함께 남긴다.

`mobile_trigger.html` 이 이제 **맵 규칙으로도** 잡히는지 확인한다 — 그것이 이 태스크의 목적이다.

- [ ] **Step 6: 커밋**

```bash
git add scripts/check_frontend_gates.py tests/frontend/test_frontend_gates.py
git commit -m "fix(ci): FG-006 맵 탐지를 줄 단위에서 블록 단위로 + 취소 라벨 추가"
```

---

## Task 6: 글리프를 SSOT 로 — `_macros.html`

**Files:**
- Modify: `app/core/status_colors.py` (`TONE_GLYPHS` 추가)
- Modify: `app/web/status_view.py` (`tone_glyph` 추가)
- Modify: `app/api/routes_dashboard.py:30-33` (Jinja 전역 등록)
- Modify: `app/web/templates/dashboard/partials/_macros.html:3-11`
- Modify: `scripts/check_frontend_gates.py` (`FG006_ALLOWLIST` 에서 한 줄 삭제)
- Test: `tests/test_tone_glyph.py`

**Interfaces:**
- Consumes: Task 3 의 `app.core.status_colors`
- Produces: Jinja 전역 `tone_glyph(tone: str) -> str`

- [ ] **Step 1: 실패 테스트를 작성한다**

`tests/test_tone_glyph.py`:

```python
"""톤 → 글리프 — 템플릿이 자체 맵을 들지 않게 한다.

_macros.html 이 10개짜리 글리프 딕셔너리를 들고 있었다. 톤이 하나 늘면
그 템플릿만 조용히 기본값(○)으로 떨어진다.
"""

from __future__ import annotations

from app.core.status_colors import TONE_GLYPHS
from app.core.status_labels import STATUS_TONES
from app.web.status_view import tone_glyph


def test_every_tone_has_a_glyph() -> None:
    missing = [tone for tone in STATUS_TONES if tone not in TONE_GLYPHS]
    assert not missing, f"TONE_GLYPHS 에 없는 톤: {missing}"


def test_no_extra_tones() -> None:
    extra = [tone for tone in TONE_GLYPHS if tone not in STATUS_TONES]
    assert not extra, f"STATUS_TONES 에 없는 톤: {extra}"


def test_lookup_returns_the_mapped_glyph() -> None:
    assert tone_glyph("passed") == "✓"
    assert tone_glyph("error") == "×"


def test_view_only_tone_folds_onto_pending() -> None:
    """not_inspected 는 화면 전용 파생 상태다 — 축을 늘리지 않고 pending 으로 접는다."""
    assert tone_glyph("not_inspected") == tone_glyph("pending")


def test_unknown_tone_falls_back_without_raising() -> None:
    """템플릿 렌더 중 예외는 화면 전체를 죽인다 — 모르는 톤은 중립 글리프로."""
    assert tone_glyph("no_such_tone") == TONE_GLYPHS["pending"]
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `python3 -m pytest tests/test_tone_glyph.py -v`
Expected: FAIL — `ImportError: cannot import name 'TONE_GLYPHS'`

- [ ] **Step 3: `TONE_GLYPHS` 를 추가한다**

`app/core/status_colors.py` 의 `PALETTE` 아래에 더한다. 값은 `_macros.html:4-9` 의 현재 맵에서 그대로 가져온다.

```python
# 톤 → 글리프. 색과 같은 파일에 두는 이유: 둘 다 "톤의 표현" 이라는 하나의 개념이고,
# 흩어 두면 톤이 늘 때 한쪽만 갱신되는 사고가 난다.
TONE_GLYPHS: dict[str, str] = {
    "passed": "✓",
    "anomaly": "!",
    "error": "×",
    "running": "●",
    "waiting_input": "●",
    "blocked": "—",
    "skipped": "—",
    "cancelled": "—",
    "pending": "○",
}
```

- [ ] **Step 4: `tone_glyph` 를 추가한다**

`app/web/status_view.py` 의 import 에 `from app.core.status_colors import TONE_GLYPHS` 를 더하고, 파일 끝에 추가한다.

```python
# 화면 전용 파생 톤 → SSOT 톤. 일간 현황의 "점검 안 함" 은 상태 축의 톤이 아니라
# 집계 결과이므로 STATUS_TONES 를 늘리지 않고 여기서 접는다.
_VIEW_TONE_ALIASES = {"not_inspected": "pending"}


def tone_glyph(tone: str) -> str:
    """톤 → 글리프. 템플릿이 자체 맵을 들지 않게 하는 단일 경로.

    모르는 톤에 예외를 내지 않는다 — 템플릿 렌더 중 예외는 화면 전체를 죽이는데,
    글리프 하나가 중립으로 나오는 것이 훨씬 가벼운 실패다.
    """
    return TONE_GLYPHS.get(_VIEW_TONE_ALIASES.get(tone, tone), TONE_GLYPHS["pending"])
```

- [ ] **Step 5: Jinja 전역으로 등록한다**

`app/api/routes_dashboard.py` 의 전역 등록부(`templates.env.globals[...]` 가 모인 곳, 31-33행 부근)에 한 줄 더한다. import 도 함께 추가한다.

```python
from app.web.status_view import status_badge_view, tone_glyph
```

```python
templates.env.globals["tone_glyph"] = tone_glyph
```

`_macros.html` 은 `dashboard/partials/zone_b_matrix.html` 에서만 import 되고 그 화면은 `routes_dashboard.py` 가 렌더하므로 등록은 이 한 곳으로 충분하다.

- [ ] **Step 6: 템플릿의 맵을 지운다**

`app/web/templates/dashboard/partials/_macros.html:3-11` 을 다음으로 바꾼다.

```jinja
{% macro module_glyph(tone) -%}
<span class="dash-mod__glyph" aria-hidden="true">{{ tone_glyph(tone) }}</span>
{%- endmacro %}
```

- [ ] **Step 7: allowlist 에서 한 줄을 지운다**

`scripts/check_frontend_gates.py` 의 `FG006_ALLOWLIST` 에서 다음 두 줄(주석 포함)을 삭제한다.

```text
    # 상태→글리프 맵
    "app/web/templates/dashboard/partials/_macros.html",
```

- [ ] **Step 8: 테스트와 게이트를 확인한다**

Run: `python3 -m pytest tests/test_tone_glyph.py tests/test_dashboard_fragments_http.py -v`
Expected: 전부 PASS

Run: `python3 scripts/ci/run_all_gates.py --gate frontend_gates`
Expected: `{"passed": true, ...}`

- [ ] **Step 9: 커밋**

```bash
git add app/core/status_colors.py app/web/status_view.py app/api/routes_dashboard.py app/web/templates/dashboard/partials/_macros.html scripts/check_frontend_gates.py tests/test_tone_glyph.py
git commit -m "refactor(web): 대시보드 글리프 맵을 SSOT 로 이관 — FG-006 allowlist 1건 제거"
```

---

## Task 7: 필터·범례 목록을 SSOT 로 — `admin/runs.html` · `schedules.html`

**Files:**
- Modify: `app/web/status_view.py` (`StatusOption` · `status_options` 추가)
- Modify: `app/api/routes_dashboard.py` (Jinja 전역 등록)
- Modify: `app/web/templates/admin/runs.html:732-735, 773-776`
- Modify: `app/web/templates/schedules.html:250-255`
- Modify: `scripts/check_frontend_gates.py` (`FG006_ALLOWLIST` 에서 두 줄 삭제)
- Test: `tests/test_status_options.py`

**Interfaces:**
- Produces: Jinja 전역 `status_options(name: str) -> list[StatusOption]`, `StatusOption` 은 `.value` · `.label` 을 갖는 frozen dataclass

- [ ] **Step 1: 실패 테스트를 작성한다**

`tests/test_status_options.py`:

```python
"""이름 붙은 상태 목록 — 필터·범례가 라벨을 다시 적지 않게 한다.

admin/runs.html 은 같은 4개 항목을 한 파일 안에서 두 번 적고 있었다
(체크박스 팝오버 + 숨은 select). SSOT 와의 중복 이전에 자기들끼리 중복이었다.
"""

from __future__ import annotations

import pytest

from app.core.enums import RunStatus
from app.core.status_labels import run_status_label
from app.web.status_view import status_options


def test_admin_runs_filter_covers_the_four_terminal_states() -> None:
    values = [option.value for option in status_options("admin_runs")]
    assert values == [
        RunStatus.PASSED.value,
        RunStatus.ANOMALY.value,
        RunStatus.ERROR.value,
        RunStatus.CANCELLED.value,
    ]


def test_labels_come_from_the_ssot() -> None:
    for option in status_options("admin_runs"):
        assert option.label == run_status_label(RunStatus(option.value))


def test_schedule_legend_omits_cancelled() -> None:
    """예약 캘린더는 취소를 칠하지 않는다 — 목록이 화면마다 다르다는 사실을 고정한다."""
    values = [option.value for option in status_options("schedule_legend")]
    assert RunStatus.CANCELLED.value not in values
    assert values == [
        RunStatus.PASSED.value,
        RunStatus.ANOMALY.value,
        RunStatus.ERROR.value,
    ]


def test_unknown_name_raises_with_the_valid_names() -> None:
    """오타가 조용히 빈 목록이 되면 필터가 통째로 사라진다."""
    with pytest.raises(KeyError, match="admin_runs"):
        status_options("no_such_list")
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `python3 -m pytest tests/test_status_options.py -v`
Expected: FAIL — `ImportError: cannot import name 'status_options'`

- [ ] **Step 3: `status_options` 를 추가한다**

`app/web/status_view.py` 의 import 에 `run_status_label` 이 이미 있다. 파일 끝에 추가한다.

```python
@dataclass(frozen=True)
class StatusOption:
    """필터 체크박스·`<option>`·범례가 쓰는 최소 표현."""

    value: str
    label: str


# 화면마다 보여줄 상태 목록이 다르다. 목록을 이름으로 부르게 해서
# "왜 이 화면엔 취소가 없나" 가 코드에 남게 한다.
_STATUS_OPTION_SETS: dict[str, tuple[RunStatus, ...]] = {
    # 관리자 Run 목록 필터 — 종료 결과 전체 + 취소
    "admin_runs": (
        RunStatus.PASSED,
        RunStatus.ANOMALY,
        RunStatus.ERROR,
        RunStatus.CANCELLED,
    ),
    # 예약 캘린더 범례 — 취소된 Run 은 캘린더에 칠하지 않는다
    "schedule_legend": (RunStatus.PASSED, RunStatus.ANOMALY, RunStatus.ERROR),
}


def status_options(name: str) -> list[StatusOption]:
    """이름 붙은 상태 목록 → (값, 라벨). 라벨은 status_labels.py 가 유일한 출처다."""
    try:
        statuses = _STATUS_OPTION_SETS[name]
    except KeyError:
        msg = (
            f"알 수 없는 상태 목록 이름: {name!r}. "
            f"{sorted(_STATUS_OPTION_SETS)} 중 하나여야 합니다."
        )
        raise KeyError(msg) from None
    return [StatusOption(status.value, run_status_label(status)) for status in statuses]
```

- [ ] **Step 4: Jinja 전역으로 등록한다**

`app/api/routes_dashboard.py` 의 import 를 `from app.web.status_view import status_badge_view, status_options, tone_glyph` 로 바꾸고 한 줄 더한다.

```python
templates.env.globals["status_options"] = status_options
```

- [ ] **Step 5: `admin/runs.html` 의 두 목록을 순회로 바꾼다**

체크박스 팝오버(732-735행 부근)를 다음으로 바꾼다.

```html
            {% for option in status_options("admin_runs") %}
            <label class="adm-filter-option-row"><input type="checkbox" class="adm-filter-option" data-group="status" value="{{ option.value }}" /> {{ option.label }}</label>
            {% endfor %}
```

숨은 `<select>`(773-776행 부근)를 다음으로 바꾼다.

```html
        {% for option in status_options("admin_runs") %}
        <option value="{{ option.value }}">{{ option.label }}</option>
        {% endfor %}
```

- [ ] **Step 6: `schedules.html` 의 범례를 바꾼다**

250-255행의 범례에서 **상태 세 줄만** 순회로 바꾼다. `planned`(예정)·`missed`(누락)는 상태 축이 아니라 스케줄 뷰 상태이므로 **그대로 둔다.**

```html
          <span class="inline-flex items-center gap-1"><i class="schedc-block !cursor-default !p-1" data-state="planned"></i>예정</span>
          {% for option in status_options("schedule_legend") %}
          <span class="inline-flex items-center gap-1"><i class="schedc-block !cursor-default !p-1" data-state="{{ option.value }}"></i>{{ option.label }}</span>
          {% endfor %}
          <span class="inline-flex items-center gap-1"><i class="schedc-block !cursor-default !p-1" data-state="missed"></i>누락</span>
          <span class="inline-flex items-center gap-1"><i class="schedc-block !cursor-default !p-1" data-state="planned" data-suite="1"></i>Suite</span>
```

- [ ] **Step 7: allowlist 에서 두 줄을 지운다**

`FG006_ALLOWLIST` 에서 다음 네 줄(주석 포함)을 삭제한다.

```text
    # <option value="PASSED">정상</option> 류 라벨 중복 + 필터 체크박스
    "app/web/templates/admin/runs.html",
    # 범례의 상태 라벨 중복
    "app/web/templates/schedules.html",
```

- [ ] **Step 8: 렌더 결과를 확인한다**

두 화면이 실제로 렌더되고 목록이 나오는지 본다.

Run: `python3 -m pytest tests/test_status_options.py -v && python3 scripts/ci/run_all_gates.py --gate frontend_gates`
Expected: 테스트 PASS, 게이트 `{"passed": true, ...}`

Run: `python3 -m pytest tests/ -q -k "schedule or admin_runs or dashboard"`
Expected: 기존 테스트 전부 PASS

- [ ] **Step 9: 커밋**

```bash
git add app/web/status_view.py app/api/routes_dashboard.py app/web/templates/admin/runs.html app/web/templates/schedules.html scripts/check_frontend_gates.py tests/test_status_options.py
git commit -m "refactor(web): 필터·범례 상태 목록을 SSOT 로 이관 — FG-006 allowlist 2건 제거"
```

---

## Task 8: 모바일 상태 맵을 서버 주입으로 — allowlist 0

**Files:**
- Modify: `app/web/status_view.py` (`mobile_status_view_map` 추가)
- Modify: `app/api/routes_trigger.py:31-33` (Jinja 전역 등록)
- Modify: `app/web/templates/mobile_trigger.html:90-98`
- Modify: `scripts/check_frontend_gates.py` (`FG006_ALLOWLIST` **삭제**)
- Test: `tests/test_mobile_status_view.py`

**Interfaces:**
- Produces: Jinja 전역 `mobile_status_view_map() -> dict[str, dict[str, object]]` — 키는 `RunStatus` 값, 각 항목은 `{"label": str, "cls": str, "spin": bool}`

- [ ] **Step 1: 실패 테스트를 작성한다**

`tests/test_mobile_status_view.py`:

```python
"""모바일 즉시 점검 화면의 상태 맵 — 드리프트가 실제로 일어났던 자리.

이 템플릿의 인라인 STATUS_VIEW 는 8개 항목 중 4개가 SSOT 와 어긋나 있었고
(대기→"진행 중", 실행 중→"진행 중", 입력 대기→"인증번호 대기", 취소→"취소됨")
FG-006 은 하나도 잡지 못했다. 서버가 SSOT 에서 만들어 내려보낸다.
"""

from __future__ import annotations

from app.core.enums import RunStatus
from app.core.status_labels import run_status_label
from app.web.status_view import mobile_status_view_map

# 이 화면에만 있는 레거시 배지 클래스. P4 가 화면을 이관하면 사라진다.
_LEGACY_CLASSES = {
    "badge-running",
    "badge-waiting",
    "badge-passed",
    "badge-anomaly",
    "badge-error",
    "badge-cancelled",
}


def test_map_covers_every_run_status() -> None:
    view = mobile_status_view_map()
    for status in RunStatus:
        assert status.value in view, status


def test_labels_come_from_the_ssot() -> None:
    view = mobile_status_view_map()
    for status in RunStatus:
        assert view[status.value]["label"] == run_status_label(status), status


def test_classes_are_all_defined_in_the_template() -> None:
    """없는 클래스를 주면 배지가 무스타일로 나간다 — 템플릿 CSS 와 맞춘다."""
    view = mobile_status_view_map()
    for status in RunStatus:
        assert view[status.value]["cls"] in _LEGACY_CLASSES, status


def test_only_in_progress_states_spin() -> None:
    """spin 은 SSOT 축이 아니라 뷰 규칙이다 — 진행을 나타내는 상태만 돈다."""
    view = mobile_status_view_map()
    spinning = {value for value, item in view.items() if item["spin"]}
    assert spinning == {RunStatus.PENDING.value, RunStatus.RUNNING.value}
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `python3 -m pytest tests/test_mobile_status_view.py -v`
Expected: FAIL — `ImportError: cannot import name 'mobile_status_view_map'`

- [ ] **Step 3: `mobile_status_view_map` 을 추가한다**

`app/web/status_view.py` 파일 끝에 추가한다. import 에 `run_status_badge_tone` 이 이미 있다.

```python
# 모바일 즉시 점검 화면의 레거시 배지 클래스. 톤 이름과 1:1 이 아니다 —
# 이 화면엔 badge-pending 이 없고(대기도 진행처럼 보인다), waiting_input 은
# badge-waiting 이다. P4 가 이 화면을 이관할 때 톤 기반으로 정리한다.
_MOBILE_TONE_CLASSES = {
    "pending": "badge-running",
    "running": "badge-running",
    "waiting_input": "badge-waiting",
    "passed": "badge-passed",
    "anomaly": "badge-anomaly",
    "error": "badge-error",
    "cancelled": "badge-cancelled",
}

# 진행을 나타내는 상태만 스피너를 돌린다. SSOT 축이 아니라 이 화면의 뷰 규칙이다.
_MOBILE_SPINNING = frozenset({RunStatus.PENDING, RunStatus.RUNNING})


def mobile_status_view_map() -> dict[str, dict[str, object]]:
    """모바일 즉시 점검 화면의 상태 → 표현 맵.

    템플릿이 이 맵을 인라인으로 들고 있던 동안 라벨 8개 중 4개가 SSOT 와
    어긋났고 FG-006 은 하나도 잡지 못했다(P3-4 §1.3). 서버가 만들어 내려보낸다.
    """
    return {
        status.value: {
            "label": run_status_label(status),
            "cls": _MOBILE_TONE_CLASSES[run_status_badge_tone(status)],
            "spin": status in _MOBILE_SPINNING,
        }
        for status in RunStatus
    }
```

- [ ] **Step 4: Jinja 전역으로 등록한다**

`app/api/routes_trigger.py` 의 전역 등록부(31-33행)에 추가한다.

```python
from app.web.status_view import mobile_status_view_map
```

```python
templates.env.globals["mobile_status_view_map"] = mobile_status_view_map
```

- [ ] **Step 5: 템플릿의 인라인 맵을 지운다**

`app/web/templates/mobile_trigger.html:90-98` 의 `const STATUS_VIEW = { ... };` 를 다음 한 줄로 바꾼다.

```html
        const STATUS_VIEW = {{ mobile_status_view_map() | tojson }};
```

`tojson` 은 Jinja2 기본 필터이며 `<script>` 안에서 안전하게 이스케이프한다.

- [ ] **Step 6: `FG006_ALLOWLIST` 를 통째로 삭제한다**

`scripts/check_frontend_gates.py` 에서 `FG006_ALLOWLIST` 딕셔너리와 그 위 주석 블록을 지우고, `check_fg006_no_template_status_literals` 안의 다음 두 줄도 지운다.

```text
        if rel in FG006_ALLOWLIST:
            continue
```

함수 독스트링에 한 문장을 더한다.

```text
    allowlist 는 P3-4 가 마지막 템플릿을 이관하며 없앴다 — 예외 없는 규칙이다.
```

- [ ] **Step 7: 테스트와 게이트를 확인한다**

Run: `python3 -m pytest tests/test_mobile_status_view.py tests/frontend/test_frontend_gates.py -v`
Expected: 전부 PASS

Run: `python3 scripts/ci/run_all_gates.py --gate frontend_gates`
Expected: `{"passed": true, ...}` — FG-006 위반 0건, allowlist 없음

- [ ] **Step 8: 라벨 변경을 눈으로 확인하고 기록한다**

이 태스크는 **사용자 눈에 보이는 문구 4건**을 바꾼다.

| status | 이전 | 이후 |
| --- | --- | --- |
| `PENDING` | 진행 중 | 대기 |
| `RUNNING` | 진행 중 | 실행 중 |
| `WAITING_INPUT` | 인증번호 대기 | 입력 대기 |
| `CANCELLED` | 취소됨 | 취소 |

모바일 페이지를 열어 배지가 정상 렌더되는지 확인한다. **"인증번호 대기"→"입력 대기"가 OTP 맥락에서 정보를 잃는다고 판단되면, SSOT 라벨 자체를 바꿔 전 화면이 함께 바뀌게 하거나 화면별 override 를 도입할지 사용자에게 확인한다** — 이 템플릿에만 다시 적는 것은 방금 없앤 문제 그대로다(설계 D7).

- [ ] **Step 9: 커밋**

```bash
git add app/web/status_view.py app/api/routes_trigger.py app/web/templates/mobile_trigger.html scripts/check_frontend_gates.py tests/test_mobile_status_view.py
git commit -m "refactor(web): 모바일 상태 맵을 서버 주입으로 — FG-006 allowlist 0"
```

---

## Task 9: 리포트 → 상황판 딥링크

**Files:**
- Modify: `app/core/settings.py` (`public_base_url` 추가, `wall_enabled` 아래)
- Modify: `app/notifications/report_renderer.py:973-1008` (`render_daily_report_html` 시그니처)
- Modify: `app/notifications/daily_report_email.py:107-108` (렌더 호출)
- Modify: `.env.example` · `docs/INSTALL.md`
- Test: `tests/test_daily_report_wall_link.py`

**Interfaces:**
- Consumes: Task 4 의 `report_renderer` 색 상수
- Produces: `render_daily_report_html(context: dict, *, wall_url: str | None = None) -> str`

- [ ] **Step 1: 실패 테스트를 작성한다**

`tests/test_daily_report_wall_link.py`:

```python
"""일간 리포트의 상황판 딥링크 — 기본은 링크 없는 자족적 메일.

P3-3 D6 은 링크를 뺐다. 이유가 둘이었는데 "대시보드는 로그인이 필요하다" 쪽은
P3-2 가 /wall 을 비인증으로 열며 해소됐고, "공개 URL env 가 없다" 만 남았다.
이 테스트가 고정하는 것: env 를 켠 사람만 링크를 얻는다.
"""

from __future__ import annotations

import pytest

from app.notifications.report_renderer import render_daily_report_html

CONTEXT = {
    "headline": "정상",
    "tone": "passed",
    "status_value": "PASSED",
    "date_label": "2026-08-21",
    "kpis": [("통과율", 100, "%")],
    "systems": [],
    "issues": [],
}


def test_no_link_when_wall_url_is_absent() -> None:
    """기본값이 자족적 메일이다 — 기존 동작이 바뀌지 않는다."""
    html = render_daily_report_html(CONTEXT)
    assert "http://" not in html
    assert "https://" not in html


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_no_link_for_blank_wall_url(blank) -> None:
    """빈 문자열 env 가 'http:///wall' 같은 깨진 링크가 되지 않아야 한다."""
    html = render_daily_report_html(CONTEXT, wall_url=blank)
    assert "http" not in html


def test_link_is_rendered_when_wall_url_is_given() -> None:
    html = render_daily_report_html(CONTEXT, wall_url="https://e2e.example.com/wall")
    assert 'href="https://e2e.example.com/wall"' in html


def test_link_text_is_korean() -> None:
    html = render_daily_report_html(CONTEXT, wall_url="https://e2e.example.com/wall")
    assert "상황판" in html
```

`tests/test_daily_report_email.py` 에 서비스 쪽 분기를 더한다.

```python
def test_wall_url_is_none_when_public_base_url_is_unset() -> None:
    from app.notifications.daily_report_email import resolve_wall_url

    assert resolve_wall_url(public_base_url="", wall_enabled=True) is None


def test_wall_url_is_none_when_wall_is_disabled() -> None:
    """상황판이 꺼져 있으면 그 URL 은 404 다 — 죽은 링크를 보내지 않는다."""
    from app.notifications.daily_report_email import resolve_wall_url

    assert resolve_wall_url(public_base_url="https://e2e.example.com", wall_enabled=False) is None


def test_wall_url_joins_without_double_slash() -> None:
    from app.notifications.daily_report_email import resolve_wall_url

    assert (
        resolve_wall_url(public_base_url="https://e2e.example.com/", wall_enabled=True)
        == "https://e2e.example.com/wall"
    )
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_wall_link.py tests/test_daily_report_email.py -v -k "wall"`
Expected: FAIL — `TypeError: render_daily_report_html() got an unexpected keyword argument 'wall_url'` 및 `ImportError: resolve_wall_url`

- [ ] **Step 3: 설정을 추가한다**

`app/core/settings.py` 의 `wall_enabled` 바로 아래에 추가한다.

```python
    # 메일에 넣을 공개 주소(예: https://e2e.example.com). 기본은 빈 문자열 —
    # 배포 환경마다 다르고, 잘못된 URL 이 든 메일은 회수할 수 없다(P3-4 D6).
    # 비어 있으면 일간 리포트는 링크 없이 지금처럼 자족적으로 나간다.
    public_base_url: str = Field(default="", validation_alias="E2E_PUBLIC_BASE_URL")
```

- [ ] **Step 4: 렌더러에 링크를 추가한다**

`app/notifications/report_renderer.py` 의 `render_daily_report_html` 시그니처와 독스트링을 바꾸고, `_footer()` 앞에 링크 블록을 넣는다.

```python
def render_daily_report_html(context: dict, *, wall_url: str | None = None) -> str:
    """일간 리포트 메일 HTML.

    Run/Suite 보고서와 같은 셸·헬퍼를 쓴다. `wall_url` 이 주어질 때만 상황판
    링크를 넣는다 — 공개 주소가 설정되지 않은 배포에서는 링크 없는 자족적
    메일이 기본이다(P3-3 D6 · P3-4 §3.4).
    """
```

`body += _section(3, "확인 필요", issue_html, accent)` 다음, `body += _footer()` **앞에** 추가한다.

```python
    if wall_url and wall_url.strip():
        body += (
            f'<div style="margin:20px 0 4px;font-size:14px;">'
            f'<a href="{escape(wall_url.strip())}" '
            f'style="color:{INFO_COLOR};text-decoration:none;font-weight:700;">'
            f"실시간 상황판 열기 →</a></div>"
        )
```

`escape` 는 이 모듈이 이미 import 하고 있다.

- [ ] **Step 5: 서비스가 URL 을 해석해 넘기게 한다**

`app/notifications/daily_report_email.py` 에 함수를 추가한다(`resolve_daily_report_recipients` 아래).

```python
def resolve_wall_url(*, public_base_url: str, wall_enabled: bool) -> str | None:
    """공개 주소 + 상황판 스위치 → 메일에 넣을 /wall 절대 URL. 없으면 None.

    두 조건이 모두 참일 때만 링크를 만든다. 상황판이 꺼져 있으면 그 URL 은
    404 이므로(app/api/routes_wall.py 의 wall_enabled 의존성) 죽은 링크가 된다.
    """
    base = (public_base_url or "").strip().rstrip("/")
    if not base or not wall_enabled:
        return None
    return f"{base}/wall"
```

`send_for` 의 렌더 호출을 바꾼다.

```python
            report = build_daily_report(summary, date_label=date_label)
            html = render_daily_report_html(
                report,
                wall_url=resolve_wall_url(
                    public_base_url=getattr(self._config, "public_base_url", ""),
                    wall_enabled=getattr(self._config, "wall_enabled", False),
                ),
            )
```

`self._config` 는 `EmailNotificationConfig` 다. 두 값이 거기에 없으면 `getattr` 기본값으로 **링크 없음**이 된다 — 안전한 방향이다. 배선에서 두 값을 실어 보내려면 `app/composition/container.py` 의 `EmailNotificationConfig` 생성부를 확인하고, 없으면 `get_settings()` 에서 직접 읽어 서비스 생성자에 넘기는 방식으로 바꾼다. **어느 쪽이든 테스트가 세 분기를 모두 덮어야 한다.**

- [ ] **Step 6: 문서에 환경변수를 적는다**

`.env.example` 의 `E2E_WALL_ENABLED=true` 아래에 추가한다.

```bash
# 메일에 넣을 공개 주소(예: https://e2e.example.com). 비우면 일간 리포트에
# 상황판 링크를 넣지 않는다. E2E_WALL_ENABLED=false 면 설정해도 링크가 안 나간다.
E2E_PUBLIC_BASE_URL=
```

`docs/INSTALL.md` 의 환경변수 표에서 `E2E_WALL_ENABLED` 행 아래에 추가한다.

```markdown
| `E2E_PUBLIC_BASE_URL` | 메일에 넣을 공개 주소. 비면 일간 리포트에 상황판 링크 없음(기본) |
```

- [ ] **Step 7: 테스트와 게이트를 확인한다**

Run: `python3 -m pytest tests/test_daily_report_wall_link.py tests/test_daily_report_email.py tests/test_daily_report_render.py tests/test_container_lifecycle.py -v`
Expected: 전부 PASS

Run: `python3 scripts/ci/run_all_gates.py --gate docs_consistency`
Expected: `{"passed": true, ...}` — 새 env 가 코드·문서 양쪽에 있다

- [ ] **Step 8: 커밋**

```bash
git add app/core/settings.py app/notifications/report_renderer.py app/notifications/daily_report_email.py .env.example docs/INSTALL.md tests/test_daily_report_wall_link.py tests/test_daily_report_email.py
git commit -m "feat(notifications): 일간 리포트에 상황판 딥링크 — 기본 꺼짐"
```

---

## 마무리: 전체 검증

- [ ] **Step 1: 전체 게이트**

Run: `npm run build && python3 scripts/ci/run_all_gates.py --profile full`
Expected: `{"passed": true, "profile": "full", "gate_count": 16}`

- [ ] **Step 2: 예외가 정말 0 인지 확인한다**

```bash
PYTHONIOENCODING=utf-8 python3 -c "
import sys; sys.path.insert(0,'.')
import scripts.check_frontend_gates as g
assert not hasattr(g, 'FG001_EXCEPTIONS'), 'FG-001 예외가 남아 있습니다'
assert not hasattr(g, 'FG006_ALLOWLIST'), 'FG-006 allowlist 가 남아 있습니다'
assert len(g.CHECKS) == 7, g.CHECKS
print('예외 0 · 체크 7개 확인')
"
grep -rn 'cdn.jsdelivr\|unpkg\|cdnjs' app/web/templates/ && echo '외부 CDN 잔존!' || echo 'CDN 0 확인'
```

- [ ] **Step 3: 수동 확인 (사람이 브라우저로)**

이 항목들은 자동화하지 않는다. **CDN 을 실제로 끊고 확인하는 것이 §5 의 진짜 합격 조건이다.**

- [ ] 브라우저 개발자도구에서 `cdn.jsdelivr.net` 을 차단한 채 `/admin/runs` — 추세선과 히트맵이 그려지는가
- [ ] 같은 조건으로 `/admin/stats` — Plotly 차트가 그려지는가
- [ ] 같은 조건으로 `/insights` — 탭을 전환하면 차트가 그려지는가
- [ ] `/dashboard` 네트워크 탭에 plotly·echarts·chart 번들이 **없는가**
- [ ] `/wall` 네트워크 탭에도 없는가
- [ ] 모바일 즉시 점검 페이지의 상태 배지 4종 문구가 바뀐 것이 어색하지 않은가(Task 8 Step 8)
- [ ] 실제 일간 리포트 메일을 Outlook·Gmail 에서 열어 상태 색이 어색하지 않은가

---

## Self-Review

**스펙 커버리지**

| 스펙 | 태스크 |
| --- | --- |
| §3.1 CDN 0 — 브리지 엔트리 | 1 · 2 |
| §3.1 만료 조건 명시 | 1 (엔트리 파일 주석) · 6 Step 3 (P4 안내) |
| §3.2 팔레트 이사 | 3 |
| §3.2 메일 상태 색 10개 파생 | 4 |
| §3.2 레이아웃 색 7개 불변 | 4 (`test_mail_layout_colors_are_untouched`) |
| §3.3 (a) 글리프 | 6 |
| §3.3 (b) 필터·범례 | 7 |
| §3.3 (c) 모바일 맵 | 8 |
| §3.3 게이트 결함 2건 | 5 |
| §3.4 딥링크 | 9 |
| §3.5 FG-001 예외 삭제 | 2 |
| §3.5 FG-006 allowlist 삭제 | 6 · 7 · 8 (한 줄씩) |
| §3.5 FG-007 신설 | 4 |
| §5 CDN 차단 렌더 확인 | 마무리 Step 3 |

**타입 일관성**

- `PALETTE` (Task 3 생성) → Task 4 · 6 이 소비. 형태 `dict[str, dict[str, str]]` 로 일치
- `TONE_GLYPHS` (Task 6) → `tone_glyph` 만 소비
- `StatusOption` (Task 7) → 템플릿이 `.value` · `.label` 로 접근
- `render_daily_report_html(context, *, wall_url=None)` (Task 9) → Task 4 Step 7 의 검증 스크립트는 인자 없이 호출하므로 기본값과 호환

**남는 위험 (정직하게)**

- Task 5 의 `_STATUS_MAP_WINDOW = 12` 는 **실측으로 확정해야 하는 값**이다. Step 5 의 오탐 측정이 이 계획에서 가장 조정 가능성이 높은 지점이다.
- Task 9 Step 5 의 `EmailNotificationConfig` 배선은 **현물 확인이 필요하다.** 두 값이 그 객체에 없으면 `get_settings()` 경로로 바꿔야 하며, 그 판단은 구현자가 코드를 보고 내린다. `getattr` 기본값 덕에 어느 쪽이든 실패 방향은 "링크 없음" 이다.
- Task 8 의 라벨 4건 변경은 **되돌릴 수 있는 사용자 가시 변경**이다. 실물 확인 후 사용자와 재검토한다.

---

## P3-4 이후 — P4 로 넘기는 것

이 계획이 P4 에 남기는 것:

- `app/web/frontend/entries/vendor-{chart,echarts,plotly}.ts` 3개 — **만료 조건이 파일 주석에 적혀 있다.** `admin-runs.js` 이관 시 chart·echarts 를, `insights.js`·`admin-stats.js` 둘 다 이관된 시점에 plotly 를 삭제
- `app/web/frontend/types/vendor-globals.d.ts` — 위 셋이 사라지면 함께 삭제
- `app/web/status_view.py` 의 `_MOBILE_TONE_CLASSES` — 모바일 화면 이관 시 톤 기반으로 정리
- `FG005_ALLOWLIST` 14줄 · `FG004_ALLOWLIST` 2줄 — 이관하며 한 줄씩
- 레거시 JS 13파일 8,917줄 — 타입 + 책임 분리 + Vitest 로
