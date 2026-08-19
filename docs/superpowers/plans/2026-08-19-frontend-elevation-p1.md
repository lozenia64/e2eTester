# 프론트엔드 고도화 P1 (기반) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 화면을 바꾸지 않은 채 프론트엔드에 빌드·토큰·게이트를 도입하고, 외부 CDN 런타임 의존을 제거하며, 상태 정의를 `app/core/status_labels.py` 단일 SSOT 로 수렴시킨다.

**Architecture:** Jinja 서버 렌더를 유지한 채 Vite 다중 엔트리 빌드를 얹는다. 상태 토큰(CSS 변수 + TS 타입)은 파이썬이 `status_labels.py` 에서 생성하고, CI 가 재생성 diff 로 어긋남을 차단한다. 새 프론트 게이트 FG-001~005 를 `scripts/ci/gates.py` Tier 0 에 배선해 백엔드 AG 게이트와 동일한 강제력을 부여한다.

**Tech Stack:** Vite 6 · TypeScript 5 · Tailwind CSS 4 (PostCSS 빌드) · htmx 2 · Alpine 3 · Vitest 3 · Jinja2 · pytest

**Spec:** `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md` (Step 0~2)

## Global Constraints

- UI·로그·README 문자열은 **한국어**. (`AGENTS.md`)
- **라이트 단일 팔레트.** 다크모드·테마 전환 기제를 만들지 않는다. `prefers-color-scheme` 분기 금지.
- **SPA 전환 금지.** React/Vue 등 프레임워크를 도입하지 않는다. 마크업 SSOT 는 Jinja 매크로.
- **톤 축은 정확히 9개**: `passed` `anomaly` `error` `running` `waiting_input` `blocked` `skipped` `cancelled` `pending`
- **엔트리·컴포넌트 파일 400줄 상한** (FG-004).
- `app/web/frontend/**` 내 하드코딩 hex 금지 (FG-002). 색은 토큰만.
- 템플릿에 외부 CDN `<script>`/`<link>` 금지 (FG-001).
- Windows 에서 `.sh` 실행은 `bash <path>.sh`.
- PR 전 `python3 scripts/ci/run_all_gates.py --profile full`.
- **P1 의 성공 기준은 "화면이 바뀌지 않는 것"이다.** 시각적 개선은 P2 의 몫이다.

---

## File Structure

| 파일 | 책임 |
| --- | --- |
| `app/core/status_labels.py` (수정) | `STATUS_TONES` 튜플 추가 — 톤 축의 명시적 SSOT |
| `scripts/gen_frontend_tokens.py` (신규) | 톤 → CSS 변수 · TS 타입/라벨 생성. `--check` 로 diff 검증 |
| `app/web/frontend/styles/tokens.generated.css` (생성물) | semantic 토큰 9톤 × 4변형 |
| `app/web/frontend/lib/status.generated.ts` (생성물) | `StatusTone` union + 라벨 맵 |
| `package.json` · `vite.config.ts` · `tsconfig.json` · `postcss.config.js` (신규) | 빌드 툴체인 |
| `app/web/frontend/entries/main.ts` (신규) | 전 페이지 공용 엔트리 — CSS 번들 + htmx/Alpine self-host |
| `app/web/frontend/styles/app.css` · `dashboard.css` (이동) | `static/` 에서 이동. 번들 대상 |
| `app/web/templates/_assets.html` (신규) | Vite manifest 를 읽어 해시 파일명을 해석하는 Jinja 매크로 |
| `app/web/asset_manifest.py` (신규) | manifest.json 로더 (Jinja 전역 함수로 주입) |
| `scripts/check_frontend_gates.py` (신규) | FG-001~005 |
| `scripts/ci/gates.py` (수정) | 게이트 4종 배선 + Tier 0 |
| `app/web/frontend/components/status-badge/` (신규) | `macro.jinja` · `index.ts` · `styles.css` |
| `tests/frontend/` (신규) | 파이썬 측 테스트 (생성기 · manifest · 게이트) |
| `app/web/frontend/**/*.test.ts` (신규) | Vitest — 순수 로직 |

---

## Task 1: 톤 축 SSOT 확정 + 토큰 생성기

**Files:**
- Modify: `app/core/status_labels.py`
- Create: `scripts/gen_frontend_tokens.py`
- Create: `tests/frontend/__init__.py`
- Test: `tests/frontend/test_status_tones.py`, `tests/frontend/test_gen_frontend_tokens.py`

**Interfaces:**
- Consumes: `app/core/status_labels.py` 의 `run_status_badge_tone` · `module_status_badge_tone` · `RUN_STATUS_LABELS` · `MODULE_STATUS_LABELS` · `SUITE_STATUS_LABELS`
- Produces:
  - `app.core.status_labels.STATUS_TONES: tuple[str, ...]` — 9개 톤 이름
  - `scripts/gen_frontend_tokens.py` 의 `render_css() -> str`, `render_ts() -> str`, `main(argv: list[str]) -> int` (`--check` 지원, 불일치 시 1 반환)
  - 생성물 경로 상수 `CSS_OUT = "app/web/frontend/styles/tokens.generated.css"`, `TS_OUT = "app/web/frontend/lib/status.generated.ts"`

- [ ] **Step 1: 톤 축 SSOT 테스트를 먼저 작성한다**

`tests/frontend/test_status_tones.py`:

```python
"""톤 축(STATUS_TONES)이 실제 badge_tone 함수의 출력 전체를 덮는지 검증."""

from app.core.enums import ModuleStatus, RunStatus
from app.core.status_labels import (
    STATUS_TONES,
    module_status_badge_tone,
    run_status_badge_tone,
)


def test_status_tones_has_exactly_nine_tones():
    assert STATUS_TONES == (
        "passed",
        "anomaly",
        "error",
        "running",
        "waiting_input",
        "blocked",
        "skipped",
        "cancelled",
        "pending",
    )


def test_every_run_status_maps_into_status_tones():
    for status in RunStatus:
        assert run_status_badge_tone(status) in STATUS_TONES, status


def test_every_module_status_maps_into_status_tones():
    for status in ModuleStatus:
        assert module_status_badge_tone(status) in STATUS_TONES, status


def test_no_unused_tone():
    """선언만 되고 아무 상태도 매핑되지 않는 톤이 없어야 한다(죽은 토큰 차단)."""
    produced = {run_status_badge_tone(s) for s in RunStatus}
    produced |= {module_status_badge_tone(s) for s in ModuleStatus}
    assert produced == set(STATUS_TONES)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_status_tones.py -v`
Expected: FAIL — `ImportError: cannot import name 'STATUS_TONES'`

- [ ] **Step 3: `STATUS_TONES` 를 추가한다**

`app/core/status_labels.py` 의 `run_status_badge_tone` 정의 **바로 앞**에 삽입:

```python
# 배지·점·막대의 색 축(SSOT). 프론트 토큰(tokens.generated.css)과
# TS union(status.generated.ts)이 이 튜플에서 생성된다.
# 순서는 생성물의 출력 순서이므로 임의로 바꾸지 않는다.
STATUS_TONES: tuple[str, ...] = (
    "passed",
    "anomaly",
    "error",
    "running",
    "waiting_input",
    "blocked",
    "skipped",
    "cancelled",
    "pending",
)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/frontend/test_status_tones.py -v`
Expected: PASS (4 passed)

`test_no_unused_tone` 이 실패하면 톤 목록과 실제 매핑이 어긋난 것이다. 튜플이 아니라 **`*_badge_tone()` 쪽을 확인**한다.

- [ ] **Step 5: 생성기 테스트를 작성한다**

`tests/frontend/test_gen_frontend_tokens.py`:

