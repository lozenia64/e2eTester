# HRP (현장출동 홈페이지 PC)

아키텍처: [E2E_ARCHITECTURE.md](../E2E_ARCHITECTURE.md). 구현: `app/automation/page_objects/hrp/`, `app/systems/hrp/executor.py`.

## 개요

| 항목 | 값 |
| --- | --- |
| 코드 | `hrp` |
| URL | `https://www.eagleprm.co.kr` |
| manifest | `app/systems/hrp/manifest.yaml` |
| 인증 | `phone` — 대시보드 아이디·비밀번호 + SMS OTP(iframe) |

## 모듈

1. `hrp.main.access`
2. `hrp.login` → `hrp.main.access`
3. `hrp.salvage.bid.inquiry.list` → `hrp.login`
4. `hrp.salvage.bid.inquiry.detail` → `hrp.salvage.bid.inquiry.list`

타임아웃: 접속 120초, 그 외 180초.

## 흐름

```text
접속 → 로그인(OTP) → 잔존물 입찰 목록 → 상세
```

목록·상세는 iframe `workArea_hrpF020` / `workArea_hrpF021`.

## 입력

브라우저 모드, 아이디, 비밀번호.
