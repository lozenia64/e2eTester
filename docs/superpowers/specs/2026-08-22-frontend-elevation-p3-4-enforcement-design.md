# P3-4 — 강제력 완성 설계

> **상위 설계:** `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md`
> **선행 의존:** P3-2(상황판 `/wall`) · P3-3(일간 리포트 메일). 둘 다 병합된 뒤에 시작한다 — §3.4 가 `/wall` 라우트를, §3.2 가 리포트 렌더러를 전제한다.

---

## 0. Step 7 재편성 — 원래 정의대로 하지 않는 이유

상위 설계는 Step 7 을 "잔여 화면 이관"으로 정의했고, P3-1 스펙 §0 은 그 규모를 13파일 8,909줄로 실측했다. **재실측 결과 8,917줄이고, 전량이 JavaScript 다** — CSS 는 P1~P3-2 를 거치며 이미 `app/web/frontend/` 로 이관을 마쳤다.

그런데 상위 설계 §6 은 이 작업을 스스로 이렇게 평가했다.

> Step 7 이 길다 | 잔여 화면 이관은 지루하며 **"우와" 에 기여하지 않는다** | 미이관 화면은 구 스타일로 계속 동작한다. **무기한 연기 가능**

이 프로그램의 목적은 "사내 동료·경영진이 감탄하는 화면"이었다. 그 기준에서 8,917줄 이관은 **아무도 알아채지 못하는 작업**이다. 반면 이관 뒤에 가려져 있던 항목 중에는 *명시된 목표인데 미달인 것*과 *게이트가 막으려던 병이 이미 발생한 것*이 있다.

따라서 Step 7 을 규모가 아니라 **가치 순으로 재편성한다.**

| 조각 | 내용 | 성격 |
| --- | --- | --- |
| **P3-4 (이 문서)** | CDN 0 완성 · FG-006 allowlist 0 · 메일 색 SSOT 수렴 · 리포트→상황판 링크 | 목표 미달 상환 + 결함 제거 |
| **P4 (별도 사이클)** | 레거시 JS 13파일 8,917줄 이관 | 기계적 대량 작업 |

P4 는 이 문서의 범위가 아니다. 다만 §3.1 이 P4 에 남기는 부채의 만료 조건을 명시한다.

---

## 1. 문제

### 1.1 게이트에 뚫어둔 구멍 3개

P1 이 도입한 프론트엔드 게이트 FG-001~006 은 각각 실제로 발생했던 사고를 막는다. 그런데 **세 곳에 예외가 뚫려 있고, 그 예외가 지금 어떤 상태인지 아무도 확인한 적이 없다.**

| # | 구멍 | 실측 | 뚫린 사유 | 사유의 현재 상태 |
| --- | --- | --- | --- | --- |
| 1 | `FG001_EXCEPTIONS` | 3파일 4 URL | "`vite.config.ts` 는 단일 엔트리만 지원해 그 구조 변경은 이후 작업으로 미룬다" | **소멸.** P3-2 가 `wall` 엔트리를 추가해 다중 엔트리가 됐다 |
| 2 | `FG006_ALLOWLIST` | 4파일 | "Step 7 이 화면을 이관할 때마다 한 줄씩 지운다" | 유효하나, §1.3 이 보여주듯 **대기 중에 이미 드리프트가 발생했다** |
| 3 | 메일 색이 SSOT 밖 | 상태 색 10개 | P3-3 D5 — "통일하면 사람들이 익숙한 메일 색이 바뀐다. 팔레트 통일은 Step 7 로" | 유효. 이 문서가 그 값을 치른다 |

### 1.2 미달 목표 — CDN 0

상위 설계 §2.1 의 목표 3번은 **"외부 CDN 런타임 의존을 `0` 으로 만든다"** 였다. P1 은 자기가 §1.4 에 나열한 4종(Pretendard · `@tailwindcss/browser` · htmx · Alpine.js)을 제거했으나, **그 재고에 없던 4종이 남아 있다.**

```text
app/web/templates/admin/runs.html:834   chart.js@4.4.7             (cdn.jsdelivr.net)
app/web/templates/admin/runs.html:835   echarts@5.5.1              (cdn.jsdelivr.net)
app/web/templates/admin/stats.html:189  plotly.js-dist-min@2.35.2  (cdn.jsdelivr.net)
app/web/templates/insights.html:267     plotly.js-dist-min@2.35.2  (cdn.jsdelivr.net)
```