```python
from app.core.status_labels import MODULE_STATUS_LABELS, STATUS_TONES
from scripts.gen_frontend_tokens import render_css, render_ts

VARIANTS = ("solid", "surface", "text", "border")


def test_css_declares_every_tone_and_variant():
    css = render_css()
    for tone in STATUS_TONES:
        for variant in VARIANTS:
            assert f"--st-{tone}-{variant}:" in css, (tone, variant)


def test_css_has_no_dark_mode_branch():
    """라이트 단일 팔레트 — 테마 분기를 만들지 않는다."""
    css = render_css()
    assert "prefers-color-scheme" not in css
    assert "[data-theme" not in css


def test_ts_union_matches_status_tones():
    ts = render_ts()
    expected = " | ".join(f'"{tone}"' for tone in STATUS_TONES)
    assert f"export type StatusTone = {expected};" in ts


def test_ts_carries_korean_module_labels():
    ts = render_ts()
    assert '"passed": "정상"' in ts
    assert '"error": "점검실패"' in ts
    # 파이썬 라벨과 실제로 같은 출처인지 확인
    assert MODULE_STATUS_LABELS[list(MODULE_STATUS_LABELS)[0]] in ts


def test_ts_label_keys_are_lowercase():
    """enum 값은 대문자지만 프론트 규약은 소문자다. 생성 시점에 맞춘다."""
    ts = render_ts()
    assert '"PASSED"' not in ts
    assert '"waiting_input": "입력 대기"' in ts


def test_generated_files_carry_do_not_edit_banner():
    for text in (render_css(), render_ts()):
        assert "자동 생성" in text
        assert "scripts/gen_frontend_tokens.py" in text
```

- [ ] **Step 6: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_gen_frontend_tokens.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.gen_frontend_tokens'`

- [ ] **Step 7: 생성기를 구현한다**

`scripts/gen_frontend_tokens.py`:

```python
"""status_labels.py → 프론트 토큰(CSS) · 타입/라벨(TS) 생성기.

생성물은 커밋한다(빌드 없이 코드를 읽을 수 있어야 하므로). CI 는 `--check` 로
재생성 diff 를 검사해 어긋남을 차단한다 — docs_consistency 와 동일한 패턴.

사용:
    python3 scripts/gen_frontend_tokens.py            # 생성/갱신
    python3 scripts/gen_frontend_tokens.py --check    # 불일치 시 exit 1
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.core.status_labels import (
    MODULE_STATUS_LABELS,
    RUN_STATUS_LABELS,
    STATUS_TONES,
    SUITE_STATUS_LABELS,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CSS_OUT = REPO_ROOT / "app/web/frontend/styles/tokens.generated.css"
TS_OUT = REPO_ROOT / "app/web/frontend/lib/status.generated.ts"

BANNER_CSS = (
    "/* 자동 생성 파일 — 직접 수정하지 마세요.\n"
    "   출처: app/core/status_labels.py\n"
    "   생성: python3 scripts/gen_frontend_tokens.py */\n"
)
BANNER_TS = (
    "// 자동 생성 파일 — 직접 수정하지 마세요.\n"
    "// 출처: app/core/status_labels.py\n"
    "// 생성: python3 scripts/gen_frontend_tokens.py\n"
)

# 톤별 팔레트(라이트 전용). Tailwind 표준 색값을 쓰되 기존 --st-* 선택을 계승한다.
# solid=칩/점, surface=배경, text=전경, border=테두리.
PALETTE: dict[str, dict[str, str]] = {
    "passed": {"solid": "#10b981", "surface": "#d1fae5", "text": "#047857", "border": "#6ee7b7"},
    "anomaly": {"solid": "#f59e0b", "surface": "#fef3c7", "text": "#b45309", "border": "#fcd34d"},
    "error": {"solid": "#ef4444", "surface": "#fee2e2", "text": "#b91c1c", "border": "#fca5a5"},
    "running": {"solid": "#3b82f6", "surface": "#dbeafe", "text": "#1d4ed8", "border": "#93c5fd"},
    # waiting_input 은 사람의 OTP 입력을 기다리는 상태 — running 과 반드시 구분한다.
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

VARIANTS = ("solid", "surface", "text", "border")


def _assert_palette_covers_tones() -> None:
    missing = [tone for tone in STATUS_TONES if tone not in PALETTE]
    if missing:
        msg = f"PALETTE 에 톤이 없습니다: {missing} — status_labels.STATUS_TONES 와 맞추세요."
        raise SystemExit(msg)


def render_css() -> str:
    _assert_palette_covers_tones()
    lines = [BANNER_CSS, ":root {"]
    for tone in STATUS_TONES:
        for variant in VARIANTS:
            lines.append(f"  --st-{tone}-{variant}: {PALETTE[tone][variant]};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _ts_label_map(name: str, labels: dict) -> str:
    # enum 값은 대문자("PASSED")지만 프론트 규약은 소문자다(app.js 가 lower() 로 정규화).
    # 생성 시점에 소문자로 맞춰 런타임 변환을 없앤다.
    body = "\n".join(f'  "{key.value.lower()}": "{value}",' for key, value in labels.items())
    return f"export const {name}: Record<string, string> = {{\n{body}\n}};\n"


def render_ts() -> str:
    _assert_palette_covers_tones()
    union = " | ".join(f'"{tone}"' for tone in STATUS_TONES)
    tone_list = ", ".join(f'"{tone}"' for tone in STATUS_TONES)
    parts = [
        BANNER_TS,
        f"export type StatusTone = {union};\n",
        f"export const STATUS_TONES: readonly StatusTone[] = [{tone_list}] as const;\n",
        _ts_label_map("RUN_STATUS_LABELS", RUN_STATUS_LABELS),
        _ts_label_map("MODULE_STATUS_LABELS", MODULE_STATUS_LABELS),
        _ts_label_map("SUITE_STATUS_LABELS", SUITE_STATUS_LABELS),
    ]
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    targets = ((CSS_OUT, render_css()), (TS_OUT, render_ts()))
    stale: list[str] = []
    for path, content in targets:
        if check_only:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != content:
                stale.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if stale:
        print("생성물이 status_labels.py 와 어긋났습니다:")
        for name in stale:
            print(f"  - {name}")
        print("해결: python3 scripts/gen_frontend_tokens.py")
        return 1
    if not check_only:
        print(f"생성 완료: {CSS_OUT.name}, {TS_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 8: 통과를 확인한다**

Run: `python3 -m pytest tests/frontend/ -v`
Expected: PASS (10 passed — 톤 축 4건 + 생성기 6건)

- [ ] **Step 9: 생성물을 만든다**

Run: `python3 scripts/gen_frontend_tokens.py`
Expected: `생성 완료: tokens.generated.css, status.generated.ts`

Run: `python3 scripts/gen_frontend_tokens.py --check`
Expected: exit 0, 출력 없음

- [ ] **Step 10: 커밋**

```bash
git add app/core/status_labels.py scripts/gen_frontend_tokens.py \
        tests/frontend/ app/web/frontend/
git commit -m "feat(frontend): 상태 토큰 생성기 + STATUS_TONES SSOT 추가"
```

---

## Task 2: Vite 다중 엔트리 빌드 + CSS 번들

**Files:**
- Create: `package.json`, `vite.config.ts`, `tsconfig.json`, `postcss.config.js`, `.gitignore` (수정)
- Create: `app/web/frontend/entries/main.ts`
- Move: `app/web/static/app.css` → `app/web/frontend/styles/app.css`
- Move: `app/web/static/dashboard.css` → `app/web/frontend/styles/dashboard.css`

**Interfaces:**
- Consumes: Task 1 의 `app/web/frontend/styles/tokens.generated.css`
- Produces:
  - 빌드 산출물 `app/web/static/dist/` + `app/web/static/dist/.vite/manifest.json`
  - manifest 엔트리 키 `app/web/frontend/entries/main.ts`
  - npm 스크립트 `build` · `dev` · `typecheck` · `lint` · `test`

- [ ] **Step 1: npm 프로젝트를 만든다**

`package.json`:

```json
{
  "name": "e2e-tester-web",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "vite build",
    "dev": "vite build --watch",
    "typecheck": "tsc --noEmit",
    "lint": "eslint app/web/frontend --ext .ts",
    "test": "vitest run"
  },
  "dependencies": {
    "@tailwindcss/postcss": "^4.0.0",
    "alpinejs": "^3.14.8",
    "htmx.org": "^2.0.4",
    "pretendard": "^1.3.9",
    "tailwindcss": "^4.0.0"
  },
  "devDependencies": {
    "@typescript-eslint/eslint-plugin": "^8.0.0",
    "@typescript-eslint/parser": "^8.0.0",
    "eslint": "^9.0.0",
    "postcss": "^8.4.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "vitest": "^3.0.0"
  }
}
```

- [ ] **Step 2: Vite·TS·PostCSS 설정을 만든다**

`vite.config.ts`:

```ts
import { defineConfig } from "vite";
import { resolve } from "node:path";

