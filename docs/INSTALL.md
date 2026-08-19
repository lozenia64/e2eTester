# 설치와 운영

> SSOT: 설치·실행·환경변수. 사용법: [README.md](../README.md). 아키텍처: [E2E_ARCHITECTURE.md](E2E_ARCHITECTURE.md).

## 빠른 시작

**준비:** Python 3.13+, Node 22+, Git, Redis.

```bash
git clone https://github.com/lozenia64/e2eTester.git && cd e2eTester
python3 -m venv .venv && .venv\Scripts\activate   # Windows
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
npm ci && npm run build   # 프론트엔드 자산 빌드 (필수)
cp .env.example .env   # 관리자·JWT 변경
python3 scripts/run_local.py
```

http://127.0.0.1:2222 — `.env` 의 `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` 로 로그인.

## 프론트엔드 빌드

화면의 CSS·JS·폰트는 Vite 가 `app/web/static/dist/` 로 빌드하고, Jinja 템플릿이
`app/web/static/dist/.vite/manifest.json` 을 읽어 해시 파일명을 해석합니다.
**빌드 산출물은 커밋되지 않으므로**, 새로 클론한 뒤 `npm run build` 를 건너뛰면
manifest 가 없어 모든 페이지가 500 으로 떨어집니다(`ManifestMissingError`).

```bash
npm ci          # 의존성 설치 (package-lock.json 기준)
npm run build   # app/web/static/dist/ 생성
npm run dev     # 개발 중 파일 변경 감시 재빌드 (선택)
```

프론트 소스를 고친 뒤에는 다시 `npm run build` 를 실행합니다. 서버 재시작은
필요 없습니다 — manifest 의 mtime 이 바뀌면 자동으로 다시 읽습니다.

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
- 자동 복구 루프: `E2E_AUTO_RERUN_ENABLED`(기본 `false`) — 예약 Run 이 `ERROR` 로 끝나면 실패 모듈부터 1회 자동 재실행. `E2E_RECOVERY_TIER2_BUDGET`(기본 `2`) — Run 당 세션 재개설(tier 2) 허용 횟수, 넘으면 한 단계 낮춘 등급으로 재시도(현재 tier 2 는 런타임 재구축까지만 하고 로그인 모듈을 다시 주행하지 않는다 — `docs/E2E_ARCHITECTURE.md` 의 'tier 2 현행 한계' 참고). `E2E_RUN_MAX_DURATION_S`(기본 무제한) — Run 총 실행 시간 상한(초), 넘으면 재시도를 중단

## 환경변수 (요약)

| 변수 | 용도 |
| --- | --- |
| `E2E_JWT_SECRET` | JWT 서명 |
| `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` | 시드 관리자 |
| `E2E_DB_PATH` / `E2E_SQLITE_BUSY_TIMEOUT_MS` | SQLite |
| `E2E_SCHEDULE_TZ` | cron·일간 대시보드 TZ |
| `E2E_RUN_RETENTION_ENABLED` / `E2E_RUN_RETENTION_CRON` | 실패 Run 자동 삭제 |
| `E2E_AUTO_RERUN_ENABLED` / `E2E_RUN_MAX_DURATION_S` / `E2E_RECOVERY_TIER2_BUDGET` | 자동 복구 루프(예약 Run 자동 재실행·실행 시간 상한·로그인 재주행 예산) |
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