상위 설계 §1.4 가 적은 위험은 그대로 살아 있다 — *"사내망 정책 변경·CDN 장애 시 화면이 통째로 깨진다."* 관리자 통계·인사이트 화면 전체가 여기에 걸린다.

목표가 "0" 이었으므로 **부분 달성은 달성이 아니다.**

### 1.3 allowlist 는 안전하지 않았다 — 실측

`FG006_ALLOWLIST` 는 "이관 대기 중이니 잠시 봐준다"는 뜻으로 뒀다. 그러나 대기하는 동안 **막으려던 병이 그 안에서 진행됐다.**

`mobile_trigger.html:90-98` 의 `STATUS_VIEW` 를 SSOT(`app/core/status_labels.py`)와 대조한 결과:

| status | SSOT | `mobile_trigger.html` | |
| --- | --- | --- | --- |
| `PENDING` | 대기 | 진행 중 | 어긋남 |
| `RUNNING` | 실행 중 | 진행 중 | 어긋남 |
| `WAITING_INPUT` | 입력 대기 | 인증번호 대기 | 어긋남 |
| `CANCELLED` | 취소 | 취소됨 | 어긋남 |
| `PASSED` | 정상 | 정상 | 일치 |
| `ANOMALY` | 이상징후 | 이상징후 | 일치 |
| `FAILED` | 이상징후 | 이상징후 | 일치 |
| `ERROR` | 점검실패 | 점검실패 | 일치 |

**8개 중 4개가 이미 다르다.** FG-006 은 하나도 잡지 못했다 — 이 게이트는 SSOT 라벨 문자열과 정확히 일치하는 리터럴이 enum 값과 같은 줄에 있을 때만 탐지하는데, 드리프트된 라벨은 정의상 SSOT 문자열과 다르기 때문이다.

일부는 의도한 모바일 문구일 수 있다("인증번호 대기"는 OTP 맥락에서 더 친절하다). **문제는 어느 쪽인지 아무 기록이 없다는 것이다.** 의도한 예외와 방치된 드리프트를 구분할 수 없는 상태 자체가 결함이다.

### 1.4 실측 요약

| 항목 | 값 |
| --- | --- |
| 남은 CDN | 4 URL / 3 파일 (라이브러리 3종) |
| FG-006 탐지 위반 | 16건 (줄 단위) / 4파일 |
| **실제** 상태→표현 매핑 항목 | **29개** — `_macros` 10 · `admin/runs` 8 · `mobile_trigger` 8 · `schedules` 3 (§3.3) |
| 메일 상태 색 상수 | **10개** — 통일 대상 |
| 메일 레이아웃 색 상수 | 7개 — 대상 아님 |
| 메일 hex 출현 | 18곳 / 고유 16값 (`#ffffff`·`#6b7280` 이 두 번씩). 전량 `report_renderer.py`, `run_completion_email.py` 는 0개 |
| 상태 색 드리프트 | 5쌍 중 4쌍 (`pending` 글자색만 이미 일치) |

---

## 2. 목표 · 비목표

### 2.1 목표

1. `FG001_EXCEPTIONS` 를 **삭제**한다 — 상위 설계 목표 3번(CDN 0)을 실제로 달성한다.
2. `FG006_ALLOWLIST` 를 **삭제**한다 — 템플릿의 상태→표현 매핑 중복을 0 으로 만든다.
3. 메일 상태 색을 웹과 **같은 SSOT 에서 파생**시키고, 새 게이트로 고정한다.
4. 일간 리포트에서 상황판으로 가는 길을 연다.

### 2.2 비목표 (명시적 YAGNI)

- **레거시 JS 8,917줄 이관** — P4 로 분리. 이 문서는 그 코드를 한 줄도 고치지 않는다.
- **`report_renderer.py`(1,008줄) · `run_completion_email.py`(1,759줄) 분할** — 성격이 다른 리팩터다. 팔레트 통일은 파일 상단 상수 10개만 건드리므로 분할 없이 가능하다.
- **`FG004_ALLOWLIST` 해소** (`app.css` 1,411줄 · `dashboard.css` 892줄 분할)
- **차트 라이브러리 통합** — 3종을 그대로 유지한다(§4 D1).
- **`app.js` 와 서버 렌더의 이중 경로 통합** — P4.

---

## 3. 설계

### 3.1 CDN 0 — 글로벌 브리지 엔트리

#### 문제의 구조

