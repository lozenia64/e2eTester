# SPEC-SYS-CHBOT: 챗봇(모바일)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SYS-CHBOT` |
| **상태** | `approved` |
| **SSOT** | `docs/scenarios/chbot.md` |
| **manifest** | `app/systems/chbot/manifest.yaml` |
| **display_order** | 60 |
| **URL** | `https://chbot.hwgeneralins.com/P29GCdKMTnbsy0PRr` |
| **execution_profile** | `interactive` |
| **구현** | `ChbotWorkflowExecutor`, `flows/chbot/`, `page_objects/chbot/` |

## 1. 실행 스택

```text
manifest → chbot/executor.py → AccessWorkflowExecutor subclass
  → ChbotSimpleAuthFlow / ChbotContractListFlow
  → mobile device mode 필수
```

## 2. 인증

| auth_method | OTP pause | 비고 |
| --- | --- | --- |
| `phone` | ✅ `chbot.simple.auth` | 채팅 UI 본인인증 |
| `kakao` | ❌ | `kakao_auth.run`, REP-HOME 카카오 상수 재사용 가능 |

## 3. Manifest SSOT

`app/systems/chbot/manifest.yaml` · `docs/scenarios/chbot.md` — module_id·run_form·`gender_code` 옵션 SSOT. 본 Spec은 AC만.

**모듈 ID:** `chbot.main.access`, `chbot.simple.auth`, `chbot.contract.list`

## 4. ChbotSimpleAuthFlow

### phone

```gherkin
Given name, birthdate, gender_code, carrier, phone_number
When simple_auth first pass
Then enter contract inquiry path in chat UI
And 본인 정보 확인 + request_otp
Then WAITING_INPUT
When OTP submitted
Then submit_otp_and_verify → PASSED
```

**런타임:** `simple_auth_sms_requested`

### kakao

```gherkin
Given auth_method=kakao and phone_number required
When kakao_auth.run
Then Kakao approval flow (no StepNeedsInput)
Then PASSED
```

**검증 실패:** 필수 필드 누락 → `RuntimeError` → ANOMALY

## 5. chbot.contract.list — ChbotContractListFlow

```gherkin
Given chbot.simple.auth PASSED
When contract_list runs
Then select contract inquiry criteria and status
And verify normal contract list with total count > 0
Then PASSED
```

## 6. 모바일 AC

```gherkin
Given chbot Run
When runtime built
Then apply_mobile_device_mode() before navigation
```

## 7. 의존성

```text
main.access → simple.auth → contract.list
```

## 8. 변경 동기화

`manifest.yaml` ↔ 본 Spec ↔ `docs/scenarios/chbot.md`
