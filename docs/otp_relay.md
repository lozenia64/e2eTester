# OTP SMS 자동입력

휴대폰 인증 Run 이 `WAITING_INPUT` 일 때 SMS 를 서버로 보내 자동 재개합니다. 서버 env: [INSTALL.md](INSTALL.md) (`E2E_OTP_RELAY_*`).

## 엔드포인트

```http
POST /api/otp/inbound
X-OTP-Relay-Token: <E2E_OTP_RELAY_TOKEN>
Content-Type: application/json

{"code": "123456"}
또는 {"text": "…인증번호 123456…"}
```

- 대기 중 Run 을 자동 탐색(run_id 불필요). OTP 는 저장하지 않음.
- 무인 점검 권장: `E2E_RUN_CONCURRENCY=1`

| HTTP | 의미 |
| --- | --- |
| 200 | 주입·재개 성공 |
| 400 | OTP 추출 실패 |
| 401 | 토큰 불일치 |
| 404 | 대기 Run 없음(무시 가능) |
| 503 | `E2E_OTP_RELAY_TOKEN` 미설정 |

카카오 인증은 자동화 불가.

## 중계기 구성

**빠른 검증:** SMS 포워더 앱(MacroDroid 등)으로 `POST http://<서버>:2222/api/otp/inbound`, 본문 `{"text":"{{sms_body}}"}`.

**운영:** 커스텀 Android 앱 — `RECEIVE_SMS`, 발신자 필터, 실패 시 짧은 재시도, TLS/VPN 권장.

토큰 유출 시 임의 OTP 주입 가능 — 길고 무작위로 관리.