차트 라이브러리를 npm 으로 당기면 그것을 쓰는 레거시 JS 가 전역 심볼(`Chart` · `echarts` · `Plotly`)을 참조하고 있어 모듈로 바꿔야 한다. 해당 파일은 셋이고 합계 2,273줄이다.

```text
app/web/static/admin-runs.js   1,558줄  (Chart, echarts)
app/web/static/insights.js       499줄  (Plotly)
app/web/static/admin-stats.js    216줄  (Plotly)
```

즉 CDN 0 을 순진하게 추진하면 **P4 의 25% 가 이 문서로 끌려 들어온다.** 그러면 이 조각도 P4 도 어중간해진다.

#### 해법 — 라이브러리당 두 줄짜리 엔트리

전역에 얹는 얇은 브리지 엔트리를 만든다. 레거시 JS 는 손대지 않는다.

```ts
// app/web/frontend/entries/vendor-plotly.ts
// 과도기 장치 — P4 가 insights.js·admin-stats.js 를 이관하면 이 파일을 삭제한다.
import Plotly from "plotly.js-dist-min";

declare global {
  interface Window {
    Plotly: typeof Plotly;
  }
}

window.Plotly = Plotly;
```

`vendor-chart.ts`(`chart.js/auto` — UMD 빌드와 동일하게 전 컨트롤러 자동 등록) · `vendor-echarts.ts`(`import * as echarts`)도 같은 형태다.

npm 의존성은 **CDN 과 정확히 같은 버전으로 고정**한다: `chart.js@4.4.7` · `echarts@5.5.1` · `plotly.js-dist-min@2.35.2`. 버전을 올리지 않는 것이 이 항목의 안전 조건이다 — 이 문서는 "같은 것을 다른 경로로 배달"할 뿐, 차트 동작을 바꾸지 않는다.

#### 왜 안전한가 — 로드 순서에 걸리지 않는다

레거시 JS 세 파일 모두 **로드 시점이 아니라 호출 시점에** 전역을 확인한다.

```text
admin-runs.js:636   if (!canvas || typeof Chart === "undefined") { ... }
admin-runs.js:754   if (!el || typeof echarts === "undefined") { ... }
admin-stats.js:95   if (typeof Plotly === 'undefined') return;
insights.js:49      if (!el || typeof Plotly === "undefined" || !figure) return;
```

차트를 그리는 함수 안에서 확인하므로, 브리지 엔트리가 그 함수보다 먼저 실행되기만 하면 된다. 실제로 그렇다 — HTML 명세상 `defer` 클래식 스크립트와 `type="module"` 스크립트는 **같은 목록에 들어가 문서 순서대로** 실행되므로, 템플릿에서 브리지를 레거시 스크립트보다 위에 두면 순서가 보장된다. 게다가 `insights.js` 는 탭을 지연 로드하므로 실제 호출은 사용자 상호작용 이후다.

#### 템플릿 변경

CDN `<script src="https://...">` 를 manifest 경유 엔트리 로드로 바꾼다. 기존 `_assets.html` 의 `asset_script` 매크로를 그대로 쓰므로 해시 파일명이 자동으로 붙는다. **레거시 `/static/*.js` 줄의 수동 `?v=N` 은 그대로 남는다** — 그 파일들의 이관이 P4 의 몫이기 때문이다.

| 템플릿 | 추가할 엔트리 |
| --- | --- |
| `app/web/templates/admin/runs.html` | `vendor-chart` · `vendor-echarts` |
| `app/web/templates/admin/stats.html` | `vendor-plotly` |
| `app/web/templates/insights.html` | `vendor-plotly` |

**일간 현황(`dashboard.html`)과 상황판(`wall.html`)에는 아무것도 추가하지 않는다.** 페이지별 엔트리이므로 이 프로그램이 만든 "우와" 화면들은 차트 라이브러리를 한 바이트도 받지 않는다.

#### 남기는 부채와 만료 조건

`window` 전역 할당은 과도기 장치다. 스펙에 만료 조건을 명시한다.

> **`entries/vendor-*.ts` 3개는 P4 가 해당 화면을 이관하는 시점에 삭제한다.** `admin-runs.js` 이관 시 `vendor-chart.ts`·`vendor-echarts.ts` 를, `insights.js`·`admin-stats.js` 둘 다 이관된 시점에 `vendor-plotly.ts` 를 지운다. 파일 상단 주석에 이 조건을 적는다.

### 3.2 상태 색 SSOT 수렴

#### 지금 hex 원본이 빌드 스크립트에 있다

