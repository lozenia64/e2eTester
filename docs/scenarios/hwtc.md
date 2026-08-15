# HWTC (연수원 PC)

아키텍처: [E2E_ARCHITECTURE.md](../E2E_ARCHITECTURE.md). 구현: `app/automation/page_objects/hwtc/`, `app/systems/hwtc/executor.py`.

## 개요

| 항목 | 값 |
| --- | --- |
| 코드 | `hwtc` |
| URL | `https://sls.hwgeneralins.com` |
| manifest | `app/systems/hwtc/manifest.yaml` |
| 인증 | `phone` — ID/PW + SMS OTP(5자리) |

## 모듈

1. `hwtc.main.access`
2. `hwtc.phone.auth` → `hwtc.main.access`
3. `hwtc.video.playback` → `hwtc.phone.auth`

타임아웃: 접속 120초, 그 외 180초.

## 흐름

```text
접속 → 로그인(OTP, 30일 미로그인 팝업 가능) → IT교육과정 → Video.js 재생 30초 검증
```

## 입력

브라우저 모드, 아이디, 비밀번호.
