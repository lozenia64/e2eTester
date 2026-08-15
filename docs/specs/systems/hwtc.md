# SPEC-SYS-HWTC: 연수원(PC)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SYS-HWTC` |
| **상태** | `approved` |
| **SSOT** | `docs/scenarios/hwtc.md` |
| **manifest** | `app/systems/hwtc/manifest.yaml` |
| **display_order** | 50 |
| **URL** | `https://sls.hwgeneralins.com` |
| **execution_profile** | `interactive` |
| **구현** | `HwtcWorkflowExecutor`, `flows/hwtc/`, `page_objects/hwtc/` |

## 1. 인증

HSP(한화스마트포털) 동일 ID/PW + SMS OTP **5자리**.

## 2. Manifest SSOT

`app/systems/hwtc/manifest.yaml` · `docs/scenarios/hwtc.md` — module_id·run_form SSOT. 본 Spec은 AC만.

**모듈 ID:** `hwtc.main.access`, `hwtc.phone.auth`, `hwtc.video.playback`

## 3. 모듈별 AC

### hwtc.main.access

```gherkin
When main_access runs
Then navigate sls.hwgeneralins.com
And dismiss popups
Then PASSED
```

### hwtc.phone.auth

```gherkin
Given user_id, password from run_form
When phone_auth runs
Then login form submit
And request 5-digit SMS OTP
Then Run=WAITING_INPUT
When OTP submitted
Then login complete
And dismiss "30일 미로그인" popup if present
Then PASSED
```

### hwtc.video.playback

```gherkin
Given hwtc.phone.auth PASSED
When video_playback runs
Then navigate IT교육과정
And open first education video
And Video.js player plays
And verify playback for 30 seconds (time progression)
Then PASSED
```

**실패:** 재생 안 됨·정지 상태 → ANOMALY; player 셀렉터 실패 → ERROR/healing

## 4. 의존성

```text
main.access → phone.auth → video.playback
```

## 5. 변경 동기화

`manifest.yaml` ↔ 본 Spec ↔ `docs/scenarios/hwtc.md`
