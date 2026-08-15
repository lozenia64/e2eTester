# MHM (대표홈페이지 모바일)

아키텍처: [E2E_ARCHITECTURE.md](../E2E_ARCHITECTURE.md). 셀렉터·단계 구현: `app/automation/page_objects/mhm/`, `app/automation/flows/rep_homepage/`.

## 개요

| 항목 | 값 |
| --- | --- |
| 코드 | `mhm` |
| URL | `https://m.hwgeneralins.com` |
| manifest | `app/systems/mhm/manifest.yaml` |
| 인증 | `phone`, `kakao` (HOM 과 동일 정책) |
| 필수 | Chrome 기동 후 **모바일 디바이스 모드** 적용 → 접속 (`apply_mobile_device_mode`) |

## 모듈 (`manifest` order)

1. `mhm.main.access`
2. `mhm.login`
3. `mhm.contract.list` → `mhm.login`
4. `mhm.contract.detail` → `mhm.contract.list`
5. `mhm.compensation.charge` → `mhm.login`
6. `mhm.compensation.result` → `mhm.compensation.charge`
7. `mhm.compensation.cancel` → `mhm.compensation.charge`
8. `mhm.proof.long_term_policy` → `mhm.login`

타임아웃: 로그인·보상 3단계 300초, 그 외 180초.

## 흐름

```text
접속(모바일) → 로그인 → [계약조회 | 보험금청구(접수→결과→취소) | 장기증권]
```

청구 문구·상수: `app/automation/scenarios/rep_homepage/constants.py`.

## 입력

HOM 과 동일 필드·`show_when` 규칙. 8개 모듈 부분 선택 가능.
