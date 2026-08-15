# FP (영업가족 위촉서류 등록 PC)

아키텍처: [E2E_ARCHITECTURE.md](../E2E_ARCHITECTURE.md). 구현: `app/automation/page_objects/fp/`, `app/systems/fp/executor.py`.

## 개요

| 항목 | 값 |
| --- | --- |
| 코드 | `fp` |
| URL | `https://fp.hwgeneralins.com` |
| manifest | `app/systems/fp/manifest.yaml` |
| 인증 | `phone` 만. OTP 는 Run 화면에서 입력 |

## 모듈

1. `fp.main.access` — 메인 접속 (`access_common`)
2. `fp.identity.verification` → `fp.main.access` — 본인인증(nfilter 주민번호·SMS OTP)
3. `fp.document.writing` → `fp.identity.verification` — OZ 양식 서명·재인증 OTP

타임아웃: 접속 120초, 본인인증 300초, 서류작성 420초.

## 흐름

```text
메인 접속 → sales01 본인인증(OTP) → sales02 OZ 서명 → sales03 완료(OTP)
```

## 입력

브라우저 모드, 이름, 주민등록번호, 통신사, 휴대폰 번호.
