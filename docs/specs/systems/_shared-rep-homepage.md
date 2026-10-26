# SPEC-SYS-REP-HOME: 대표홈페이지 공통 (HOM·MHM)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SYS-REP-HOME` |
| **상태** | `approved` |
| **적용** | `SPEC-SYS-HOM`, `SPEC-SYS-MHM` |
| **구현** | `app/scenarios/rep_homepage/`, `app/automation/flows/rep_homepage/`, `app/automation/scenarios/rep_homepage/constants.py` |

## 1. 채널 아키텍처

| 구성 | HOM (PC) | MHM (모바일) |
| --- | --- | --- |
| Executor | `RepHomepageExecutor` | 동일 |
| Channel | `PC_CHANNEL` (`hom/channel.py`) | `MOBILE_CHANNEL` (`mhm/channel.py`) |
| PageObject | `page_objects/hom/` | `page_objects/mhm/` |
| Flow | `flows/rep_homepage/` (공유) | 동일 |
| workflow_name | `hom_login` | `mhm_login` |
| 모바일 모드 | 불필요 | `apply_mobile_device_mode()` 필수 |

## 2. workflow_step ↔ Flow 매핑

| workflow_step | Flow 클래스 | module_id suffix |
| --- | --- | --- |
| `main_access` | `MainAccessFlow` | `*.main.access` |
| `login` | `LoginFlow` | `*.login` |
| `contract_list` | `ContractListFlow` | `*.contract.list` |
| `contract_detail` | `ContractDetailFlow` | `*.contract.detail` |
| `compensation_charge` | `CompensationChargeFlow` | `*.compensation.charge` |
| `compensation_result` | `CompensationResultFlow` | `*.compensation.result` |
| `compensation_cancel` | `CompensationCancelFlow` | `*.compensation.cancel` |
| `long_term_policy_certificate` | `LongTermPolicyCertificateFlow` | `*.proof.long_term_policy` |
| `marketing_consent_apply` | `MarketingConsentApplyFlow` | `*.marketing.consent.apply` (HOM only) |
| `marketing_consent_withdraw` | `MarketingConsentWithdrawFlow` | `*.marketing.consent.withdraw` (HOM only) |

## 3. 도메인 상수 (`app/automation/scenarios/rep_homepage/constants.py`)

| 상수 | 값·용도 |
| --- | --- |
| `CLAIM_CONTENT_TEXT` | `"IT직원 테스트입니다. 바로 취소할 예정입니다."` — charge 입력 본문 |
| `TARGET_CLAIM_TEXT` | 결과·취소 단계 청구 식별 (전체 일치) |
| `TARGET_CLAIM_TEXT_TRUNCATED` | `"IT직원 테스트입니다. 바로 취소할"` — 목록 부분 일치 |
| `KAKAO_AUTH_BACKGROUND_WAIT_MS` | 30_000 — 카카오 대기 |
| `KAKAO_AUTH_MAX_ATTEMPTS` | 3 — 카카오 미완료 재시도 |
| `KAKAO_AUTH_INCOMPLETE_DIALOG_MARKERS` | 미완료 alert 문구 패턴 |
| `is_kakao_auth_incomplete_message()` | alert 판별 헬퍼 |

**규칙:** charge → result/cancel은 동일 `CLAIM_CONTENT_TEXT`로 결합. 채널별 step에 상수 중복 정의 금지.

## 4. LoginFlow 동작

### phone

1. `login_move` — 로그인 화면 이동
2. `phone_login.request_sms` — SMS 요청
3. `otp_code` 없으면 → `StepNeedsInput` → Run `WAITING_INPUT`
4. resume 후 `phone_login.submit_otp_and_login`

### kakao

1. `login_move`
2. `kakao_login.run` — 30초 대기·인증완료 클릭
3. 미완료 alert → 최대 3회 재시도 (`is_kakao_auth_incomplete_message`)
4. **OTP pause 없음** (`StepNeedsInput` 반환 안 함)

## 5. 종료 분류 (공통)

| 예외 유형 | Module status | 의미 |
| --- | --- | --- |
| `RuntimeError` (사이트 검증 실패) | ANOMALY | 실제 사이트 이상 |
| Playwright timeout·셀렉터 미매칭 등 | ERROR 또는 healing 후 재시도 | 도구/셀렉터 이슈 |
| `RejectUnexpectedInput` | ERROR | 정책 위반 pause |

## 6. 공유 세션

- Run 내 단일 `RepHomepageRuntime` + browser context
- OTP pause 후 in-process 세션 유지
- `phone_login_sms_requested` 플래그 — resume 시 SMS 재요청 방지

## 7. 부분 선택·의존성

- `selected_module_ids`로 모듈 부분 실행
- 미선택 → `SKIPPED`
- `depends_on` 미충족 선택 → API `400`
- 선행 모듈 실패(PASSED 아님) → 후속 `BLOCKED`

## 8. 셀렉터 규칙 (page object)

- 사이트에 중복 id·숨김 사본이 있다 → `.first` 대신 `:visible`
- 체크박스에 JS 이중클릭 헬퍼(`_click_label_in_modal` 등) 금지 — 토글 상쇄. Playwright 실클릭 후 `is_checked()` 검증
