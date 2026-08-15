# SPEC-INT-001: SMS OTP 중계

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-INT-001` |
| **상태** | `approved` |
| **SSOT** | `docs/otp_relay.md` |
| **구현** | `routes_otp.py` |

## 1. 개요

안드로이드 SMS 리레이가 수신 OTP를 API로 전달.

## 2. API

`POST /api/otp/inbound`

**Headers:** 인증 토큰 (env 설정, `docs/INSTALL.md` 참조)

**Body:** SMS payload (phone, message, etc.)

## 3. FR-001: 라우팅

`RunService.submit_otp_to_waiting`:
- `WAITING_INPUT` + live pending runs 검색
- OTP 코드 추출·매칭
- 최신 `paused_at` run에 submit

## 4. 수용 기준

### AC-001: 대기 Run 없음

```gherkin
Given no WAITING_INPUT runs
When inbound OTP
Then appropriate no-op or error (no wrong run OTP)
```

## 5. 수동 검증

실제 Android relay + live site