```text
scripts/gen_frontend_tokens.py:47   PALETTE: dict[str, dict[str, str]]
```

"정상은 초록, 점검실패는 빨강"은 도메인 지식이지 빌드 도구의 소관이 아니다. 그리고 이 위치 때문에 **메일이 이 값을 쓸 수 없다** — 앱 코드가 `scripts/` 를 import 하는 것은 방향이 거꾸로다(`scripts/` 는 패키지가 아니며 배포 산출물에 없을 수 있다).

#### 이사

`PALETTE` 를 `app/core/status_colors.py`(신규)로 옮긴다. `app/core/status_labels.py` 옆이 제자리다 — 같은 상태 축의 라벨과 색이 나란히 있게 된다.

소비자는 둘 다 import 방향이 기존과 같다.

```text
scripts/gen_frontend_tokens.py        →  app.core.status_colors
    (이미 app.core.status_labels 를 import 중)
app/notifications/report_renderer.py  →  app.core.status_colors
```

`pyproject.toml` 의 importlinter 계약은 `root_package = "app"` 이고 `app.notifications` → `app.core` 를 금지하는 계약이 없으므로 **계약 변경이 없다.**

#### 무엇을 통일하고 무엇을 두는가

`report_renderer.py` 의 색 상수 17개는 성격이 갈린다.

| 그룹 | 상수 | 처리 |
| --- | --- | --- |
| 메일 레이아웃 색 (7개) | `PAGE_BG` `CARD_BG` `INK` `MUTED` `BORDER` `SOFT_BG` `LABEL_BG` | **그대로 둔다.** 상태와 무관한 메일 크롬이다. `MUTED` 는 `NEUTRAL_COLOR` 와 값이 같지만(`#6b7280`) 의미가 달라 따로 둔다 |
| 상태 색 (10개) | `PASS_*` `FAIL_*` `WARN_*` `NEUTRAL_*` `INFO_*` | **SSOT 파생으로 바꾼다** |

매핑은 메일의 `(글자색, 옅은 배경)` 쌍을 웹 팔레트의 `(text, surface)` 축에 대응시킨다.

| 메일 상수 | 웹 톤 · 축 | 현재 | 통일 후 |
| --- | --- | --- | --- |
| `PASS_COLOR` | `passed.text` | `#2f8f4e` | `#047857` |
| `PASS_SOFT_BG` | `passed.surface` | `#e9f6ee` | `#d1fae5` |
| `FAIL_COLOR` | `error.text` | `#c0392b` | `#b91c1c` |
| `FAIL_SOFT_BG` | `error.surface` | `#fdecea` | `#fee2e2` |
| `WARN_COLOR` | `anomaly.text` | `#b7791f` | `#b45309` |
| `WARN_SOFT_BG` | `anomaly.surface` | `#fdf6e3` | `#fef3c7` |
| `NEUTRAL_COLOR` | `pending.text` | `#6b7280` | `#6b7280` (이미 일치) |
| `NEUTRAL_SOFT_BG` | `pending.surface` | `#f1f3f5` | `#f4f4f5` |
| `INFO_COLOR` | `running.text` | `#2563eb` | `#1d4ed8` |
| `INFO_SOFT_BG` | `running.surface` | `#eef3ff` | `#dbeafe` |

#### 정직하게 — 메일이 눈에 띄게 바뀐다

**글자색 변화는 미미하다.** `#2f8f4e` → `#047857` 은 둘 다 진한 초록이고, `#c0392b` → `#b91c1c` 도 둘 다 진한 빨강이다.

**배경색 변화는 눈에 띈다.** 웹의 `surface` 축은 화면에서 배지 바탕으로 쓰도록 만든 값이라 메일이 쓰던 옅은 톤보다 채도가 높다. 예를 들어 정상 배경은 `#e9f6ee`(거의 흰색에 가까운 연녹)에서 `#d1fae5`(뚜렷한 민트)로 간다.

P3-3 의 D5 가 미룬 이유가 정확히 이것이었다 — *"통일하면 사람들이 익숙한 메일 색이 바뀐다."* 이 문서는 그 값을 **의도적으로 치른다.** 매일 아침 오는 리포트와 화면이 다른 색으로 같은 상태를 말하는 것이 더 나쁘기 때문이다.

이 변경은 되돌릴 수 있다(상수 매핑 한 곳). 실제 메일을 받아보고 너무 강하면 `surface` 대신 별도의 `mail_surface` 축을 SSOT 에 추가하는 것이 후속 선택지다 — 다만 그 판단은 실물을 본 뒤에 한다.

