# SPEC-SYS-HOM: 대표홈페이지(PC)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SYS-HOM` |
| **상태** | `approved` |
| **공통 Spec** | [SPEC-SYS-REP-HOME](_shared-rep-homepage.md) |
| **SSOT 시나리오** | `docs/scenarios/hom.md` |
| **manifest** | `app/systems/hom/manifest.yaml` |
| **display_order** | 10 |
| **URL** | `https://www.hwgeneralins.com` |
| **execution_profile** | `heavy` |

## 1. 실행 스택

```text
manifest → hom/executor.py → RepHomepageExecutor(PC_CHANNEL)
  → ScenarioEngine(build_rep_homepage_engine)
  → page_objects/hom/* + flows/rep_homepage/*
```

## 2. 인증

| auth_method | API | OTP pause | 비고 |
| --- | --- | --- | --- |
| `phone` | ✅ | ✅ `hom.login` | SMS OTP |
| `kakao` | ✅ | ❌ | 30s×최대3회, REP-HOME §4 |
| `finance_certificate` | ❌ 400 | — | UI placeholder |
| `public_certificate` | ❌ 400 | — | UI placeholder |

## 3. Manifest SSOT (모듈 메타·입력 필드)

모듈 순서·`depends_on`·timeout·`requires_user_input`·`run_form` 필드는 **manifest가 단일 진실원천**이다.

| 문서 | 역할 |
| --- | --- |
| `app/systems/hom/manifest.yaml` | module_id·run_form·retry·execution_profile |
| `docs/scenarios/hom.md` | 운영 시나리오·스크린샷 맥락 |
| 본 Spec | 행동 AC·Gherkin만 |

`python3 scripts/check_docs_consistency.py`가 manifest↔시나리오↔본 Spec의 `module_id` 존재를 검증한다.

**모듈 ID (manifest SSOT — timeout/retry/depends_on은 manifest 참조):**

`hom.main.access`, `hom.login`, `hom.contract.list`, `hom.contract.detail`, `hom.compensation.charge`, `hom.compensation.result`, `hom.compensation.cancel`, `hom.proof.long_term_policy`, `hom.marketing.consent.apply`, `hom.marketing.consent.withdraw`

## 4. 모듈별 AC

### hom.main.access

```gherkin
Given browser_mode from run_form
When MainAccessFlow runs
Then navigate https://www.hwgeneralins.com
And close/dismiss initial popups
And module status=PASSED
And artifact final.png captured
```

**실패:** 메인 미로드 → ANOMALY(`RuntimeError`); 네트워크/타임아웃 → ERROR(재시도 1회)

### hom.login

```gherkin
Scenario: phone OTP
  Given auth_method=phone and hom.main.access PASSED
  When LoginFlow requests SMS
  Then Run=WAITING_INPUT and module=WAITING_INPUT
  When POST /api/runs/{id}/otp with valid code
  Then login completes PASSED

Scenario: kakao
  Given auth_method=kakao
  When KakaoLoginFlow completes within retry policy
  Then PASSED without WAITING_INPUT
```

**실패:** 인증 실패 alert → ANOMALY; 셀렉터 깨짐 → ERROR/healing

### hom.contract.list

```gherkin
Given hom.login PASSED
When ContractListFlow runs
Then MY한화 GNB → 개인계약 조회
And contract list count > 0 verified
Then PASSED
```

### hom.contract.detail

```gherkin
Given hom.contract.list PASSED
When ContractDetailFlow runs
Then click first selectable contract
And verify detail info region visible
Then PASSED
```

### hom.compensation.charge

```gherkin
Given hom.login PASSED
When CompensationChargeFlow runs
Then 보상 GNB → 신규접수 → 정보입력(CLAIM_CONTENT_TEXT) → 서류등록
And reach charge06 completion screen
Then PASSED
```

**결합:** `CLAIM_CONTENT_TEXT` = `SPEC-SYS-REP-HOME` §3

### hom.compensation.result

```gherkin
Given hom.compensation.charge PASSED
When CompensationResultFlow runs
Then find today's claim by TARGET_CLAIM_TEXT (or TRUNCATED)
And verify detail and submitted documents
Then PASSED
```

**전제:** charge가 동일 Run에서 선행 완료 (depends_on)

### hom.compensation.cancel

```gherkin
Given hom.compensation.charge PASSED
When CompensationCancelFlow runs
Then cancel in-progress claim
And absent from 진행중 tab
And visible as cancelled in 완료 tab
Then PASSED
```

**참고:** result와 병렬 depends (둘 다 charge 의존). result 후 cancel 불필요.

### hom.proof.long_term_policy

```gherkin
Given hom.login PASSED
When LongTermPolicyCertificateFlow runs
Then 증명서 발급 → 장기보험증권
And download first contract as PDF
Then PASSED
```

### hom.marketing.consent.apply / withdraw

```gherkin
Scenario: apply
  Given hom.login PASSED
  When MarketingConsentApplyFlow runs
  Then MY한화 → 마케팅활용동의신청/철회 → 동의 상태
  Then PASSED

Scenario: withdraw
  Given hom.marketing.consent.apply PASSED
  When MarketingConsentWithdrawFlow runs
  Then change to 미동의
  Then PASSED
```

## 5. 의존성 그래프

```text
main.access → login ─┬→ contract.list → contract.detail
                     ├→ compensation.charge ─┬→ result
                     │                        └→ cancel
                     ├→ proof.long_term_policy
                     └→ marketing.apply → marketing.withdraw
```

## 6. Suite·스케줄·프리셋

- Suite `display_order` 10 — HOM 선행 시스템
- Schedule: `POST /api/schedules/systems/hom`
- Preset: system_code=`hom`, `validate_run_request` 동일 검증

## 7. 변경 동기화

`manifest.yaml` ↔ 본 Spec ↔ `docs/scenarios/hom.md` — `python3 scripts/check_docs_consistency.py`가 manifest↔시나리오·manifest↔본 Spec의 `module_id` 존재를 기계 검증한다. 행동 AC·Gherkin은 수동/리뷰로 유지한다.
