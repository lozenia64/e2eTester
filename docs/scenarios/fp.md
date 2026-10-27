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
3. `fp.document.writing` → `fp.identity.verification` — TM 관리자 확인(해당 시)·OZ 양식 서명·재인증 OTP

타임아웃: 접속 120초, 본인인증 300초, 서류작성 420초.

## 흐름

```text
메인 접속 → sales01 본인인증(OTP) → sales02 또는 sales02_tm1 → TM 관리자 확인(해당 시) → OZ 서명 → sales03 또는 sales03_tm1 완료(OTP)
```

## 입력

브라우저 모드, 이름, 주민등록번호, 통신사, 휴대폰 번호, 관리자사번(`manager_employee_id`).

관리자사번은 입력 프리셋에 저장할 수 있다. 일반 계약서 화면(`sales02.do`)에서는 생략 가능하며,
TM 계약서 화면(`sales02_tm1.do`)에서는 관리자사번 7자리 숫자를 입력하고 확인을 마쳐야 양식보기를 진행한다.
두 계약서 경로 모두 본인인증 성공으로 처리하며 도착한 경로를 유지한다.
서약서 완료 상태는 `작성완료` 또는 `제출완료`를 인정한다.
최종 완료 경로는 `sales03.do`, `sales03_tm1.do` 모두 성공으로 인정한다.
완료 화면 대기 시간 초과 시 기대 경로와 현재 URL을 보고하며, 이전 인증 안내를 실패 사유로 사용하지 않는다.
제출 이후 새로 발생한 실패 알림은 실패 사유로 유지한다.