### 3.3 FG-006 allowlist 0

위반은 세 가지 모양이다. 각각 다른 해법이 필요하다.

#### (a) 글리프 맵 — `_macros.html:3-11`

```jinja
{% macro module_glyph(tone) -%}
{% set g = {
  'passed': '✓', 'anomaly': '!', 'error': '×',
  'running': '●', 'waiting_input': '●',
  'not_inspected': '○', 'pending': '○',
  'blocked': '—', 'skipped': '—', 'cancelled': '—'
} %}
```

글리프는 톤의 표현 축이다 — 색·라벨과 같은 자리에 있어야 한다. `app/core/status_colors.py` 에 톤→글리프 축을 추가하고(색과 같은 파일에 두는 편이 "톤의 표현"이라는 하나의 개념을 흩지 않는다), 템플릿은 조회만 한다.

`not_inspected` 는 `STATUS_TONES` 9축에 없는 키다. 화면 전용 파생 상태(점검 안 함)이므로 **`pending` 과 같은 글리프를 쓰도록 명시적으로 매핑**하고, 축 자체를 늘리지 않는다.

#### (b) 필터·범례 목록 — `admin/runs.html` · `schedules.html`

```html
<!-- admin/runs.html:732-735  체크박스 팝오버 -->
<label ...><input type="checkbox" ... value="PASSED" /> 정상</label>
<!-- admin/runs.html:773-776  숨은 select (같은 목록 두 번째) -->
<option value="PASSED">정상</option>
```

`admin/runs.html` 은 **같은 4개 항목을 한 파일 안에서 두 번** 적는다. SSOT 와의 중복 이전에 자기들끼리 중복이다. 서버가 `(value, label)` 목록 하나를 컨텍스트로 주고 템플릿이 두 곳에서 순회한다.

`schedules.html:250-255` 의 범례도 같은 처리를 한다. 다만 이 범례에는 `planned`(예정) · `missed`(누락)처럼 **상태가 아닌 스케줄 뷰 상태**가 섞여 있다. 이들은 SSOT 대상이 아니므로 목록을 합치지 않고, 상태 3개만 SSOT 순회로 바꾸고 뷰 상태는 템플릿에 남긴다.

#### (c) 인라인 JS 맵 — `mobile_trigger.html:90-98`

```js
const STATUS_VIEW = {
    PENDING: { label: "진행 중", cls: "badge-running", spin: true },
    // ...
};
```

서버가 SSOT 에서 만든 맵을 주입한다. 축은 셋이다.

- `label` — SSOT 그대로. **§1.3 의 드리프트 4건이 여기서 해소된다.**
- `cls` — 기존 `badge-*` 클래스. 이 화면은 P4 이관 대상이므로 클래스 체계는 건드리지 않고 톤→클래스 대응만 서버가 만든다.
- `spin` — **SSOT 가 아니다.** "진행을 나타내는 상태면 회전"이라는 뷰 규칙이며, 현재 `PENDING`·`RUNNING` 만 참이다. 파생 규칙으로 명시하고 SSOT 축을 늘리지 않는다.

드리프트 4건 중 `WAITING_INPUT`("인증번호 대기")은 OTP 맥락에서 의도한 문구일 수 있다. **이 문서는 SSOT("입력 대기")로 통일한다** — 의도한 예외라면 SSOT 에 그렇게 적어 모든 화면이 함께 바뀌어야지, 한 템플릿만 몰래 다른 것은 §1.3 이 지적한 상태 그대로다.

#### 게이트 자체의 결함 — 과소 계수 2건

FG-006 은 위반 16건(줄 단위)을 보고한다. 그러나 네 파일이 실제로 들고 있는 상태→표현 매핑은 **29개 항목**이다 — `_macros` 10 · `admin/runs` 8 · `mobile_trigger` 8 · `schedules` 3. 탐지가 새는 원인이 둘이다.

**원인 1 — `취소` 가 `_DOMAIN_LABELS` 에 없다 (3건)**

```text
admin/runs.html:735     value="CANCELLED" /> 취소        (미탐지)
admin/runs.html:776     <option value="CANCELLED">취소   (미탐지)
mobile_trigger.html:98  CANCELLED: { label: "취소됨"     (미탐지 — 드리프트라 문자열도 불일치)
```

