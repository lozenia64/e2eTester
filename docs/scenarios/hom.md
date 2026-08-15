# HOM (대표홈페이지 PC)

아키텍처: [E2E_ARCHITECTURE.md](../E2E_ARCHITECTURE.md). 셀렉터·단계 구현: `app/automation/page_objects/hom/`, `app/automation/flows/rep_homepage/`.

## 개요

| 항목 | 값 |
| --- | --- |
| 코드 | `hom` |
| URL | `https://www.hwgeneralins.com` |
| manifest | `app/systems/hom/manifest.yaml` |
| 인증 | `phone`(OTP 일시정지), `kakao`(30초 대기·최대 3회). 금융/공동인증서는 UI placeholder, API 거부 |

## 모듈 (`manifest` order)

1. `hom.main.access`
2. `hom.login` — 로그인 이동 + 본인인증 한 단계
3. `hom.contract.list` → `hom.login`
4. `hom.contract.detail` → `hom.contract.list`
5. `hom.compensation.charge` → `hom.login`
6. `hom.compensation.result` → `hom.compensation.charge`
7. `hom.compensation.cancel` → `hom.compensation.charge`
8. `hom.proof.long_term_policy` → `hom.login`
9. `hom.marketing.consent.apply` → `hom.login`
10. `hom.marketing.consent.withdraw` → `hom.marketing.consent.apply`

타임아웃: 로그인·보상 3단계 300초, 그 외 180초. 미선택 모듈은 `SKIPPED`.

## 흐름

```text
접속 → 로그인(휴대폰 OTP | 카카오) → [계약조회 | 보험금청구(접수→결과→취소) | 장기증권 | 마케팅동의(신청→철회)]
```

청구 테스트 문구 SSOT: `app/automation/scenarios/rep_homepage/constants.py` (`CLAIM_CONTENT_TEXT` 등).

## 입력 (`run_form`)

브라우저 모드, 인증 수단, 고객명, 생년월일, (휴대폰 시) 성별·내외국인·통신사·휴대폰 번호. `show_when` 으로 인증 수단별 노출. 모듈은 `selected_module_ids` 로 부분 선택(의존성 위반 시 400).
