# E2E Control Deck

이 문서에는 **설치와 실행**, **선택 기능**(AI 분석, 메일, 예약) 사용법, **환경변수 목록**이 담겨 있습니다. 아키텍처나 API 전체 목록은 [E2E_ARCHITECTURE.md](E2E_ARCHITECTURE.md)가, 시스템별 화면 흐름은 `docs/scenarios/{code}.md`가 각각 맡습니다. 문서를 어디에 써야 하는지에 대한 규칙은 [docs/DOCS_GOVERNANCE.md](docs/DOCS_GOVERNANCE.md)를 보면 됩니다.

---

## 이 도구는 무엇을 하는가

아침에 매장 문을 열기 전, 누군가는 불이 켜지는지, 카드 단말기가 살아 있는지, 화면에 이상한 오류가 뜨지 않는지 확인합니다. 우리가 만든 웹도 비슷합니다. 배포가 끝났다고 해서 고객이 처음 만나는 화면이 반드시 괜찮다는 뜻은 아니거든요.

**E2E Control Deck**은 그 확인을 사람 대신, 브라우저로 대신 해 주는 사내 점검 도구입니다. 직원이 대시보드에서 실행을 누르면 PC에 Chrome이 열리고, 정해진 순서대로 로그인하고, 계약을 조회하고, 청구 화면까지 들어가 봅니다. 각 단계마다 로그가 남고, 마지막 화면은 스크린샷으로 남깁니다. 고객용 서비스가 아니라, **우리가 스스로 “고객 입장에서 잘 되나?”를 반복해서 묻기 위한 내부 장치**입니다.

점검은 웹 화면에서 시작합니다. 진행 상황은 실시간으로 보이고, 휴대폰 인증이 필요한 구간에서는 잠시 멈춰 번호 입력을 기다립니다. 새벽이나 주말처럼 사람이 없는 시간에도 예약으로 돌릴 수 있지만, OTP가 걸리면 그때는 누군가 한 번 개입해야 합니다.

---

## 처음 만나는 사람에게