`_DOMAIN_LABELS` 에 `취소` 를 추가한다. 이 규칙은 **enum 값과 라벨이 같은 줄에 있을 때만** 발화하므로 오탐 위험이 없다 — `admin/runs.html:825` 의 취소 버튼과 `:648` 의 설명 문구에는 enum 값이 없어 걸리지 않는다.

**원인 2 — 맵 키 규칙이 줄 단위다**

맵 규칙은 **한 줄 안에 상태 키가 2개 이상**(`_STATUS_MAP_MIN_KEYS = 2`) 있어야 발화한다. `_macros.html` 은 한 줄에 3개씩 적혀 있어 걸렸지만, 한 항목씩 줄바꿈한 맵은 영영 걸리지 않는다. `mobile_trigger.html:90-98` 실측:

```text
91  PENDING: { label: "진행 중", ... }        키 1개  →  놓침
92  RUNNING: { label: "진행 중", ... }        키 1개  →  놓침
93  WAITING_INPUT: { label: "인증번호 대기" }  키 1개  →  놓침
    ... 8줄 전부 동일
```

**8개짜리 상태 키 맵인데 맵 규칙에 통째로 안 잡힌다.** 대소문자 문제도 겹쳐 있으나(`_STATUS_MAP_KEYS` 는 전부 소문자, `re.IGNORECASE` 없음) **대소문자만 고쳐도 해결되지 않는다** — 줄당 키가 1개라 여전히 문턱 미달이다. 규칙을 **줄 단위에서 블록 단위로** 바꿔야 한다.

**두 결함이 겹쳐 만든 사각지대.** 맵 규칙이 못 보고, 남은 탐지 경로(enum+라벨 동일 줄)는 §1.3 의 드리프트 4건을 원리상 잡을 수 없다 — 드리프트된 라벨은 SSOT 문자열과 다르기 때문이다. **결국 이 게이트는 "아직 어긋나지 않은 중복"만 잡는다.** 어긋나고 나면 보이지 않게 되는데, 그때가 정작 문제가 된 시점이다.

**블록 단위 탐지로 바꾼다** — 중괄호 블록(또는 고정 크기 창) 안에서 서로 다른 상태 키가 2개 이상이면 발화. 대소문자도 무시한다. 이는 P3-1 이 FG-006 을 어휘 탐지에서 구조 탐지로 바꿨을 때와 같은 성격의 변경이므로 **같은 검증 절차를 따른다: 전체 템플릿에 돌려 오탐 0 을 확인한 뒤 채택한다.** 오탐이 나오면 창 크기·문턱을 조정하되, 조정 결과를 스펙이 아니라 코드 주석에 실측과 함께 남긴다.

이 화면 자체는 §3.3(c) 가 맵을 서버 주입으로 바꿔 어차피 사라진다. **게이트 수정의 값은 이 청소가 아니라 다음번을 막는 데 있다.**

### 3.4 리포트 → 상황판 딥링크

#### P3-3 이 링크를 뺀 이유 중 절반이 해소됐다

P3-3 의 D6 은 이유를 둘 댔다.

> 기존 Run 완료 메일에 링크가 하나도 없고 **공개 URL env 자체가 없다.** 링크를 넣으려면 새 base URL env + **"대시보드는 로그인이 필요하다"는 문제**를 함께 풀어야 한다.

**뒤쪽은 P3-2 가 해결했다.** `/wall` 은 비인증 읽기 전용 라우트다. 남은 것은 공개 URL 설정뿐이다.

#### 설계

신규 설정 `E2E_PUBLIC_BASE_URL`, **기본값 빈 문자열.**

링크는 두 조건이 **모두** 참일 때만 렌더한다.

1. `E2E_PUBLIC_BASE_URL` 이 비어 있지 않다
2. `wall_enabled` 가 `true` — 거짓이면 그 URL 은 404 다(`app/api/routes_wall.py:39-41`)

둘 중 하나라도 아니면 링크 없이 현재와 동일하게 발송한다. **D6 이 지키려던 "자족적 메일" 성질이 기본값으로 보존된다** — 설정을 켠 사람만 링크를 얻는다.

기존 `worker_base_url`(`E2E_WORKER_BASE_URL`)을 재사용하지 않는다. 그것은 API 가 워커에 접속하는 내부 주소이며, 사람이 브라우저로 여는 공개 주소와 성격이 다르다.

### 3.5 게이트 변경

