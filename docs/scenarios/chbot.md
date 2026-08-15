# CHBOT (챗봇 모바일)

아키텍처: [E2E_ARCHITECTURE.md](../E2E_ARCHITECTURE.md). 구현: `app/automation/page_objects/chbot/`, `app/systems/chbot/executor.py`.

## 개요

| 항목 | 값 |
| --- | --- |
| 코드 | `chbot` |
| URL | `https://chbot.hwgeneralins.com/P29GCdKMTnbsy0PRr` |
| manifest | `app/systems/chbot/manifest.yaml` |
| 인증 | `phone`(OTP), `kakao`(카카오톡 승인·재시도 최대 3회, OTP 없음) |
| 필수 | 모바일 디바이스 모드 후 접속 |

## 모듈

1. `chbot.main.access`
2. `chbot.simple.auth` → `chbot.main.access`
3. `chbot.contract.list` → `chbot.simple.auth`

타임아웃: 접속·계약조회 120초, 본인인증 180초.

## 흐름

```text
접속 → 채팅 본인인증(휴대폰 OTP | 카카오) → 계약조회(계약자·정상)
```

카카오 대기·재시도: `app/automation/scenarios/rep_homepage/constants.py`.

## 입력

브라우저 모드, 인증 수단, 성명, 생년월일, 성별코드, (휴대폰 시) 통신사·휴대폰 번호.
