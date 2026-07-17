# 설치와 운영

> **문서 소유권(SSOT):** 이 문서는 **설치·실행 방법, 선택 기능(AI/메일/예약) 사용법, 환경변수 카탈로그**의 단일 진실원천입니다. 점검 도구를 쓰는 방법은 [README.md](../README.md), 플랫폼 아키텍처·API 목록은 [E2E_ARCHITECTURE.md](../E2E_ARCHITECTURE.md), 시스템별 시나리오는 `docs/scenarios/{code}.md`가 소유합니다. 문서 거버넌스 규칙은 [DOCS_GOVERNANCE.md](DOCS_GOVERNANCE.md)를 참고하세요.

사내 임직원이 로컬 PC에서 회사 웹사이트를 자동 점검하기 위한 내부용 E2E 테스터입니다. 웹 대시보드에서 점검을 시작·감시하고, 로그와 스크린샷을 확인합니다. 실행 이력은 SQLite에, 로그·스크린샷 파일은 `artifacts/`에 남습니다.

**대상:** Python·Git·Redis를 설치할 수 있는 사내 임직원.

---

## 빠른 시작

**준비:** Python 3.11 이상, Git, Redis(`redis-cli ping` → `PONG`).

```bash
git clone https://github.com/lozenia64/e2eTester.git
cd e2eTester

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium

cp .env.example .env               # 관리자 계정·JWT 비밀값 변경

python3 scripts/run_local.py       # Redis 미기동 시 자동 기동 (redis-server 필요)
```

브라우저에서 **http://127.0.0.1:2222** 로 접속합니다. `.env`의 `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD`로 로그인하세요. 다른 기기에서 보려면 `http://<PC IP>:2222`인데, 방화벽에서 TCP 2222를 열어야 할 수 있습니다.

---

## 설치 상세

### Redis

Redis가 없다면:

```bash
# Windows: winget install Redis.Redis
# macOS: brew install redis  → run_local.py 가 자동 기동하거나 python3 scripts/run_redis.py --daemonize yes
# Ubuntu: sudo apt-get install -y redis-server && sudo service redis-server start
```

로컬 데이터는 git에 안 올라갑니다. `data/`에 SQLite, `redis-data/`에 Redis 영속 파일이 생깁니다. Redis 주소를 바꾸려면 `.env`의 `E2E_REDIS_URL`을 수정하세요.

### 실행 옵션

`run_local.py` 옵션: `--no-start-redis`, `--api-port`, `--worker-port`. 워커 HTTP 기본 주소는 `http://127.0.0.1:8100`입니다.

브라우저는 로컬 Chrome 채널을 먼저 쓰고, 안 되면 Playwright Chromium으로 넘어갑니다. **HOM·FP·HRP**는 `~/.e2etester/*-chrome-profile`(`E2E_USER_DATA_DIR`)을 씁니다. **MHM·HWTC·CHBOT** 등은 `%LOCALAPPDATA%/ms-playwright-mcp/mcp-chrome-{workspace_hash}`(`E2E_PLAYWRIGHT_MCP_PROFILE_DIR`, `E2E_WORKSPACE_DIR`)입니다. 보안 프로그램과 맞추려고 확장 로드·로컬 네트워크 허용 설정이 들어가 있습니다.

---

## 실행 구조

웹/API와 Playwright 브라우저는 **서로 다른 프로세스**입니다. Redis로 세션과 실시간 알림을 나눠 쓰기 때문에, 실제 점검에는 API·워커·Redis가 함께 떠 있어야 합니다. `scripts/run_local.py`가 세 프로세스를 한꺼번에 띄우고 끌 때 같이 내립니다(`E2E_EXECUTION_MODE=remote`).

---

## 운영과 보존

Run·Suite 이력과 cron 예약은 SQLite(`E2E_DB_PATH`, 기본 `data/e2etester.db`)에 있습니다. 아티팩트는 `artifacts/{run_id}/{module_id}/` 아래 `execution.log`, `final.png`입니다. 동시 실행 상한은 `E2E_RUN_CONCURRENCY_HEAVY`(2), `LIGHT`(4), `INTERACTIVE`(2)이고, 레거시 `E2E_RUN_CONCURRENCY`(4)도 남아 있습니다. 서버를 재시작하면 진행 중이던 브라우저 세션은 사라지고 Run은 `CANCELLED`로 정리됩니다(체크포인트가 있으면 복구 가능). 점검실패·취소 Run은 `E2E_RUN_RETENTION_CRON`(기본 `0 3 * * *`, `E2E_SCHEDULE_TZ`)에 따라 자동 삭제됩니다.

로그인은 `GET /login` → `POST /auth/login`, 비밀번호 변경은 `GET /account/password`입니다. 관리자는 `/admin`(사용자·통계·운영 관측 `/admin/ops`)을 쓰고, 일반 사용자 계정은 `/admin/users`에서 만들며 시스템별 권한을 줍니다.

---

## 환경변수 카탈로그