| 게이트 | 변경 |
| --- | --- |
| **FG-001** | `FG001_EXCEPTIONS` 딕셔너리 **삭제.** 예외 없는 절대 규칙이 된다 |
| **FG-005** | 변경 없음 — 벤더 3종이 manifest 를 타므로 allowlist 가 늘지 않는다 |
| **FG-006** | `FG006_ALLOWLIST` **삭제** + `_DOMAIN_LABELS` 에 `취소` 추가 + 맵 규칙을 **줄 단위 → 블록 단위**(대소문자 무시)로 (§3.3) |
| **FG-007 (신규)** | `report_renderer.py` 의 상태 색이 `status_colors.PALETTE` 파생인지 — 상태용 hex 리터럴 금지. 메일 레이아웃 색 7개는 명시적 예외로 둔다 |

FG-004 는 이 문서의 범위 밖이다(`FG004_ALLOWLIST` 2개 유지).

---

## 4. 결정

| # | 결정 | 근거 |
| --- | --- | --- |
| D1 | **차트 라이브러리 3종을 그대로 self-host.** 통합하지 않는다 | Plotly 는 서버의 `insights_charts.py`·`stats_charts.py` 가 Python `plotly.graph_objects` 로 figure JSON 을 만들어 내려보내므로 교체하면 파이썬 빌더를 다시 써야 한다. Chart.js↔ECharts 통합은 잘 돌아가는 차트를 다시 쓰는 회귀 위험을 진다. 이 문서의 목적은 **배달 경로 변경이지 차트 변경이 아니다** |
| D2 | **글로벌 브리지 엔트리.** 레거시 JS 를 고치지 않는다 | 대안은 `admin-runs.js`(1,558줄) 등 2,273줄을 이 문서로 끌어오는 것인데, 그러면 P4 를 반만 앞당겨 하는 셈이 된다. 브리지는 만료 조건이 명확한 부채다(§3.1) |
| D3 | **vendor UMD 파일 복사를 쓰지 않는다** | manifest 를 타지 않아 해시가 없고 수동 `?v=N` 이 남으며, FG-005 에 새 예외를 뚫어야 한다. **게이트 구멍을 막으려다 다른 구멍을 내는 것** |
| D4 | **`PALETTE` 를 `app/core/` 로 옮긴다** | 도메인 지식이 빌드 스크립트에 있으면 앱이 쓸 수 없다. 이사 방향이 기존 import 방향과 같아 계약 변경이 없다 |
| D5 | **메일 배경색이 바뀌는 것을 감수한다** | 화면과 메일이 같은 상태를 다른 색으로 말하는 것이 더 나쁘다. 되돌리기 비용은 상수 매핑 한 곳이며, 실물을 본 뒤 `mail_surface` 축 신설이 후속 선택지로 남는다 |
| D6 | **딥링크는 기본 꺼짐** | 공개 URL 은 배포 환경마다 다르고, 잘못된 URL 이 든 메일은 회수할 수 없다. 켠 사람만 얻는다 |
| D7 | **`mobile_trigger.html` 의 라벨 드리프트를 SSOT 로 통일한다** | 의도한 예외라면 SSOT 에 적어 모든 화면이 함께 바뀌어야 한다. 한 템플릿만 다른 상태가 §1.3 이 지적한 병 자체다 |

---

## 5. 검증

| 대상 | 방법 |
| --- | --- |
| CDN 0 | `FG001_EXCEPTIONS` 삭제 후 `frontend_gates` 통과. 템플릿 전체에 `https://` 자산 참조 0건 |
| 차트가 실제로 그려지는가 | `admin/runs`(추세선·히트맵) · `admin/stats` · `insights` 세 화면에서 렌더 확인. **네트워크에서 `cdn.jsdelivr.net` 을 차단한 상태로도** 동일해야 한다 — 이것이 이 항목의 진짜 합격 조건이다 |
| 번들 격리 | 일간 현황·상황판의 로드 자산 목록에 차트 라이브러리가 없음 |
| 팔레트 수렴 | `report_renderer.py` 에 상태용 hex 리터럴 0건(FG-007). 통일 전후 메일 HTML 을 렌더해 **상태 색만 바뀌고 레이아웃 색 7개는 불변**임을 단언 |
| SSOT 라벨 일치 | `mobile_trigger.html` 렌더 결과의 라벨이 `MODULE_STATUS_LABELS` 와 전수 일치 |
| FG-006 완성 | `FG006_ALLOWLIST` 삭제 후 위반 0건. `취소` 추가가 오탐을 만들지 않는지(`admin/runs.html:825` 취소 버튼) 확인. **고친 게이트를 수정 전 코드에 돌려** `mobile_trigger.html` 의 맵 8개를 잡는지, 그리고 **전체 템플릿에서 오탐 0** 인지 확인 |
| 딥링크 3분기 | env 미설정 → 링크 없음 / 설정 + `wall_enabled=false` → 링크 없음 / 설정 + `true` → 링크 있음 |
| 전체 | `run_all_gates --profile full` |

