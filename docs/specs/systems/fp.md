# SPEC-SYS-FP: 영업가족 위촉서류 등록(PC)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SYS-FP` |
| **상태** | `approved` |
| **SSOT** | `docs/scenarios/fp.md` |
| **manifest** | `app/systems/fp/manifest.yaml` |
| **display_order** | 40 |
| **URL** | `https://fp.hwgeneralins.com` |
| **execution_profile** | `interactive` |
| **구현** | `FpWorkflowExecutor`, `flows/fp/`, `page_objects/fp/`, `access_common/` |

## 1. 실행 스택

```text
manifest → fp/executor.py → AccessWorkflowExecutor subclass
  → workflow_name: fp_access
  → FpIdentityVerificationFlow / FpDocumentWritingFlow
```

## 2. 인증

| method | 지원 | OTP 횟수 |
| --- | --- | --- |
| `phone` | ✅ only | 2회 (본인인증 + 서류작성) |

## 3. Manifest SSOT

`app/systems/fp/manifest.yaml` · `docs/scenarios/fp.md` — module_id·run_form·timeout SSOT. 본 Spec은 AC만.

**모듈 ID:** `fp.main.access`, `fp.identity.verification`, `fp.document.writing`

## 4. 화면 흐름 (sales01→03)

```text
메인 접속 → sales01 본인인증(OTP) → sales02 또는 sales02_tm1 → TM 관리자 확인(해당 시) → OZ 전자서명 → sales03 또는 sales03_tm1 작성완료(OTP)
```

## 5. 모듈별 AC

### fp.main.access

```gherkin
When main_access step runs
Then navigate fp.hwgeneralins.com
And dismiss initial popups
Then PASSED
```

### fp.identity.verification — FpIdentityVerificationFlow

```gherkin
Given fp.main.access PASSED
When identity_verification runs first pass
Then navigate sales01 본인확인
And input name, nfilter SSN, carrier, phone
And request SMS OTP
Then Run=WAITING_INPUT (requires_user_input=true)
When OTP submitted via API
Then submit_otp_and_complete → 계약서 체결하기까지
Then PASSED
```

**런타임:** `phone_auth_sms_requested` — resume 시 SMS 재요청 방지

계약서 작성 화면은 `sales02.do`와 `sales02_tm1.do` 모두 성공으로 인정한다.

**실패:** 주민번호·OTP 오류 alert → ANOMALY; nfilter 타임아웃 → ERROR

### fp.document.writing — FpDocumentWritingFlow

```gherkin
Given fp.identity.verification PASSED
When document_writing runs
Then preserve the arrived contract page (sales02.do or sales02_tm1.do)
When the page is sales02_tm1.do
Then verify the seven-digit manager_employee_id from the input preset before opening forms
Then OZ 양식(정보보호서약서) 전자서명 진행
And accept 작성완료 or 제출완료 as the form completion status
And request 재인증 SMS (runtime.otp_code cleared)
Then WAITING_INPUT (2차 OTP)
When OTP submitted
Then sales03.do 또는 sales03_tm1.do 작성완료 화면
Then PASSED
```

완료 화면 대기는 두 경로를 모두 인정한다. 대기 시간 초과 시 제출 이후 발생한 실패 알림이 있으면
해당 알림을 보고하고, 그렇지 않으면 대기 제한·기대 경로·현재 URL을 보고한다.
제출 이전 알림이나 정상 인증 안내를 실패 원인으로 대체하지 않는다.

**런타임:** `document_sms_requested`; 2차 OTP 전 `otp_code=""` 리셋

관리자사번은 manifest의 선택 입력으로 프리셋에 저장한다. 일반 경로에서는 필요하지 않으며,
TM 경로에서 누락·형식 오류·관리자 확인 실패 시 양식 제출 전에 오류로 종료한다.

## 6. OTP 정책

| pause 지점 | module | resume |
| --- | --- | --- |
| 1차 | fp.identity.verification | 동일 모듈 OTP 제출 후 완료 |
| 2차 | fp.document.writing | 동일 모듈 OTP 제출 후 완료 |

Suite OTP: `awaiting_input_run_id` → `POST /api/suites/{id}/otp`

## 7. 부분 선택

3모듈 전체 선택이 일반적. login 계열 partial_rerun=false — 실패 시 전체 rerun 권장.

## 8. 변경 동기화

`manifest.yaml` ↔ 본 Spec ↔ `docs/scenarios/fp.md`