주소는 보통 `http://127.0.0.1:2222`입니다. 처음이라면 누군가와 함께 로그인해 보는 편이 마음이 편합니다. 설치와 서버를 켜는 일은 이 글 뒤쪽 [설치와 운영](#설치와-운영)에 적어 두었습니다.

로그인한 뒤 왼쪽 메뉴에서 **「점검 실행」**으로 갑니다. 점검할 **시스템**(예: 대표홈페이지 PC)과 **항목**을 고르고, 필요하면 테스트용 고객 정보를 넣습니다. **「실행」** 또는 맨 위 **「전체 점검 시작」**을 누르면 곧 브라우저 창이 뜨고 화면이 저절로 움직입니다. 진행 화면에서 단계별 상태·로그·스크린샷을 보면서 따라가면 됩니다. 끝나면 **대시보드**와 **Run 이력**에서 요약을 확인할 수 있습니다.

휴대폰 인증이 필요한 단계에서는 점검이 잠깐 멈추고 입력란이 나타납니다. 문자로 받은 번호를 넣고 제출하면 이어집니다.

---

## 화면을 돌아다니며

로그인 직후 보이는 **대시보드**는 오늘 각 시스템·항목이 정상인지, 이상이 있는지, 아직 안 돌렸는지를 한눈에 보여 줍니다. **점검 실행**은 지금 당장 돌릴 때 쓰는 곳이고, 시스템별 카드와 맨 위 **전체 순차 점검(SUITE)** 카드가 있습니다. **Run 이력**은 지난 점검을 날짜별로 찾아봅니다.

자주 같은 인증 정보와 항목 조합을 쓴다면 **프리셋 관리**에 이름을 붙여 저장해 두었다가 다음에 한 번에 불러올 수 있습니다. **예약 관리**에서는 반복 일정을 등록하고, 실패하거나 빠진 예약이 없는지 모니터링합니다. 모바일 전용 URL(`/m/...`)로 로그인 없이 “지금 실행”도 가능합니다.

**이상징후 인박스**에는 사이트 쪽에서 의미 있는 이상이 잡힌 점검만 모아 둡니다. **자가 치유 센터**는 화면 버튼 위치가 바뀌어 점검이 깨졌을 때, 자동으로 살려 낸 기록과 개발에 반영할 수정 제안을 다룹니다. **시스템 인사이트**는 통계와 추이를 봅니다. 관리자(admin)는 사용자·권한·전체 Run 이력·사용량을 **관리자 화면**에서 다룹니다.

---

## 결과를 읽는 법

**정상**이면 점검한 흐름이 기대대로 돌아갔다는 뜻입니다. 별다른 조치는 없어도 됩니다.

**이상징후**는 점검 자체는 끝까지 갔는데, 실제 사이트에서 뭔가 이상하다는 뜻입니다. 해당 서비스를 맡은 쪽이 봐야 합니다.

**점검실패**는 점검 도구나 환경 쪽 문제로 중간에 끊겼다는 뜻입니다. 도구를 운영·개발하는 쪽이 봐야 합니다.

그밖에 **건너뜀**(선택하지 않은 항목), **취소**(사람이 중단했거나 서버가 꺼짐), **입력 대기**(OTP 등)도 있습니다.

---

## 어떤 사이트를 점검하나

| 코드 | 이름 | 대략적인 흐름 |
| --- | --- | --- |
| **HOM** | 대표홈페이지(PC) | 접속 → 로그인(휴대폰/카카오) → 계약·청구·증명서·마케팅동의 |
| **MHM** | 대표홈페이지(모바일) | HOM과 같은 흐름, 모바일 화면 기준 |
| **FP** | 영업가족 위촉서류 등록(PC) | 접속 → 본인인증(OTP) → 서류 작성 |
| **HRP** | 현장출동 홈페이지(PC) | 접속 → 로그인(SMS OTP) → 잔존물 입찰 목록·상세 |
| **HWTC** | 연수원(PC) | 접속 → 로그인(SMS OTP) → IT교육 동영상 재생 |
| **CHBOT** | 챗봇(모바일) | 접속(모바일) → 간편 본인인증(OTP) → 계약 조회 |

화면마다 무엇을 누르고 무엇을 확인하는지는 시나리오 문서에 적어 두었습니다. 실행 전 항목을 골라 넣거나 빼 낼 수 있고, 빼 둔 항목은 **건너뜀**으로 표시됩니다.

| 시스템 | 문서 |
| --- | --- |
| HOM | [docs/scenarios/hom.md](docs/scenarios/hom.md) |
| MHM | [docs/scenarios/mhm.md](docs/scenarios/mhm.md) |
| FP | [docs/scenarios/fp.md](docs/scenarios/fp.md) |
| HRP | [docs/scenarios/hrp.md](docs/scenarios/hrp.md) |
| HWTC | [docs/scenarios/hwtc.md](docs/scenarios/hwtc.md) |
| CHBOT | [docs/scenarios/chbot.md](docs/scenarios/chbot.md) |

**전체 순차 점검(SUITE)**은 등록된 시스템을 순서대로 돌립니다. 시스템별로 포함·제외를 정할 수 있고, 한 곳에서 실패해도 다음은 계속 갑니다. SUITE에서는 시스템마다 프리셋을 지정해야 합니다.

---

## 알아두면 마음이 편한 것들

점검 범위를 바꾸려면 개발이 필요하고, `docs/scenarios/{시스템코드}.md`도 함께 고쳐야 합니다. 사이트 구조가 크게 바뀌면 자가 치유만으로는 부족할 수 있고, 시나리오와 자동화 코드를 손봐야 합니다. 허가된 테스트 계정과 환경에서만 쓰고, 테스트 데이터나 스크린샷에 담긴 개인정보를 밖으로 가져가지 마세요.

---

## 자주 묻는 질문

**고객이 쓰는 서비스인가요?**  
아닙니다. 사내에서 품질을 점검하기 위한 도구입니다.

**웹만 열면 되나요?**  
아닙니다. 브라우저 자동 조작은 점검을 실행하는 PC에서 일어납니다.

**점검 중에 제 컴퓨터를 써도 되나요?**  
점검용 Chrome 창은 가능하면 건드리지 않는 편이 낫습니다.

**예약이 안 돌았어요.**  
**예약 관리**에서 해당 예약 상태를 먼저 확인해 보세요. 원인이 보이지 않으면 이 도구를 설치·운영하는 쪽에 알려 주시면 됩니다.

---

## 설치와 운영

사내 임직원이 로컬 PC에서 회사 웹사이트를 자동 점검하기 위한 내부용 E2E 테스터입니다. 웹 대시보드에서 점검을 시작·감시하고, 로그와 스크린샷을 확인합니다. 실행 이력은 SQLite에, 로그·스크린샷 파일은 `artifacts/`에 남습니다.

**준비:** Python 3.11 이상, Git, Redis(`redis-cli ping` → `PONG`).

### 설치와 기동

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

Redis가 없다면:

```bash
# Windows: winget install Redis.Redis
# macOS: brew install redis  → run_local.py 가 자동 기동하거나 python3 scripts/run_redis.py --daemonize yes
# Ubuntu: sudo apt-get install -y redis-server && sudo service redis-server start
```

로컬 데이터는 git에 안 올라갑니다. `data/`에 SQLite, `redis-data/`에 Redis 영속 파일이 생깁니다. Redis 주소를 바꾸려면 `.env`의 `E2E_REDIS_URL`을 수정하세요.

`run_local.py` 옵션: `--no-start-redis`, `--api-port`, `--worker-port`. 워커 HTTP 기본 주소는 `http://127.0.0.1:8100`입니다.

브라우저는 로컬 Chrome 채널을 먼저 쓰고, 안 되면 Playwright Chromium으로 넘어갑니다. **HOM·FP·HRP**는 `~/.e2etester/*-chrome-profile`(`E2E_USER_DATA_DIR`)을 씁니다. **MHM·HWTC·CHBOT** 등은 `%LOCALAPPDATA%/ms-playwright-mcp/mcp-chrome-{workspace_hash}`(`E2E_PLAYWRIGHT_MCP_PROFILE_DIR`, `E2E_WORKSPACE_DIR`)입니다. 보안 프로그램과 맞추려고 확장 로드·로컬 네트워크 허용 설정이 들어가 있습니다.

### 실행 구조

웹/API와 Playwright 브라우저는 **서로 다른 프로세스**입니다. Redis로 세션과 실시간 알림을 나눠 쓰기 때문에, 실제 점검에는 API·워커·Redis가 함께 떠 있어야 합니다. `scripts/run_local.py`가 세 프로세스를 한꺼번에 띄우고 끌 때 같이 내립니다(`E2E_EXECUTION_MODE=remote`).

### 운영과 보존

Run·Suite 이력과 cron 예약은 SQLite(`E2E_DB_PATH`, 기본 `data/e2etester.db`)에 있습니다. 아티팩트는 `artifacts/{run_id}/{module_id}/` 아래 `execution.log`, `final.png`입니다. 동시 실행 상한은 `E2E_RUN_CONCURRENCY_HEAVY`(2), `LIGHT`(4), `INTERACTIVE`(2)이고, 레거시 `E2E_RUN_CONCURRENCY`(4)도 남아 있습니다. 서버를 재시작하면 진행 중이던 브라우저 세션은 사라지고 Run은 `CANCELLED`로 정리됩니다(체크포인트가 있으면 복구 가능). 점검실패·취소 Run은 `E2E_RUN_RETENTION_CRON`(기본 `0 3 * * *`, `E2E_SCHEDULE_TZ`)에 따라 자동 삭제됩니다.

로그인은 `GET /login` → `POST /auth/login`, 비밀번호 변경은 `GET /account/password`입니다. 관리자는 `/admin`(사용자·통계·운영 관측 `/admin/ops`)을 쓰고, 일반 사용자 계정은 `/admin/users`에서 만들며 시스템별 권한을 줍니다.

### 환경변수 카탈로그

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

### 선택 기능

기본은 모두 꺼져 있습니다. 설정이 틀려도 앱은 뜨지만, 해당 기능만 동작하지 않을 수 있습니다.

**실패 원인 AI 분석** — `E2E_FAILURE_ANALYZER_ENABLED=true`, `GEMINI_API_KEY`, `GEMINI_MODELS=gemini-3.5-flash|gemini-3.1-flash-lite|gemini-3-flash-preview|gemini-3.1-pro-preview`, `E2E_GEMINI_SSL_VERIFY`.

**종료 메일** — `E2E_EMAIL_ENABLED=true`와 Gmail 계정·앱 비밀번호. 정상·이상징후는 `E2E_EMAIL_RECIPIENTS_{시스템코드}`, 점검실패는 `E2E_EMAIL_OPERATOR_RECIPIENTS`만 받습니다. SUITE가 끝나면 통합 메일 한 통입니다. HTML 본문은 고정 템플릿이고, Gemini는 콘텐츠 JSON만 만듭니다.

**OTP SMS 자동입력** — `E2E_OTP_RELAY_TOKEN`, `E2E_OTP_RELAY_REGEX`. 인입은 `POST /api/otp/inbound`(`X-OTP-Relay-Token` 헤더). 무인 OTP를 쓸 때는 `E2E_RUN_CONCURRENCY=1`을 권장합니다. 안드로이드 중계기 설정은 [docs/otp_relay.md](docs/otp_relay.md)를 보세요.

**자가 치유** — 무인 실행 중 셀렉터가 깨지면 라이브 DOM을 훑어 한 번 재시도합니다. `/self-healing`에서 KPI와 승인 대기 패치를 관리하고, 패치는 자동으로 소스에 합치지 않습니다.

### 더 읽을 곳

| 문서 | 내용 |
| --- | --- |
| [E2E_ARCHITECTURE.md](E2E_ARCHITECTURE.md) | 아키텍처·API·상태 모델 |
| [docs/CI.md](docs/CI.md) | CI 게이트·로컬 검증 |
| [docs/otp_relay.md](docs/otp_relay.md) | OTP SMS 중계기 |
| [CLAUDE.md](CLAUDE.md) | 코드베이스 작업 지침 (기여자·에이전트용) |
