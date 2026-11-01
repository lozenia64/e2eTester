# SPEC-SYS-MHM: 대표홈페이지(모바일)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SYS-MHM` |
| **상태** | `approved` |
| **공통 Spec** | [SPEC-SYS-REP-HOME](_shared-rep-homepage.md) |
| **SSOT** | `docs/scenarios/mhm.md` |
| **manifest** | `app/systems/mhm/manifest.yaml` |
| **display_order** | 20 |
| **URL** | `https://m.hwgeneralins.com` |
| **execution_profile** | `heavy` |

## 1. HOM 대비 차이

| 항목 | MHM |
| --- | --- |
| URL | m.hwgeneralins.com |
| Channel | `MOBILE_CHANNEL` |
| PageObject | `page_objects/mhm/` |
| workflow_name | `mhm_login` |
| 모듈 수 | 8 (마케팅동의 없음) |
| GNB/메뉴 | 모바일 UI (MY한화 메뉴, 전체메뉴 등) |
| 증명서 경로 | 전체메뉴 → 증명서발급 → 보험증권(장기/자동차) |

인증·상수·LoginFlow·보상 결합 규칙은 `SPEC-SYS-REP-HOME` 동일.

## 2. Manifest SSOT

`app/systems/mhm/manifest.yaml` · `docs/scenarios/mhm.md` — 모듈 메타·run_form SSOT. 본 Spec은 AC만.

**모듈 ID:** `mhm.main.access`, `mhm.login`, `mhm.contract.list`, `mhm.contract.detail`, `mhm.compensation.charge`, `mhm.compensation.result`, `mhm.compensation.cancel`, `mhm.proof.long_term_policy`

## 3. 모바일 필수 AC

```gherkin
Given any mhm module executes
When RepHomepageRuntime is built
Then apply_mobile_device_mode() before first navigation
And mobile viewport active throughout Run
```

## 4. 모듈별 AC (HOM 대비 UI 차이만 명시)

### mhm.main.access

```gherkin
When MainAccessFlow runs with MOBILE_CHANNEL steps
Then navigate https://m.hwgeneralins.com in mobile mode
And dismiss mobile popups
Then PASSED
```

### mhm.login

`SPEC-SYS-HOM` hom.login AC 동일 (phone OTP pause / kakao no pause).

### 로그인 전후 하단 배너 (`.dialog.bottom.bottom_bnr`)

```gherkin
Given 로그인 전 또는 로그인 후 팝업 점검 단계
When 하단 배너가 표시되어 있으면
Then 닫기 버튼으로 닫고 다음 단계를 진행한다
When 배너가 없거나 처리 도중 사라지면
Then 오류·경고 없이 다음 단계를 진행한다
When 배너를 닫지 못하면
Then 경고만 남기고 다음 단계를 진행한다
```

### mhm.contract.list / detail

```gherkin
# list: 모바일 MY한화 → 개인계약 조회 → 건수 확인
# detail: 첫 선택 가능 계약 → 상세 정보 영역
```

### mhm.compensation.*

```gherkin
# charge/result/cancel: HOM 동일 플로우, 모바일 보상 메뉴 경로
# CLAIM_CONTENT_TEXT 결합 규칙 동일 (REP-HOME §3)
```

### mhm.proof.long_term_policy

```gherkin
When LongTermPolicyCertificateFlow runs (mhm steps)
Then 전체메뉴 → 증명서발급 → 보험증권(장기/자동차)
And first contract PDF download
Then PASSED
```

## 5. 의존성 그래프

```text
main.access → login ─┬→ contract.list → detail
                     ├→ compensation.charge ─┬→ result
                     │                        └→ cancel
                     └→ proof.long_term_policy
```

## 6. 변경 동기화

`manifest.yaml` ↔ 본 Spec ↔ `docs/scenarios/mhm.md`