// Jinja 서버 렌더를 유지하는 다중 엔트리 빌드. SPA 아님.
// manifest 를 켜서 Jinja 가 해시 파일명을 해석한다(수동 ?v= 캐시버스팅 제거).
export default defineConfig({
  root: resolve(__dirname, "app/web/frontend"),
  build: {
    outDir: resolve(__dirname, "app/web/static/dist"),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, "app/web/frontend/entries/main.ts"),
      },
    },
  },
});
```

`tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "allowJs": true,
    "checkJs": false,
    "noEmit": true,
    "skipLibCheck": true,
    "types": ["vite/client"]
  },
  "include": ["app/web/frontend/**/*.ts"]
}
```

`postcss.config.js`:

```js
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
```

- [ ] **Step 3: CSS 를 이동하고 공용 엔트리를 만든다**

```bash
git mv app/web/static/app.css app/web/frontend/styles/app.css
git mv app/web/static/dashboard.css app/web/frontend/styles/dashboard.css
```

`app/web/frontend/styles/base.css`:

```css
@import "tailwindcss";
@import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
@import "./tokens.generated.css";
@import "./app.css";
@import "./dashboard.css";
```

`app/web/frontend/entries/main.ts`:

```ts
// 전 페이지 공용 엔트리. CSS 번들 + htmx/Alpine self-host.
// 외부 CDN 을 대체한다(FG-001).
import "../styles/base.css";

import Alpine from "alpinejs";
import "htmx.org";

declare global {
  interface Window {
    Alpine: typeof Alpine;
  }
}

window.Alpine = Alpine;
Alpine.start();
```

- [ ] **Step 4: dist 를 gitignore 에 추가한다**

`.gitignore` 끝에 추가:

```
# Vite 빌드 산출물
app/web/static/dist/
node_modules/
```

- [ ] **Step 5: 빌드가 도는지 확인한다**

Run: `npm install && npm run build`
Expected: `app/web/static/dist/.vite/manifest.json` 생성. 종료 코드 0.

Run: `npm run typecheck`
Expected: 에러 0건

- [ ] **Step 6: 커밋**

```bash
git add package.json package-lock.json vite.config.ts tsconfig.json \
        postcss.config.js .gitignore app/web/frontend/ app/web/static/
git commit -m "build(frontend): Vite 다중 엔트리 빌드 + CSS 번들 도입"
```

---

## Task 3: Jinja manifest 매크로

**Files:**
- Create: `app/web/asset_manifest.py`
- Create: `app/web/templates/_assets.html`
- Test: `tests/frontend/test_asset_manifest.py`

**Interfaces:**
- Consumes: Task 2 의 `app/web/static/dist/.vite/manifest.json`
- Produces: `app.web.asset_manifest.AssetManifest` — `.js_url(entry: str) -> str`, `.css_urls(entry: str) -> list[str]`. Jinja 전역으로 `asset_js` · `asset_css` 이름으로 주입된다.

- [ ] **Step 1: 테스트를 작성한다**

`tests/frontend/test_asset_manifest.py`:

```python
import json

import pytest

from app.web.asset_manifest import AssetManifest, ManifestMissingError

SAMPLE = {
    "entries/main.ts": {
        "file": "assets/main-a1b2c3d4.js",
        "src": "entries/main.ts",
        "isEntry": True,
        "css": ["assets/main-e5f6a7b8.css"],
    }
}


