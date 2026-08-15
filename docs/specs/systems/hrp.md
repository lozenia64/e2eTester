# SPEC-SYS-HRP: 현장출동 홈페이지(PC)

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SYS-HRP` |
| **상태** | `approved` |
| **SSOT** | `docs/scenarios/hrp.md` |
| **manifest** | `app/systems/hrp/manifest.yaml` |
| **display_order** | 30 |
| **URL** | `https://www.eagleprm.co.kr` |
| **execution_profile** | `interactive` |
| **구현** | `HrpWorkflowExecutor`, `flows/hrp/`, `page_objects/hrp/` |

## 1. 인증

ID/PW 로그인 + SMS OTP (iframe 내 입력). `supported_auth_methods: [phone]` — OTP는 로그인 모듈에서 처리.

## 2. Manifest SSOT

`app/systems/hrp/manifest.yaml` · `docs/scenarios/hrp.md` — module_id·run_form SSOT. 본 Spec은 AC·iframe 맥락만.

**모듈 ID:** `hrp.main.access`, `hrp.login`, `hrp.salvage.bid.inquiry.list`, `hrp.salvage.bid.inquiry.detail`

## 3. iframe 컨텍스트

| 모듈 | iframe name | 용도 |
| --- | --- | --- |
| list | `workArea_hrpF020` | 잔존물 입찰 목록 |
| detail | `workArea_hrpF021` | 잔존물 입찰 상세 |

PageObject가 frame 전환 책임.

## 4. 모듈별 AC

### hrp.main.access

```gherkin
When main_access runs
Then navigate www.eagleprm.co.kr
And dismiss popups
Then PASSED
```

### hrp.login

```gherkin
Given credentials from run_form
When login step runs
Then submit user_id + password
And trigger SMS OTP (iframe)
Then Run=WAITING_INPUT
When OTP submitted
Then login session established
Then PASSED
```

**실패:** ID/PW 오류 → ANOMALY; iframe 로드 실패 → ERROR

### hrp.salvage.bid.inquiry.list

```gherkin
Given hrp.login PASSED
When salvage_bid_inquiry_list runs
Then enter 잔존물 입찰조회 menu
And in workArea_hrpF020 verify list (총 N건, 순번 1 exists)
Then PASSED
```

### hrp.salvage.bid.inquiry.detail

```gherkin
Given list PASSED
When salvage_bid_inquiry_detail runs
Then click 순번 1 접수번호 in F020
And in workArea_hrpF021 verify 상세 정보
Then PASSED
```

## 5. 의존성

```text
main.access → login → list → detail
```

## 6. 변경 동기화

`manifest.yaml` ↔ 본 Spec ↔ `docs/scenarios/hrp.md`