**DoD:** 게이트 예외 3개가 모두 사라지고, 차트 3종이 CDN 차단 상태에서 정상 렌더되며, 메일과 화면이 같은 색으로 같은 상태를 말한다.

---

## 6. 리스크 · 한계

| 항목 | 내용 | 대응 |
| --- | --- | --- |
| **plotly 번들이 크다** | `plotly.js-dist-min` 은 수 MB 급이다. 빌드 시간과 `build_web` 게이트가 느려진다 | 페이지별 엔트리라 일간 현황·상황판은 영향 0. 증가분을 측정해 기록한다 |
| **rollup 이 거대 UMD 를 처리하지 못할 수 있다** | 사전 번들된 dist 를 다시 번들할 때 경고·실패 사례가 있다 | **구현 첫 단계에서 세 라이브러리가 빌드되는지부터 확인**한다. 실패하면 그 시점에 보고하고 설계를 재검토한다 — 우회를 즉흥으로 만들지 않는다 |
| **메일 배경색이 눈에 띄게 바뀐다** | 사용자가 익숙한 색이 변한다 | D5 의 의도된 절충. 실물 확인 후 `mail_surface` 축 신설이 후속 선택지 |
| **`window` 전역 오염** | 브리지 엔트리 3개가 전역을 쓴다 | 만료 조건을 파일 주석과 스펙에 명시(§3.1). P4 이관 시 삭제 |
| **`mobile_trigger.html` 라벨 변경** | "인증번호 대기" → "입력 대기" 등 4건이 사용자 눈에 보인다 | D7. 의도한 문구라면 SSOT 를 고쳐 전 화면이 함께 바뀌게 한다 |
| **FG-007 이 메일 렌더러만 본다** | 다른 파이썬 모듈이 상태 hex 를 쓰면 못 잡는다 | 현재 `run_completion_email.py` 는 hex 0개이고 메일 렌더 경로는 `report_renderer.py` 단일이다. 범위가 늘면 게이트를 넓힌다 |

---

## 7. P3-4 이후 — P4 로 넘기는 것

| 항목 | 규모 |
| --- | --- |
| 레거시 JS 이관 (`app/web/static/*.js` → `app/web/frontend/`) | 13파일 8,917줄 |
| `FG005_ALLOWLIST` 비우기 | 14줄 |
| `FG004_ALLOWLIST` 비우기 (`app.css` 1,411 · `dashboard.css` 892 분할) | 2파일 |
| `entries/vendor-*.ts` 3개 삭제 | 이 문서가 남기는 부채 |
| 수동 `?v=N` 캐시버스팅 잔여분 제거 | 템플릿 다수 |
| `app.js` 와 서버 렌더의 이중 경로 통합 | — |
| `execute.html:6` 의 `tone_pill`(색명 키 맵) 정리 | — |
| `_macros.html` 정리 후 상황판 매트릭스 공통화 재검토 | P3-2 가 남긴 것 |
| `report_renderer.py`(1,008줄) · `run_completion_email.py`(1,759줄) 분할 | 성격이 다른 리팩터 — 별도 판단 |

**이관 수준:** 기계적 `.js`→`.ts` 가 아니라 **타입 + 책임 분리 + Vitest** 로 한다(사용자 결정). `admin-runs.js` 1,558줄 하나만으로도 P3-1 급 규모이므로 P4 도 다시 쪼개야 할 가능성이 높다.

---

## 8. 참조

- 상위 설계: `docs/superpowers/specs/2026-08-19-frontend-elevation-design.md` (§1.4 CDN 위험 · §2.1 목표 3 · §6 Step 7 평가)
- P3 분해표: `docs/superpowers/specs/2026-08-20-frontend-elevation-p3-1-run-live-design.md` §0
- FG-006 설계 근거: 같은 문서 §3.6
- 미룬 항목의 출처: `docs/superpowers/specs/2026-08-21-frontend-elevation-p3-3-daily-report-design.md` D4·D5·D6
- 게이트 SSOT: `scripts/check_frontend_gates.py` · `scripts/ci/gates.py` · `docs/CI.md`
- 상태 SSOT: `app/core/status_labels.py`