@pytest.fixture()
def manifest_path(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return path


def test_js_url_resolves_hashed_filename(manifest_path):
    manifest = AssetManifest(manifest_path, base_url="/static/dist")
    assert manifest.js_url("entries/main.ts") == "/static/dist/assets/main-a1b2c3d4.js"


def test_css_urls_resolves_hashed_filenames(manifest_path):
    manifest = AssetManifest(manifest_path, base_url="/static/dist")
    assert manifest.css_urls("entries/main.ts") == ["/static/dist/assets/main-e5f6a7b8.css"]


def test_unknown_entry_raises_with_actionable_message(manifest_path):
    manifest = AssetManifest(manifest_path, base_url="/static/dist")
    with pytest.raises(ManifestMissingError) as excinfo:
        manifest.js_url("entries/nope.ts")
    assert "npm run build" in str(excinfo.value)


def test_missing_manifest_file_raises_with_actionable_message(tmp_path):
    manifest = AssetManifest(tmp_path / "absent.json", base_url="/static/dist")
    with pytest.raises(ManifestMissingError) as excinfo:
        manifest.js_url("entries/main.ts")
    assert "npm run build" in str(excinfo.value)


def test_manifest_is_reloaded_when_file_changes(manifest_path):
    """개발 중 재빌드가 서버 재시작 없이 반영되어야 한다."""
    manifest = AssetManifest(manifest_path, base_url="/static/dist")
    assert manifest.js_url("entries/main.ts").endswith("main-a1b2c3d4.js")
    changed = {"entries/main.ts": {"file": "assets/main-99999999.js", "isEntry": True}}
    manifest_path.write_text(json.dumps(changed), encoding="utf-8")
    assert manifest.js_url("entries/main.ts").endswith("main-99999999.js")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_asset_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.web.asset_manifest'`

- [ ] **Step 3: 구현한다**

`app/web/asset_manifest.py`:

```python
"""Vite manifest 로더 — 템플릿이 해시 파일명을 해석한다.

수동 `?v=` 캐시버스팅을 대체한다. 파일 mtime 이 바뀌면 다시 읽으므로
개발 중 재빌드가 서버 재시작 없이 반영된다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ManifestMissingError(RuntimeError):
    """manifest 또는 엔트리를 찾지 못했을 때. 메시지에 해결책을 담는다."""


class AssetManifest:
    def __init__(self, path: Path, *, base_url: str) -> None:
        self._path = Path(path)
        self._base_url = base_url.rstrip("/")
        self._cache: dict[str, Any] = {}
        self._mtime: float | None = None

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            msg = (
                f"Vite manifest 가 없습니다: {self._path}. "
                "`npm run build` 를 먼저 실행하세요."
            )
            raise ManifestMissingError(msg)
        mtime = self._path.stat().st_mtime
        if self._mtime != mtime:
            self._cache = json.loads(self._path.read_text(encoding="utf-8"))
            self._mtime = mtime
        return self._cache

    def _entry(self, entry: str) -> dict[str, Any]:
        manifest = self._load()
        record = manifest.get(entry)
        if record is None:
            known = ", ".join(sorted(manifest)) or "(비어 있음)"
            msg = (
                f"manifest 에 엔트리가 없습니다: {entry}. 등록된 엔트리: {known}. "
                "vite.config.ts 의 rollupOptions.input 을 확인하고 `npm run build` 를 실행하세요."
            )
            raise ManifestMissingError(msg)
        return record

    def js_url(self, entry: str) -> str:
        return f"{self._base_url}/{self._entry(entry)['file']}"

    def css_urls(self, entry: str) -> list[str]:
        return [f"{self._base_url}/{name}" for name in self._entry(entry).get("css", [])]
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/frontend/test_asset_manifest.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Jinja 매크로와 전역 주입을 추가한다**

`app/web/templates/_assets.html`:

```jinja
{# Vite manifest 경유 자산 태그. static/ 직접 참조 금지(FG-005). #}
{% macro asset_styles(entry="entries/main.ts") -%}
{% for href in asset_css(entry) %}<link rel="stylesheet" href="{{ href }}">
{% endfor %}
{%- endmacro %}

{% macro asset_script(entry="entries/main.ts") -%}
<script type="module" src="{{ asset_js(entry) }}"></script>
{%- endmacro %}
```

Jinja 환경이 만들어지는 지점(템플릿 `Jinja2Templates` 생성부)에서 전역을 주입한다:

```python
from pathlib import Path

from app.web.asset_manifest import AssetManifest

_manifest = AssetManifest(
    Path(__file__).resolve().parents[1] / "web/static/dist/.vite/manifest.json",
    base_url="/static/dist",
)
templates.env.globals["asset_js"] = _manifest.js_url
templates.env.globals["asset_css"] = _manifest.css_urls
```

주입 위치는 `grep -rn "Jinja2Templates(" app/` 로 찾는다. 경로 계산은 그 파일 위치 기준으로 맞춘다.

- [ ] **Step 6: 커밋**

```bash
git add app/web/asset_manifest.py app/web/templates/_assets.html \
        tests/frontend/test_asset_manifest.py
git commit -m "feat(frontend): Vite manifest 로더 + Jinja 자산 매크로 추가"
```

---

## Task 4: CDN 4종 제거

**Files:**
- Modify: `app/web/templates/base.html:11-13`
- Modify: `app/web/templates/dashboard.html:6, 53-54`

**Interfaces:**
- Consumes: Task 3 의 `asset_styles` · `asset_script` 매크로
- Produces: 외부 CDN 참조가 0 인 템플릿 트리

- [ ] **Step 1: `base.html` 의 CDN 3줄을 교체한다**

현재 (11~13행):

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
<link rel="stylesheet" href="/static/app.css?v=16">
```

교체:

```html
{% import "_assets.html" as assets %}
{{ assets.asset_styles() }}
{{ assets.asset_script() }}
```

`{% import %}` 는 `<head>` 시작 전 최상단으로 올려도 되고 그 자리에 둬도 된다. `asset_script()` 는 `type="module"` 이라 자동 defer 되므로 `<head>` 에 두어도 렌더를 막지 않는다.

- [ ] **Step 2: `dashboard.html` 의 htmx·Alpine CDN 2줄과 CSS 링크를 제거한다**

6행의 `<link rel="stylesheet" href="/static/dashboard.css?v=8">` 를 삭제한다 — `base.css` 번들에 이미 포함됐다.

53~54행을 삭제한다:

```html
<script src="https://unpkg.com/htmx.org@2.0.4" defer></script>
<script src="https://unpkg.com/alpinejs@3.14.8/dist/cdn.min.js" defer></script>
```

`{% block scripts %}` 에는 `<script src="/static/dashboard.js?v=22" defer></script>` 만 남는다. (기존 페이지별 JS 는 P3 이관 전까지 `static/` 에서 그대로 로드한다.)

- [ ] **Step 3: 외부 참조가 사라졌는지 확인한다**

Run: `grep -rn "cdn.jsdelivr\|unpkg.com\|cdnjs" app/web/templates/`
Expected: 출력 없음 (exit 1)

- [ ] **Step 4: 화면이 동일한지 육안 검증한다**

Run: `npm run build`, 그다음 앱을 띄운다 (`docs/INSTALL.md` 절차).

확인 항목:
- `/` (일간 현황) — 히어로·매트릭스가 이전과 동일하게 보이는가
- `/runs/execute` · `/runs/history` · `/self-healing` · `/admin` — 레이아웃 깨짐 없는가
- 브라우저 콘솔 에러 0건
- 네트워크 탭에 외부 도메인 요청 0건
- **FOUC 가 사라졌는지** — 새로고침 시 스타일 없는 프레임이 보이지 않아야 한다

Alpine 이 동작하는지는 일간 현황의 드로어(`x-data="{ drawerOpen: false }"`)를 열어 확인한다. htmx 는 `/api/dashboard/daily/fragments/kpi` 요청이 네트워크 탭에 뜨는지로 확인한다.

- [ ] **Step 5: 커밋**

```bash
git add app/web/templates/base.html app/web/templates/dashboard.html
git commit -m "build(frontend): 외부 CDN 4종 제거 — Tailwind·Pretendard·htmx·Alpine self-host"
```

---

## Task 5: 프론트 게이트 FG-001~005

**Files:**
- Create: `scripts/check_frontend_gates.py`
- Test: `tests/frontend/test_frontend_gates.py`

**Interfaces:**
- Produces: `scripts/check_frontend_gates.py` 의 `check_fg001_no_cdn(root: Path) -> list[str]` · `check_fg002_no_hex(root)` · `check_fg003_status_source(root)` · `check_fg004_file_size(root)` · `check_fg005_no_static_ref(root)` · `main() -> int`. 각 check 는 위반 메시지 리스트를 반환하며 빈 리스트가 통과다.

- [ ] **Step 1: 테스트를 작성한다**

`tests/frontend/test_frontend_gates.py`:

```python
from pathlib import Path

from scripts.check_frontend_gates import (
    check_fg001_no_cdn,
    check_fg002_no_hex,
    check_fg003_status_source,
    check_fg004_file_size,
    check_fg005_no_static_ref,
)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_fg001_flags_external_script(tmp_path):
    _write(tmp_path, "app/web/templates/x.html", '<script src="https://unpkg.com/htmx.org@2"></script>')
    problems = check_fg001_no_cdn(tmp_path)
    assert len(problems) == 1
    assert "unpkg.com" in problems[0]


def test_fg001_allows_local_script(tmp_path):
    _write(tmp_path, "app/web/templates/x.html", '<script src="/static/dashboard.js"></script>')
    assert check_fg001_no_cdn(tmp_path) == []


def test_fg002_flags_hex_in_frontend(tmp_path):
    _write(tmp_path, "app/web/frontend/components/a/styles.css", ".x { color: #ff0000; }")
    problems = check_fg002_no_hex(tmp_path)
    assert len(problems) == 1
    assert "#ff0000" in problems[0]


def test_fg002_ignores_generated_tokens(tmp_path):
    """생성물은 팔레트 원본이므로 hex 를 담는 유일한 예외다."""
    _write(tmp_path, "app/web/frontend/styles/tokens.generated.css", ":root { --st-passed-solid: #10b981; }")
    assert check_fg002_no_hex(tmp_path) == []


def test_fg003_flags_hardcoded_korean_status_label(tmp_path):
    _write(tmp_path, "app/web/frontend/lib/x.ts", 'const label = "점검실패";')
    problems = check_fg003_status_source(tmp_path)
    assert len(problems) == 1
    assert "점검실패" in problems[0]


def test_fg003_allows_generated_module(tmp_path):
    _write(tmp_path, "app/web/frontend/lib/status.generated.ts", 'export const X = { "error": "점검실패" };')
    assert check_fg003_status_source(tmp_path) == []


def test_fg004_flags_oversized_file(tmp_path):
    _write(tmp_path, "app/web/frontend/entries/big.ts", "\n".join(f"const x{i} = {i};" for i in range(401)))
    problems = check_fg004_file_size(tmp_path)
    assert len(problems) == 1
    assert "401" in problems[0]


def test_fg004_allows_file_at_limit(tmp_path):
    _write(tmp_path, "app/web/frontend/entries/ok.ts", "\n".join(f"const x{i} = {i};" for i in range(400)))
    assert check_fg004_file_size(tmp_path) == []


def test_fg005_flags_direct_static_reference(tmp_path):
    _write(tmp_path, "app/web/templates/x.html", '<link rel="stylesheet" href="/static/app.css?v=16">')
    problems = check_fg005_no_static_ref(tmp_path)
    assert len(problems) == 1
    assert "app.css" in problems[0]


def test_fg005_allows_legacy_page_scripts(tmp_path):
    """P3 이관 전까지 페이지별 레거시 JS 는 허용한다(ALLOWLIST)."""
    _write(tmp_path, "app/web/templates/x.html", '<script src="/static/dashboard.js?v=22" defer></script>')
    assert check_fg005_no_static_ref(tmp_path) == []
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_frontend_gates.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.check_frontend_gates'`

- [ ] **Step 3: 구현한다**

`scripts/check_frontend_gates.py`:

```python
"""프론트엔드 게이트 FG-001~005 — check_architecture_gates.py 의 프론트 대응물.

디자인 시스템은 강제력이 없으면 6개월 안에 하드코딩으로 되돌아간다.
각 규칙은 실제로 발생했던 사고를 막는다(설계 문서 §3.6 참조).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TEMPLATE_DIR = "app/web/templates"
FRONTEND_DIR = "app/web/frontend"

MAX_FILE_LINES = 400

# hex 를 담을 수 있는 유일한 예외 — 팔레트 원본
GENERATED_FILES = {
    "app/web/frontend/styles/tokens.generated.css",
    "app/web/frontend/lib/status.generated.ts",
}

# P3 이관 완료 전까지 템플릿이 직접 로드하는 레거시 페이지 스크립트.
# 화면을 이관할 때마다 여기서 한 줄씩 지운다. 비면 FG-005 가 완성된다.
FG005_ALLOWLIST = {
    "/static/admin-dashboard.js",
    "/static/admin-ops.js",
    "/static/admin-runs.js",
    "/static/admin-stats.js",
    "/static/anomalies.js",
    "/static/app.js",
    "/static/dashboard.js",
    "/static/healing.js",
    "/static/insights.js",
    "/static/mobile-nav.js",
    "/static/nav-badges.js",
    "/static/presets.js",
    "/static/schedules.js",
    "/static/favicon.svg",
}

_EXTERNAL_URL = re.compile(r"""(?:src|href)\s*=\s*["'](https?://[^"']+)["']""")
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_STATIC_REF = re.compile(r"""(?:src|href)\s*=\s*["'](/static/[^"'?]+)""")


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _iter(root: Path, subdir: str, *suffixes: str):
    base = root / subdir
    if not base.exists():
        return
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.suffix in suffixes:
            yield path


def check_fg001_no_cdn(root: Path = REPO_ROOT) -> list[str]:
    """FG-001: 템플릿에 외부 CDN script/link 금지."""
    problems: list[str] = []
    for path in _iter(root, TEMPLATE_DIR, ".html"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for url in _EXTERNAL_URL.findall(line):
                problems.append(
                    f"[FG-001] {_rel(path, root)}:{lineno} 외부 자산 참조 `{url}` — "
                    "npm 으로 self-host 하고 asset 매크로를 쓰세요."
                )
    return problems


def check_fg002_no_hex(root: Path = REPO_ROOT) -> list[str]:
    """FG-002: frontend/ 내 하드코딩 hex 금지(생성물 제외)."""
    problems: list[str] = []
    for path in _iter(root, FRONTEND_DIR, ".css", ".ts"):
        rel = _rel(path, root)
        if rel in GENERATED_FILES:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for hex_value in _HEX.findall(line):
                problems.append(
                    f"[FG-002] {rel}:{lineno} 하드코딩 색 `{hex_value}` — "
                    "var(--st-*) 또는 var(--c-*) 토큰을 쓰세요."
                )
    return problems


def check_fg003_status_source(root: Path = REPO_ROOT) -> list[str]:
    """FG-003: 상태 라벨은 status.generated.ts 경유만."""
    labels = ("정상", "이상징후", "점검실패", "입력 대기", "실행 중", "차단", "제외", "취소")
    problems: list[str] = []
    for path in _iter(root, FRONTEND_DIR, ".ts"):
        rel = _rel(path, root)
        if rel in GENERATED_FILES:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for label in labels:
                if f'"{label}"' in line or f"'{label}'" in line:
                    problems.append(
                        f"[FG-003] {rel}:{lineno} 상태 라벨 `{label}` 하드코딩 — "
                        "lib/status.generated.ts 의 라벨 맵을 임포트하세요."
                    )
    return problems


def check_fg004_file_size(root: Path = REPO_ROOT) -> list[str]:
    """FG-004: 엔트리·컴포넌트 400줄 상한."""
    problems: list[str] = []
    for path in _iter(root, FRONTEND_DIR, ".ts", ".css"):
        rel = _rel(path, root)
        if rel in GENERATED_FILES:
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > MAX_FILE_LINES:
            problems.append(
                f"[FG-004] {rel} 가 {lines}줄 (상한 {MAX_FILE_LINES}) — "
                "책임 단위로 분리하세요."
            )
    return problems


def check_fg005_no_static_ref(root: Path = REPO_ROOT) -> list[str]:
    """FG-005: static/ 직접 참조 금지(allowlist 제외). manifest 경유만."""
    problems: list[str] = []
    for path in _iter(root, TEMPLATE_DIR, ".html"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for ref in _STATIC_REF.findall(line):
                if ref in FG005_ALLOWLIST:
                    continue
                problems.append(
                    f"[FG-005] {_rel(path, root)}:{lineno} static 직접 참조 `{ref}` — "
                    "_assets.html 의 asset 매크로를 쓰거나 FG005_ALLOWLIST 에 등록하세요."
                )
    return problems


CHECKS = (
    check_fg001_no_cdn,
    check_fg002_no_hex,
    check_fg003_status_source,
    check_fg004_file_size,
    check_fg005_no_static_ref,
)


def main() -> int:
    problems: list[str] = []
    for check in CHECKS:
        problems.extend(check(REPO_ROOT))
    if problems:
        print(f"프론트엔드 게이트 위반 {len(problems)}건:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("프론트엔드 게이트 통과 (FG-001~005)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/frontend/test_frontend_gates.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: 실제 저장소에 대해 돌린다**

Run: `python3 scripts/check_frontend_gates.py`

Expected: FG-002 위반이 대량 보고된다 — `app/web/frontend/styles/app.css` 와 `dashboard.css` 에 hex 244개가 아직 남아 있기 때문이다. **이는 정상이며 Task 6 에서 해소한다.** FG-001·FG-003·FG-005 는 0건이어야 한다 (Task 4 완료분).

FG-001 또는 FG-005 가 걸리면 Task 4 로 돌아간다.

- [ ] **Step 6: 커밋**

```bash
git add scripts/check_frontend_gates.py tests/frontend/test_frontend_gates.py
git commit -m "feat(ci): 프론트엔드 게이트 FG-001~005 추가"
```

---

## Task 6: hex → 토큰 치환 (FG-002 해소)

**Files:**
- Modify: `app/web/frontend/styles/app.css`
- Modify: `app/web/frontend/styles/dashboard.css`
- Create: `app/web/frontend/styles/primitives.css`

**Interfaces:**
- Consumes: Task 1 의 `--st-{tone}-{variant}` 토큰
- Produces: `--c-*` primitive 토큰 (`primitives.css`). FG-002 위반 0건 상태.

- [ ] **Step 1: primitive 팔레트를 만든다**

상태색이 아닌 중립색(회색·흰색·그림자)은 primitive 층에 둔다. `app/web/frontend/styles/primitives.css`:

```css
/* 중립 팔레트(라이트 전용). 상태색은 tokens.generated.css 가 담당한다. */
:root {
  --c-white: #ffffff;
  --c-gray-50: #f9fafb;
  --c-gray-100: #f3f4f6;
  --c-gray-200: #e5e7eb;
  --c-gray-300: #d1d5db;
  --c-gray-400: #9ca3af;
  --c-gray-500: #6b7280;
  --c-gray-700: #374151;
  --c-gray-900: #111827;
  --c-indigo-50: #e0e7ff;
  --c-indigo-500: #6366f1;
  --c-indigo-600: #4f46e5;
  --c-violet-100: #ede9fe;
  --c-violet-600: #7c3aed;
  --c-violet-700: #6d28d9;

  --pl-bg: var(--c-gray-50);
  --pl-surface: var(--c-white);
  --pl-border: var(--c-gray-200);
  --pl-text: var(--c-gray-900);
  --pl-text-muted: var(--c-gray-500);
  --pl-text-subtle: var(--c-gray-400);
  --pl-accent: var(--c-indigo-500);
  --pl-shadow-sm: 0 1px 3px rgb(0 0 0 / 0.06), 0 1px 2px rgb(0 0 0 / 0.04);
  --pl-shadow-md: 0 8px 30px -8px rgb(0 0 0 / 0.12);
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
}
```

`base.css` 의 `@import "./tokens.generated.css";` **바로 위**에 `@import "./primitives.css";` 를 추가한다.

- [ ] **Step 2: `dashboard.css` 의 기존 `:root` 블록을 제거한다**

`dashboard.css` 11~21행의 `--pl-*` · `--st-*` · `--ease-out` 선언은 이제 `primitives.css` 와 `tokens.generated.css` 가 담당한다. 해당 `:root { ... }` 블록을 통째로 삭제한다.

**주의:** 기존 `--st-passed` 등은 이름이 `--st-passed-solid` 로 바뀌었다. 다음 단계에서 참조를 일괄 갱신한다.

- [ ] **Step 3: 구 토큰 이름 참조를 갱신한다**

```bash
cd app/web/frontend/styles
sed -i 's/var(--st-passed)/var(--st-passed-solid)/g;
        s/var(--st-anomaly)/var(--st-anomaly-solid)/g;
        s/var(--st-error)/var(--st-error-solid)/g;
        s/var(--st-running)/var(--st-running-solid)/g;
        s/var(--st-blocked)/var(--st-blocked-solid)/g;
        s/var(--st-idle)/var(--st-pending-solid)/g' dashboard.css
```

Run: `grep -n "var(--st-[a-z_]*)" app/web/frontend/styles/dashboard.css | grep -v -- "-solid\|-surface\|-text\|-border"`
Expected: 출력 없음

- [ ] **Step 4: `waiting_input` 과 `skipped`/`cancelled` 톤을 분리한다**

`dashboard.css` 에서 `waiting_input` 이 `running` 과 묶여 있던 선택자를 분리한다. 예 (362~369행 부근, `.dash-attention__item`):

```css
.dash-attention__item[data-tone="running"] .dash-attention__dot { background: var(--st-running-solid); }
.dash-attention__item[data-tone="waiting_input"] .dash-attention__dot { background: var(--st-waiting_input-solid); }
.dash-attention__item[data-tone="skipped"] .dash-attention__dot { background: var(--st-skipped-solid); }
.dash-attention__item[data-tone="cancelled"] .dash-attention__dot { background: var(--st-cancelled-solid); }
```

`.dash-seg[data-tone=...]`(541행 부근), `.dash-sys-row__icon`(611행 부근), `.dash-mod--filled`(666행 부근)도 같은 방식으로 9개 톤을 모두 덮도록 채운다.

**이는 P1 에서 유일하게 화면이 미세하게 바뀌는 지점이다** — 지금까지 회색으로 뭉개지던 `skipped`/`cancelled` 가 구분되고, `waiting_input` 이 보라로 분리된다. 설계 문서 §3.3 의 의도된 변경이다.

- [ ] **Step 5: 남은 hex 를 토큰으로 치환한다**

Run: `python3 scripts/check_frontend_gates.py`

보고되는 각 위반을 순회하며 치환한다. 대응표:

| hex | 토큰 |
| --- | --- |
| `#fff` · `#ffffff` | `var(--c-white)` |
| `#f9fafb` | `var(--c-gray-50)` |
| `#f3f4f6` | `var(--c-gray-100)` |
| `#e5e7eb` | `var(--c-gray-200)` |
| `#d1d5db` | `var(--c-gray-300)` |
| `#9ca3af` | `var(--c-gray-400)` |
| `#6b7280` | `var(--c-gray-500)` |
| `#111827` | `var(--c-gray-900)` |
| `#4f46e5` | `var(--c-indigo-600)` |
| `#6366f1` | `var(--c-indigo-500)` |
| `#e0e7ff` | `var(--c-indigo-50)` |
| `#7c3aed` | `var(--c-violet-600)` |
| `#6d28d9` | `var(--c-violet-700)` |
| `#ede9fe` | `var(--c-violet-100)` |
| `#10b981` | `var(--st-passed-solid)` |
| `#d1fae5` | `var(--st-passed-surface)` |
| `#f59e0b` | `var(--st-anomaly-solid)` |
| `#fef3c7` | `var(--st-anomaly-surface)` |
| `#b45309` | `var(--st-anomaly-text)` |
| `#ef4444` | `var(--st-error-solid)` |
| `#3b82f6` | `var(--st-running-solid)` |
| `#f97316` | `var(--st-blocked-solid)` |

표에 없는 hex 가 남으면 `primitives.css` 에 primitive 를 추가하고 표에 맞춰 치환한다. **새 hex 를 컴포넌트 CSS 에 직접 남기지 않는다.**

- [ ] **Step 6: 게이트 통과를 확인한다**

Run: `python3 scripts/check_frontend_gates.py`
Expected: `프론트엔드 게이트 통과 (FG-001~005)`

- [ ] **Step 7: 화면이 동일한지 육안 검증한다**

Run: `npm run build`, 앱 실행.

확인 항목:
- 일간 현황·실행·이력·자가 치유·관리자 화면이 **Task 4 시점과 동일하게** 보이는가
- 예외: `skipped`/`cancelled`/`waiting_input` 상태의 점·막대 색이 구분되어 보이는가 (Step 4 의 의도된 변경)
- 브라우저 콘솔 에러 0건

- [ ] **Step 8: 커밋**

```bash
git add app/web/frontend/styles/
git commit -m "refactor(frontend): 하드코딩 hex 244개를 토큰으로 치환 — FG-002 해소"
```

---

## Task 7: 게이트 CI 배선

**Files:**
- Modify: `scripts/ci/gates.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/CI.md`
- Test: `tests/frontend/test_frontend_gate_wiring.py`

**Interfaces:**
- Consumes: Task 1 의 `gen_frontend_tokens.py --check`, Task 5 의 `check_frontend_gates.py`
- Produces: 게이트 이름 `frontend_gates` · `frontend_tokens` · `typecheck_web` · `eslint_web` (전부 Tier 0, `STANDARD_GATES` 포함)

- [ ] **Step 1: 배선 테스트를 작성한다**

`tests/frontend/test_frontend_gate_wiring.py`:

```python
from scripts.ci.gates import (
    GATE_COMMANDS,
    GATE_TIERS,
    PROFILE_GATES,
    STANDARD_GATES,
)

FRONTEND_GATES = ("frontend_gates", "frontend_tokens", "typecheck_web", "eslint_web")


def test_frontend_gates_are_registered():
    for name in FRONTEND_GATES:
        assert name in GATE_COMMANDS, name


def test_frontend_gates_are_tier_zero():
    """빠르고 결정적인 검사이므로 fail-fast 계층에 둔다."""
    for name in FRONTEND_GATES:
        assert GATE_TIERS[name] == 0, name


def test_frontend_gates_are_in_standard_profile():
    for name in FRONTEND_GATES:
        assert name in STANDARD_GATES, name


def test_docs_only_profile_excludes_frontend_gates():
    """문서만 바뀐 PR 에서 npm 빌드를 요구하지 않는다."""
    for name in FRONTEND_GATES:
        assert name not in PROFILE_GATES["docs_only"], name
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest tests/frontend/test_frontend_gate_wiring.py -v`
Expected: FAIL — `KeyError` 또는 `assert 'frontend_gates' in GATE_COMMANDS`

- [ ] **Step 3: `gates.py` 에 게이트를 등록한다**

`GATE_COMMANDS` dict 의 `"ruff"` 항목 **바로 앞**에 추가:

```python
    "frontend_gates": _py("scripts/check_frontend_gates.py"),
    "frontend_tokens": _py("scripts/gen_frontend_tokens.py", "--check"),
    "typecheck_web": ["npm", "run", "typecheck"],
    "eslint_web": ["npm", "run", "lint"],
```

`GATE_TIERS` dict 의 `"ruff": 0,` 아래에 추가:

```python
    "frontend_gates": 0,
    "frontend_tokens": 0,
    "typecheck_web": 0,
    "eslint_web": 0,
```

`STANDARD_GATES` 리스트의 `"ruff_format",` 아래에 추가:

```python
    "frontend_gates",
    "frontend_tokens",
    "typecheck_web",
    "eslint_web",
```

`docs_only` 프로필은 손대지 않는다 — 문서만 바뀐 PR 에서 npm 설치를 요구하지 않기 위해서다.

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest tests/frontend/test_frontend_gate_wiring.py -v`
Expected: PASS (4 passed)

Run: `python3 scripts/ci/check_ci_config.py`
Expected: 통과 — 새 게이트의 스크립트 경로가 실재하는지 검사한다. 실패하면 경로 오타다.

- [ ] **Step 5: ESLint 설정을 추가한다**

`eslint.config.js`:

```js
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";

export default [
  {
    files: ["app/web/frontend/**/*.ts"],
    ignores: ["app/web/frontend/**/*.generated.ts"],
    languageOptions: { parser: tsparser, ecmaVersion: 2022, sourceType: "module" },
    plugins: { "@typescript-eslint": tseslint },
    rules: {
      "@typescript-eslint/no-unused-vars": "error",
      "@typescript-eslint/no-explicit-any": "error",
      eqeqeq: "error",
      "no-console": ["error", { allow: ["warn", "error"] }],
    },
  },
];
```

Run: `npm run lint`
Expected: 에러 0건

- [ ] **Step 6: CI 워크플로에 Node 셋업을 조건부로 추가한다**

`.github/workflows/ci.yml` 의 `gate` job 은 `plan.py` 가 고른 게이트 목록을 **matrix 로 펼쳐 게이트당 job 하나**를 돌리고, 각 job 에는 Python 만 설치한다. 따라서 Node 가 필요한 게이트에만 조건부로 설치해야 한다 — 무조건 설치하면 Python 전용 게이트 job 마다 불필요하게 npm 이 돈다.

`gate` job 의 `Install dev dependencies` 스텝 **바로 뒤**, `Run gate` 스텝 **앞**에 삽입한다:

```yaml
      # typecheck_web·eslint_web 만 Node 를 필요로 한다.
      # 게이트당 job 이 하나이므로 해당 job 에서만 설치한다.
      - name: Set up Node (프론트 게이트 전용)
        if: matrix.gate == 'typecheck_web' || matrix.gate == 'eslint_web'
        uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm

      - name: Install web dependencies
        if: matrix.gate == 'typecheck_web' || matrix.gate == 'eslint_web'
        run: npm ci
```

`frontend_gates` 와 `frontend_tokens` 는 순수 파이썬이라 Node 가 필요 없다 — 조건에 넣지 않는다. `npm run build` 도 CI 에서는 불필요하다. 두 게이트 모두 소스만 읽고 `dist/` 를 읽지 않기 때문이다.

`docs_only` 프로필은 Task 7 Step 3 에서 이미 제외했으므로 문서 PR 에서는 이 job 자체가 생성되지 않는다.

- [ ] **Step 7: `docs/CI.md` 를 갱신한다**

"게이트 계층" 표의 Tier 0 행을 교체한다:

```markdown
| 0 | `ci_config_valid`, `ruff`, `ruff_format`, `docs_consistency`, `frontend_gates`, `frontend_tokens`, `typecheck_web`, `eslint_web` |
```

"아키텍처 게이트 요약" 표 아래에 절을 추가한다:

```markdown
## 프론트엔드 게이트 요약

SSOT: `scripts/check_frontend_gates.py`. 상태 토큰 생성기: `scripts/gen_frontend_tokens.py`.

| 규칙 | 내용 |
| --- | --- |
| FG-001 | 템플릿에 외부 CDN `<script>`/`<link>` 금지 |
| FG-002 | `app/web/frontend/` 내 하드코딩 hex 금지 (생성물 제외) |
| FG-003 | 상태 라벨은 `lib/status.generated.ts` 경유만 |
| FG-004 | 엔트리·컴포넌트 파일 400줄 상한 |
| FG-005 | 템플릿의 `/static/` 직접 참조 금지 (allowlist 제외) |

`frontend_tokens` 는 `status_labels.py` 에서 토큰·타입을 재생성해 커밋본과
diff 를 검사한다 — 상태를 추가하고 프론트 갱신을 잊는 것을 막는다.
```

- [ ] **Step 8: 전체 게이트를 돌린다**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 통과

- [ ] **Step 9: 커밋**

```bash
git add scripts/ci/gates.py .github/workflows/ci.yml docs/CI.md \
        eslint.config.js tests/frontend/test_frontend_gate_wiring.py
git commit -m "ci(frontend): 프론트 게이트 4종을 Tier 0 에 배선 + 문서 갱신"
```

---

## Task 8: StatusBadge 컴포넌트 + 상태 정의 중복 제거

**Files:**
- Create: `app/web/frontend/components/status-badge/macro.jinja`
- Create: `app/web/frontend/components/status-badge/index.ts`
- Create: `app/web/frontend/components/status-badge/styles.css`
- Create: `app/web/frontend/components/status-badge/index.test.ts`
- Modify: `app/web/static/app.js:1-27` (`STATUS_BADGE_CLASSES` · `STATUS_DISPLAY_LABELS` 삭제)
- Modify: `app/web/frontend/entries/main.ts`

**Interfaces:**
- Consumes: Task 1 의 `lib/status.generated.ts` (`StatusTone` · `MODULE_STATUS_LABELS`)
- Produces:
  - `renderStatusBadge(status: string, options?: { size?: "sm" | "md" }): HTMLElement`
  - `normalizeTone(status: string): StatusTone`
  - `statusLabel(status: string): string`
  - 전역 `window.__statusBadge` 로 레거시 `app.js` 가 호출할 수 있게 노출

- [ ] **Step 1: Vitest 테스트를 작성한다**

`app/web/frontend/components/status-badge/index.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { normalizeTone, renderStatusBadge, statusLabel } from "./index";

describe("normalizeTone", () => {
  it("레거시 FAILED 를 anomaly 로 정규화한다", () => {
    expect(normalizeTone("failed")).toBe("anomaly");
    expect(normalizeTone("FAILED")).toBe("anomaly");
  });

  it("queued 를 pending 으로 정규화한다", () => {
    expect(normalizeTone("queued")).toBe("pending");
  });

  it("알 수 없는 상태는 pending 으로 떨어뜨린다", () => {
    expect(normalizeTone("무엇인가")).toBe("pending");
  });

  it("waiting_input 을 running 과 구분한다", () => {
    expect(normalizeTone("waiting_input")).toBe("waiting_input");
    expect(normalizeTone("running")).toBe("running");
  });
});

describe("statusLabel", () => {
  it("생성된 라벨 맵에서 한국어 라벨을 읽는다", () => {
    expect(statusLabel("passed")).toBe("정상");
    expect(statusLabel("error")).toBe("점검실패");
    expect(statusLabel("failed")).toBe("이상징후");
  });
});

describe("renderStatusBadge", () => {
  it("data-tone 속성으로 색을 결정한다(클래스 하드코딩 없음)", () => {
    const el = renderStatusBadge("passed");
    expect(el.dataset.tone).toBe("passed");
    expect(el.className).not.toMatch(/bg-|text-(red|emerald|amber)/);
  });

  it("라벨을 텍스트로 넣는다", () => {
    expect(renderStatusBadge("error").textContent).toBe("점검실패");
  });

  it("size 옵션을 data-size 로 반영한다", () => {
    expect(renderStatusBadge("passed", { size: "sm" }).dataset.size).toBe("sm");
    expect(renderStatusBadge("passed").dataset.size).toBe("md");
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `npm run test`
Expected: FAIL — `Failed to resolve import "./index"`

- [ ] **Step 3: 컴포넌트를 구현한다**

`app/web/frontend/components/status-badge/index.ts`:

```ts
import {
  MODULE_STATUS_LABELS,
  STATUS_TONES,
  type StatusTone,
} from "../../lib/status.generated";

// 서버 status 문자열 → 톤. status_labels.py 의 *_badge_tone() 과 같은 규칙이다.
const TONE_ALIASES: Record<string, StatusTone> = {
  failed: "anomaly",
  queued: "pending",
  not_inspected: "pending",
};

export function normalizeTone(status: string): StatusTone {
  const key = String(status ?? "").toLowerCase();
  const alias = TONE_ALIASES[key];
  if (alias) return alias;
  return (STATUS_TONES as readonly string[]).includes(key) ? (key as StatusTone) : "pending";
}

export function statusLabel(status: string): string {
  const key = String(status ?? "").toLowerCase();
  return MODULE_STATUS_LABELS[key] ?? MODULE_STATUS_LABELS[normalizeTone(key)] ?? key;
}

export function renderStatusBadge(
  status: string,
  options: { size?: "sm" | "md" } = {},
): HTMLElement {
  const el = document.createElement("span");
  el.className = "status-badge";
  el.dataset.tone = normalizeTone(status);
  el.dataset.size = options.size ?? "md";
  el.textContent = statusLabel(status);
  return el;
}
```

`app/web/frontend/components/status-badge/styles.css`:

```css
/* 색은 전부 토큰. 톤별 규칙을 손으로 쓰지 않도록 data-tone 으로 분기한다. */
.status-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 9999px;
  font-weight: 600;
  border: 1px solid transparent;
}

.status-badge[data-size="sm"] { padding: 0.125rem 0.5rem; font-size: 0.6875rem; }
.status-badge[data-size="md"] { padding: 0.25rem 0.625rem; font-size: 0.75rem; }

.status-badge[data-tone="passed"] { background: var(--st-passed-surface); color: var(--st-passed-text); border-color: var(--st-passed-border); }
.status-badge[data-tone="anomaly"] { background: var(--st-anomaly-surface); color: var(--st-anomaly-text); border-color: var(--st-anomaly-border); }
.status-badge[data-tone="error"] { background: var(--st-error-surface); color: var(--st-error-text); border-color: var(--st-error-border); }
.status-badge[data-tone="running"] { background: var(--st-running-surface); color: var(--st-running-text); border-color: var(--st-running-border); }
.status-badge[data-tone="waiting_input"] { background: var(--st-waiting_input-surface); color: var(--st-waiting_input-text); border-color: var(--st-waiting_input-border); }
.status-badge[data-tone="blocked"] { background: var(--st-blocked-surface); color: var(--st-blocked-text); border-color: var(--st-blocked-border); }
.status-badge[data-tone="skipped"] { background: var(--st-skipped-surface); color: var(--st-skipped-text); border-color: var(--st-skipped-border); }
.status-badge[data-tone="cancelled"] { background: var(--st-cancelled-surface); color: var(--st-cancelled-text); border-color: var(--st-cancelled-border); }
.status-badge[data-tone="pending"] { background: var(--st-pending-surface); color: var(--st-pending-text); border-color: var(--st-pending-border); }
```

`app/web/frontend/components/status-badge/macro.jinja` (서버 최초 렌더용 — 같은 마크업):

```jinja
{% macro status_badge(status, label, size="md") -%}
<span class="status-badge" data-tone="{{ status }}" data-size="{{ size }}">{{ label }}</span>
{%- endmacro %}
```

- [ ] **Step 4: Vitest 환경을 설정하고 통과를 확인한다**

`vite.config.ts` 에 `test` 설정을 추가한다 (`defineConfig` 안, `build` 와 형제):

```ts
  test: {
    environment: "jsdom",
    include: ["**/*.test.ts"],
  },
```

`npm install -D jsdom` 후:

Run: `npm run test`
Expected: PASS (10 tests)

- [ ] **Step 5: 엔트리에서 컴포넌트를 로드하고 전역으로 노출한다**

`app/web/frontend/entries/main.ts` 에 추가:

```ts
import "../components/status-badge/styles.css";
import { normalizeTone, renderStatusBadge, statusLabel } from "../components/status-badge/index";

// 레거시 app.js 가 참조하는 다리. P3 에서 app.js 가 소멸하면 함께 제거한다.
window.__statusBadge = { renderStatusBadge, normalizeTone, statusLabel };
```

`declare global` 블록에 추가:

```ts
  interface Window {
    Alpine: typeof Alpine;
    __statusBadge: {
      renderStatusBadge: typeof renderStatusBadge;
      normalizeTone: typeof normalizeTone;
      statusLabel: typeof statusLabel;
    };
  }
```

- [ ] **Step 6: `app.js` 의 중복 정의를 삭제한다**

`app/web/static/app.js` 1~27행의 `STATUS_BADGE_CLASSES` 와 `STATUS_DISPLAY_LABELS` 두 상수를 삭제하고, 이를 쓰던 함수 3개를 다리로 교체한다.

`normalizeOutcomeStatus`(29행) · `statusDisplayLabel`(34행) · `statusBadgeClassName`(590행) 을 다음으로 대체:

```js
// 상태 라벨·색의 SSOT 는 app/core/status_labels.py 이며,
// 생성물(status.generated.ts)을 main.ts 가 window.__statusBadge 로 노출한다.
function normalizeOutcomeStatus(status) {
    return window.__statusBadge.normalizeTone(status);
}

function statusDisplayLabel(entity) {
    return window.__statusBadge.statusLabel(entity?.status ?? entity ?? "");
}

function statusBadgeClassName(status, sizeClasses = "") {
    void sizeClasses; // 크기는 data-size 로 이관됨 — 호출부 호환을 위해 인자만 유지
    return "status-badge";
}
```

`statusBadgeClassName` 호출부는 반환 클래스만 쓰므로, `data-tone` 이 없어 색이 빠진다. 호출부를 찾아 `data-tone` 을 함께 세팅한다:

Run: `grep -n "statusBadgeClassName" app/web/static/*.js`

각 호출부에서 배지 엘리먼트를 만드는 자리를 `window.__statusBadge.renderStatusBadge(status)` 로 교체하는 것이 가장 깔끔하다. 문자열 템플릿으로 HTML 을 만드는 자리는 다음 형태로 바꾼다:

```js
`<span class="status-badge" data-tone="${window.__statusBadge.normalizeTone(status)}" data-size="md">${window.__statusBadge.statusLabel(status)}</span>`
```

- [ ] **Step 7: 중복이 사라졌는지 확인한다**

Run: `grep -rn "STATUS_BADGE_CLASSES\|STATUS_DISPLAY_LABELS" app/web/`
Expected: 출력 없음

Run: `grep -rn "이상징후\|점검실패" app/web/static/*.js`
Expected: 출력 없음 (한국어 상태 라벨이 JS 에서 사라졌다)

- [ ] **Step 8: 화면 검증**

Run: `npm run build`, 앱 실행.

확인 항목:
- `/runs/history` 의 상태 배지가 이전과 같은 의미의 색으로 보이는가
- `/` 의 실행 목록 배지
- Run 상세(`/runs/{id}`) 의 모듈 상태 배지
- 브라우저 콘솔 에러 0건

배지가 회색으로만 보이면 `data-tone` 이 안 붙은 호출부가 남은 것이다. Step 6 으로 돌아간다.

- [ ] **Step 9: 전체 게이트를 돌린다**

Run: `python3 scripts/ci/run_all_gates.py --profile full`
Expected: 전 게이트 통과

Run: `npm run test && npm run typecheck && npm run lint`
Expected: 전부 통과

- [ ] **Step 10: 커밋**

```bash
git add app/web/frontend/ app/web/static/app.js vite.config.ts package.json
git commit -m "refactor(frontend): StatusBadge 컴포넌트화 — 상태 정의 3중 중복 제거"
```

---

## 완료 기준 (P1 DoD)

- [ ] `grep -rn "cdn.jsdelivr\|unpkg.com" app/web/templates/` → 출력 없음
- [ ] `python3 scripts/check_frontend_gates.py` → 통과
- [ ] `python3 scripts/gen_frontend_tokens.py --check` → exit 0
- [ ] `grep -rn "STATUS_BADGE_CLASSES\|STATUS_DISPLAY_LABELS" app/web/` → 출력 없음
- [ ] `npm run build && npm run typecheck && npm run lint && npm run test` → 전부 통과
- [ ] `python3 scripts/ci/run_all_gates.py --profile full` → 전 게이트 통과
- [ ] 육안 검증: 전 화면이 P1 착수 전과 동일 (예외: `skipped`/`cancelled`/`waiting_input` 톤 분리 — Task 6 Step 4 의 의도된 변경)
- [ ] 브라우저 네트워크 탭에 외부 도메인 요청 0건
- [ ] 새로고침 시 FOUC 없음

---

## 이월 항목 (P1 에서 하지 않는 것)

설계 문서 §5 의 검증 방법 중 **"각 페이지가 콘솔 에러 0 으로 렌더되는지" 자동 스모크**는 P1 에 넣지 않는다.

- 이유: 로그인 세션·점검 PC 환경이 필요해 CI 안에서 결정적으로 돌리기 어렵다. 게이트로 넣으면 불안정 실패(flaky)가 생겨 Tier 0 의 신뢰를 떨어뜨린다.
- P1 에서의 대체 수단: Task 4·6·8 의 **육안 검증 스텝**(콘솔 에러 0건 확인 포함)이 DoD 에 들어 있다.
- 이월 시점: P2 에서 일간 현황 화면을 새로 만들 때, 인증이 필요 없는 정적 렌더 경로부터 스모크를 붙인다.

## P1 이후

P2(일간 현황 B안)는 이 계획의 `KpiCard` 부재를 전제로 시작한다. P1 이 만든 것 중 P2 가 직접 소비하는 것:

- `--st-{tone}-{variant}` 토큰 (KPI 카드 상태 색)
- `lib/status.generated.ts` (라벨)
- `components/status-badge/` (컴포넌트 페어 규약 — `macro.jinja` + `index.ts` + `styles.css`)
- `_assets.html` 자산 매크로
- FG-001~005 게이트