터미널에 직접 넣은 환경 변수가 `.env`보다 우선합니다. 예시값은 `.env.example`을 보세요.

| 변수 | 용도 |
| --- | --- |
| `E2E_JWT_SECRET` | JWT 서명 비밀값 (운영 시 반드시 변경) |
| `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` | 최초 관리자 시드 계정 |
| `E2E_DB_PATH` | SQLite DB 경로 |
| `E2E_SQLITE_BUSY_TIMEOUT_MS` | SQLite 락 대기(ms, 기본 5000) |
| `E2E_SCHEDULE_TZ` | cron·일간 대시보드 기준 타임존 (기본 Asia/Seoul) |
| `E2E_RUN_RETENTION_ENABLED` / `E2E_RUN_RETENTION_CRON` | 점검실패·취소 Run 자동 삭제 |
| `E2E_RUN_CONCURRENCY` / `E2E_RUN_CONCURRENCY_HEAVY` / `E2E_RUN_CONCURRENCY_LIGHT` / `E2E_RUN_CONCURRENCY_INTERACTIVE` | 동시 Run 상한 |
| `E2E_EXECUTION_MODE` | `local` / `remote` |
| `E2E_REDIS_URL` | Redis 연결 URL |
| `E2E_WORKER_BASE_URL` / `E2E_WORKER_CONCURRENCY` / `E2E_SESSION_LEASE_TTL` | 워커 연동 |
| `E2E_REALTIME_FANOUT` | 다중 API WS fan-out |
| `E2E_LOG_LEVEL` / `E2E_LOG_FORMAT` | structlog 설정 |
| `E2E_USER_DATA_DIR` / `E2E_WORKSPACE_DIR` / `E2E_PLAYWRIGHT_MCP_PROFILE_DIR` | Chrome 프로필 경로 |
| `E2E_FAILURE_ANALYZER_ENABLED` / `GEMINI_API_KEY` / `GEMINI_MODELS` / `E2E_GEMINI_SSL_VERIFY` | 실패 AI 분석 |
| `E2E_EMAIL_ENABLED` / `E2E_EMAIL_GMAIL_ACCOUNT` / `E2E_EMAIL_GMAIL_APP_PASSWORD` | 종료 메일 |
| `E2E_EMAIL_RECIPIENTS_{시스템코드}` | 시스템별 수신자 (HOM·MHM·FP·HRP·HWTC·CHBOT) |
| `E2E_EMAIL_OPERATOR_RECIPIENTS` | 점검실패(ERROR) 운영자 수신자 |
| `E2E_OTP_RELAY_TOKEN` / `E2E_OTP_RELAY_REGEX` | SMS OTP 자동 중계 |

---

## 선택 기능

기본은 모두 꺼져 있습니다. 설정이 틀려도 앱은 뜨지만, 해당 기능만 동작하지 않을 수 있습니다.

**실패 원인 AI 분석** — `E2E_FAILURE_ANALYZER_ENABLED=true`, `GEMINI_API_KEY`, `GEMINI_MODELS=gemini-3.5-flash|gemini-3.1-flash-lite|gemini-3-flash-preview|gemini-3.1-pro-preview`, `E2E_GEMINI_SSL_VERIFY`.

**종료 메일** — `E2E_EMAIL_ENABLED=true`와 Gmail 계정·앱 비밀번호. 정상·이상징후는 `E2E_EMAIL_RECIPIENTS_{시스템코드}`, 점검실패는 `E2E_EMAIL_OPERATOR_RECIPIENTS`만 받습니다. SUITE가 끝나면 통합 메일 한 통입니다. HTML 본문은 고정 템플릿이고, Gemini는 콘텐츠 JSON만 만듭니다.

**OTP SMS 자동입력** — `E2E_OTP_RELAY_TOKEN`, `E2E_OTP_RELAY_REGEX`. 인입은 `POST /api/otp/inbound`(`X-OTP-Relay-Token` 헤더). 무인 OTP를 쓸 때는 `E2E_RUN_CONCURRENCY=1`을 권장합니다. 안드로이드 중계기 설정은 [otp_relay.md](otp_relay.md)를 보세요.

**자가 치유** — 무인 실행 중 셀렉터가 깨지면 라이브 DOM을 훑어 한 번 재시도합니다. `/self-healing`에서 KPI와 승인 대기 패치를 관리하고, 패치는 자동으로 소스에 합치지 않습니다.

---

## 더 읽을 곳

| 문서 | 내용 |
| --- | --- |
| [README.md](../README.md) | 점검 도구 사용 안내 |
| [E2E_ARCHITECTURE.md](../E2E_ARCHITECTURE.md) | 아키텍처·API·상태 모델 |
| [CI.md](CI.md) | CI 게이트·로컬 검증 |
| [otp_relay.md](otp_relay.md) | OTP SMS 중계기 |
| [CLAUDE.md](../CLAUDE.md) | 코드베이스 작업 지침 (기여자·에이전트용) |
