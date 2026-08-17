# 설치와 운영

> SSOT: 설치·실행·환경변수. 사용법: [README.md](../README.md). 아키텍처: [E2E_ARCHITECTURE.md](E2E_ARCHITECTURE.md).

## 빠른 시작

**준비:** Python 3.13+, Git, Redis.

```bash
git clone https://github.com/lozenia64/e2eTester.git && cd e2eTester
python3 -m venv .venv && .venv\Scripts\activate   # Windows
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
cp .env.example .env   # 관리자·JWT 변경
python3 scripts/run_local.py
```

http://127.0.0.1:2222 — `.env` 의 `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` 로 로그인.

## 실행 구조

API·워커·Redis 가 함께 떠야 실제 점검이 동작합니다. `run_local.py` 가 세 프로세스를 기동·종료합니다(`E2E_EXECUTION_MODE=remote`).

- Redis: `E2E_REDIS_URL` (기본 로컬). 데이터: `data/`, `redis-data/`
- 워커: `http://127.0.0.1:8100` (`E2E_WORKER_BASE_URL`)
- Chrome 프로필: HOM·FP·HRP → `E2E_USER_DATA_DIR`; MHM·HWTC·CHBOT → `E2E_PLAYWRIGHT_MCP_PROFILE_DIR`

## 운영

- DB: `E2E_DB_PATH` (기본 `data/e2etester.db`)
- 아티팩트: `artifacts/{run_id}/{module_id}/`
- 동시 실행: `E2E_RUN_CONCURRENCY_HEAVY`(2), `E2E_RUN_CONCURRENCY_LIGHT`(4), `E2E_RUN_CONCURRENCY_INTERACTIVE`(2)
- 재기동 시 진행 중 Run 은 `CANCELLED`(체크포인트 있으면 복구 가능)
- ERROR·CANCELLED Run 자동 삭제: `E2E_RUN_RETENTION_CRON` (기본 `0 3 * * *`, `E2E_SCHEDULE_TZ`)

## 환경변수 (요약)

| 변수 | 용도 |
| --- | --- |
| `E2E_JWT_SECRET` | JWT 서명 |
| `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` | 시드 관리자 |
| `E2E_DB_PATH` / `E2E_SQLITE_BUSY_TIMEOUT_MS` | SQLite |
| `E2E_SCHEDULE_TZ` | cron·일간 대시보드 TZ |
| `E2E_RUN_RETENTION_ENABLED` / `E2E_RUN_RETENTION_CRON` | 실패 Run 자동 삭제 |
| `E2E_RUN_CONCURRENCY` / `E2E_RUN_CONCURRENCY_HEAVY` / `E2E_RUN_CONCURRENCY_LIGHT` / `E2E_RUN_CONCURRENCY_INTERACTIVE` | 동시 Run |
| `E2E_EXECUTION_MODE` / `E2E_REDIS_URL` / `E2E_WORKER_BASE_URL` / `E2E_WORKER_CONCURRENCY` / `E2E_SESSION_LEASE_TTL` | 워커·Redis |
| `E2E_LOG_LEVEL` / `E2E_LOG_FORMAT` | structlog |
| `E2E_USER_DATA_DIR` / `E2E_WORKSPACE_DIR` / `E2E_PLAYWRIGHT_MCP_PROFILE_DIR` | Chrome 프로필 |
| `E2E_FAILURE_ANALYZER_ENABLED` / `GEMINI_API_KEY` / `GEMINI_MODELS` / `E2E_GEMINI_SSL_VERIFY` | AI 분석 |
| `E2E_EMAIL_ENABLED` / `E2E_EMAIL_GMAIL_ACCOUNT` / `E2E_EMAIL_GMAIL_APP_PASSWORD` / `E2E_EMAIL_RECIPIENTS_{코드}` / `E2E_EMAIL_OPERATOR_RECIPIENTS` | 종료 메일 |
| `E2E_OTP_RELAY_TOKEN` / `E2E_OTP_RELAY_REGEX` | SMS OTP 중계 |

전체·예시값: `.env.example`.

## 선택 기능

- **AI 분석:** `E2E_FAILURE_ANALYZER_ENABLED=true`, `GEMINI_API_KEY`, `GEMINI_MODELS=gemini-3.5-flash|gemini-3.1-flash-lite|gemini-3-flash-preview|gemini-3.1-pro-preview`
- **종료 메일:** `E2E_EMAIL_ENABLED=true`, Gmail 앱 비밀번호. HTML 은 고정 템플릿, Gemini 는 JSON 콘텐츠만
- **OTP 중계:** `E2E_OTP_RELAY_TOKEN`, `E2E_OTP_RELAY_REGEX` — [otp_relay.md](otp_relay.md)
- **자가 치유:** 무인 실행 중 셀렉터 복구, `/self-healing` 에서 패치 승인

## 더 읽을 곳

[README.md](../README.md) · [E2E_ARCHITECTURE.md](E2E_ARCHITECTURE.md) · [CI.md](CI.md) · [AGENTS.md](../AGENTS.md)
