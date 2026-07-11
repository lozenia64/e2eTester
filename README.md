# E2E Tester

> **문서 소유권(SSOT):** 이 문서는 **설치·실행 방법, 선택 기능(AI/메일/예약) 사용법, 환경변수 카탈로그**의 단일 진실원천입니다. 플랫폼 아키텍처·API 목록은 [E2E_ARCHITECTURE.md](E2E_ARCHITECTURE.md), 시스템별 시나리오는 `docs/scenarios/{code}.md` 가 소유합니다. 문서 거버넌스 규칙과 정합성 가드는 [docs/DOCS_GOVERNANCE.md](docs/DOCS_GOVERNANCE.md) 를 참고하세요.

사내 임직원이 본인 로컬 PC에서 웹 애플리케이션을 점검하기 위해 사용하는 내부용 E2E 테스터입니다.

이 프로젝트를 내려받아 실행하면 브라우저 기반 테스트를 웹 화면에서 시작할 수 있고, 실행 상태와 로그를 확인할 수 있습니다.

## 프로젝트 소개

이 프로젝트의 목적은 다음과 같습니다.

- 사내 사용자가 직접 로컬 PC에서 웹 애플리케이션 E2E 테스트를 실행
- 테스트 진행 상태를 웹 화면에서 확인
- 실행 중 필요한 입력이 있으면 화면에서 이어서 처리
- 실행 로그와 스크린샷 결과를 로컬에 저장

현재 프로젝트는 Python 기반으로 실행되며, 로컬에서 웹 서버를 띄운 뒤 브라우저로 접속해 사용하는 방식입니다.

## 사용 대상

- 사내 임직원
- 본인 PC에 Python 설치가 가능한 사용자
- 로컬 환경에서 테스트 실행이 필요한 사용자

## 로컬 PC 실행 방법

### 1. 사전 준비

먼저 로컬 PC에 아래가 준비되어 있어야 합니다.

- Python 3 설치
- Git 설치

터미널에서 아래 명령으로 설치 여부를 확인할 수 있습니다.

```bash
python3 --version
git --version
```

### 2. 프로젝트 내려받기

원하는 작업 폴더에서 아래 명령을 실행합니다.

```bash
git clone https://github.com/lozenia64/e2eTester.git
cd e2eTester
```

### 3. 필요한 패키지 설치

프로젝트 폴더에서 아래 명령을 실행합니다.

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

브라우저 실행 시 코드는 로컬 Chrome 채널을 우선 사용하고, 실행이 어려우면 설치된 Playwright Chromium으로 자동 fallback 합니다.

일반 브라우저나 Cursor의 Playwright MCP와 동일하게 보안프로그램(키보드보안/백신류 로컬 에이전트·확장)을 인식시키기 위해, 브라우저를 다음과 같이 띄웁니다.

- **영속 프로파일(persistent context)**: 시크릿 일회용 컨텍스트가 아니라 영속 프로파일로 실행해 확장/인증서/권한 상태가 유지됩니다. **HOM·FP·HRP**는 설치형 보안프로그램 호환을 위해 시스템별 `~/.e2etester/{chrome-profile|fp-chrome-profile|hrp-chrome-profile}` 프로파일과 기존 launch 옵션을 씁니다(`E2E_USER_DATA_DIR`로 경로 변경 가능). **MHM·HWTC·CHBOT** 등 나머지는 Cursor Playwright MCP와 동일한 프로파일(`%LOCALAPPDATA%/ms-playwright-mcp/mcp-chrome-{workspace_hash}`, `E2E_PLAYWRIGHT_MCP_PROFILE_DIR`로 재정의)을 씁니다. 이때 `{workspace_hash}` 는 프로젝트 폴더 경로로 계산하며, MCP 를 다른 폴더 기준으로 쓰고 있다면 `E2E_WORKSPACE_DIR` 로 그 폴더 경로를 지정해 같은 해시(=같은 프로파일)를 쓰게 할 수 있습니다. 같은 프로파일을 쓰는 Chrome/MCP 창이 떠 있으면 Run이 실패할 수 있으며, 동시 실행도 같은 프로파일을 공유할 수 없습니다.
- **확장 활성화**: Playwright 기본값인 `--disable-extensions`(및 component-extensions) 를 제거해, 보안프로그램의 브라우저 확장이 로드되도록 합니다.
- **로컬 네트워크 허용**: 보안프로그램은 로컬 에이전트(loopback/사설망)와 통신합니다. Chrome의 Local/Private Network Access 차단 기능을 꺼서(일반 브라우저에서 "로컬 네트워크 허용"을 켠 것과 동일) 페이지가 로컬 에이전트에 접근할 수 있게 합니다.

> 참고: 위 설정에도 보안프로그램이 인식되지 않으면, 해당 보안프로그램(및 그 브라우저 확장)이 실제로 설치되어 있고, `E2E_USER_DATA_DIR` 가 그 확장이 설치된 프로파일을 가리키는지 확인하세요.

환경에 따라 `python3` 대신 회사 PC에 설치된 Python 실행 경로를 사용해야 할 수 있습니다.

예:

```bash
/usr/local/bin/python3 -m pip install -r requirements.txt
/usr/local/bin/python3 -m playwright install chromium
```

### 4. 웹 서버 실행

프로젝트 폴더에서 아래 명령을 실행합니다.

```bash
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 2222
```

예:

```bash
/usr/local/bin/python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 2222
```

### 5. 브라우저에서 접속

웹 브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:2222
```

같은 PC가 아닌 다른 기기(휴대폰 SMS 중계기 등)에서 접속할 때는 PC의 IP 주소를 사용합니다. 서버는 `--host 0.0.0.0`으로 모든 네트워크 인터페이스에서 수신합니다.

```text
http://<PC IP>:2222
```

예: PC IP가 `219.251.153.96`이면 `http://219.251.153.96:2222`

Windows 방화벽에서 TCP 2222 인바운드를 허용해야 할 수 있습니다.

### Docker Compose (원격 실행 모드)

Redis + API + 워커(2대)로 분리 실행하려면:

```bash
docker compose up --build --scale worker=2
```

- 대시보드: `http://127.0.0.1:2222`
- `E2E_EXECUTION_MODE=remote` 로 API는 Redis 에 Run 작업을 적재하고, 워커가 Playwright 를 실행합니다.
- 로컬 개발(단일 프로세스)은 `E2E_EXECUTION_MODE=local`(기본값)을 사용하세요.

## 사용 흐름

1. 브라우저에서 `/login` 으로 접속해 이메일·비밀번호로 로그인합니다. (최초 관리자 계정은 `.env` 의 `E2E_ADMIN_EMAIL` / `E2E_ADMIN_PASSWORD` 로 시드됩니다.)
2. 홈 화면에서 테스트할 시스템을 선택하거나, 맨 위 **전체 시스템 순차 점검(SUITE)** 카드에서 여러 시스템을 한 번에 실행합니다.
3. 필요한 입력값을 작성합니다. (개별 Run은 모듈 선택, SUITE는 시스템 선택)
4. `실행` 또는 `전체 점검 시작` 버튼을 눌러 테스트를 시작합니다.
5. Run/Suite 화면에서 진행 상태, 로그, 결과를 확인합니다.
6. 추가 입력이 필요한 경우 화면 안내에 따라 계속 진행합니다. (SUITE 실행 중 OTP는 Suite 화면의 OTP 패널에서 제출)

현재 기본으로 포함된 시스템은 다음과 같습니다.

대표홈페이지(로그인·본인인증 포함 전체 점검):

- **HOM**(`대표홈페이지(PC)`): PC 웹 대표홈페이지 점검
- **MHM**(`대표홈페이지(모바일)`): 모바일 웹 대표홈페이지 점검 (Playwright로 모바일 디바이스 모드를 먼저 적용한 뒤 접속)

대표홈페이지와 별개의 업무 시스템(휴대폰 OTP 본인인증 포함, manifest 기준 모듈 수):

- **FP**(`영업가족 위촉서류 등록(PC)`, 3모듈): 메인 접속 → 본인인증(휴대폰 OTP) → 서류작성 — `https://fp.hwgeneralins.com`
- **HRP**(`현장출동 홈페이지(PC)`, 4모듈): 메인 접속 → 로그인(SMS OTP) → 잔존물 입찰 목록/상세 — `https://www.eagleprm.co.kr`
- **HWTC**(`연수원(PC)`, 3모듈): 메인 접속 → 로그인(SMS OTP) → IT교육 동영상 재생 — `https://sls.hwgeneralins.com`
- **CHBOT**(`챗봇(모바일)`, 3모듈): 메인 접속(모바일 모드) → 간편본인인증(휴대폰 OTP) → 계약조회 — `https://chbot.hwgeneralins.com/...`

모든 시스템은 홈 화면 카드를 펼쳐 입력값을 채우고 실행하며, 실행 전 모듈 선택 그래프에서 실행할 모듈을 개별로 선택/해제할 수 있습니다. 선택하지 않은 모듈은 Run 화면에서 `SKIPPED`(건너뜀)로 표시됩니다. FP·HRP·HWTC·CHBOT도 휴대폰 OTP가 필요한 단계가 있으면 Run/Suite 화면에서 OTP를 제출해 재개합니다.

### 전체 시스템 순차 점검 (SUITE)

홈 화면 맨 위 **SUITE** 카드에서 등록된 시스템을 `display_order` 순으로 **하나씩 순차 실행**할 수 있습니다. 개별 Run의 모듈 선택과 같은 패턴으로, 실행 전 **시스템 체크박스**에서 포함할 시스템만 골라 실행할 수 있습니다.

- **시스템 선택**: 기본값은 전체 선택. 체크 해제한 시스템은 Suite 결과 화면에서 `SKIPPED`(건너뜀)로 남고 Run은 생성되지 않습니다.
- **브라우저 모드**: 모든 선택 시스템에 공통 적용 (`headed` / `headless`).
- **시스템별 인증 입력**: `supported_auth_methods` 가 있는 시스템(HOM·MHM·FP·HRP·HWTC·CHBOT)은 SUITE 카드에서 해당 시스템이 선택된 경우에만 인증 입력 패널이 표시·검증됩니다.
- **실패 시 동작**: 한 시스템이 실패해도 다음 선택 시스템 점검은 계속됩니다.
- **OTP**: 휴대폰인증 Run이 `WAITING_INPUT`이 되면 Suite 화면(`/suites/{suite_id}`)에서 OTP를 제출합니다.
- **예약 실행**: SUITE 카드 안에서 cron 예약을 등록할 수 있으며, 등록 시점의 **시스템 선택·브라우저 모드·선택된 시스템별 인증 정보**가 함께 저장되어 예약 트리거 시 동일하게 재현됩니다. 무인 예약은 OTP 대기에서 멈출 수 있습니다.

API 요청 시 `selected_system_codes`를 생략하면 기존과 같이 전체 시스템이 선택됩니다.

### 모바일 즉시 점검 URL (예약 기반)

등록해 둔 예약(개별 시스템·전체 점검 모두)은 **예약별 비밀 토큰이 담긴 전용 URL**(`/m/{trigger_token}`)로도 실행할 수 있습니다. 대시보드 로그인 없이 휴대폰 브라우저에서 URL 에 접속하는 것만으로 해당 예약의 **지금 실행** 버튼과 동일한 점검이 시작됩니다.

- **URL 확인**: 홈 화면 예약 카드의 **모바일 URL** 버튼을 누르면 클립보드로 복사됩니다. 휴대폰 홈 화면/북마크에 등록해 두면 앞으로 접속만으로 같은 점검을 반복 실행할 수 있습니다.
- **동작 방식**: 접속 시 열리는 모바일 페이지가 실행을 요청하고, 진행 상태(통과 개수·결과)를 자동 갱신해 보여줍니다. 페이지(GET) 자체는 실행 부수효과가 없어 메신저 링크 미리보기·브라우저 미리 불러오기로 점검이 오발사되지 않습니다.
- **중복 실행 방지**: 직전 실행이 아직 진행 중이면 새 점검을 만들지 않고 진행 중인 점검 상태를 그대로 보여줍니다(새로고침·중복 탭에 안전).
- **OTP 입력**: 휴대폰인증 단계에서 `WAITING_INPUT` 이 되면 같은 페이지에 인증번호 입력란이 나타나 모바일에서 바로 제출·재개할 수 있습니다.
- **보안**: 토큰은 예약 생성 시 자동 발급되는 추측 불가 문자열이며, URL 을 아는 사람은 누구나 그 예약을 실행할 수 있으므로 사내 인원 외 공유하지 마세요. URL 이 유출되면 대시보드에서 해당 예약을 삭제하면 즉시 폐기됩니다.

### HOM 시스템

**HOM**(`대표홈페이지(PC)`) Run은 다음 순서로 모듈이 실행됩니다.

1. 메인화면 접속 → 로그인(본인인증) → 계약목록 조회 → 계약상세 조회 → 보험금청구 접수(질병/상해) → 보험금청구 결과 조회 → 보험금청구 취소 → 장기보험증권 증명서 발급

   (로그인 화면 이동과 본인인증 로그인은 하나의 `로그인` 모듈에서 함께 처리됩니다.)

실행 폼에는 아래 입력이 있습니다.

- 브라우저 실행 모드
- 인증 수단
- 고객명
- 생년월일
- 성별
- 내외국인 구분
- 통신사
- 휴대폰 번호

**인증 수단**에 따라 본인인증 단계 동작이 다릅니다.

- **휴대폰인증**: SMS 요청 후 Run이 `WAITING_INPUT`으로 멈추면, Run 화면의 OTP 패널에서 인증번호를 제출해 재개합니다.
- **카카오인증**: OTP 입력 없이 자동화가 `인증요청` 후 30초 대기(카카오톡에서 인증)를 거친 뒤 `인증완료`를 누릅니다. 「인증이 완료되지 않았습니다」 등 미완료 알림이 뜨면 `인증요청`을 재시도하며, 최대 3회까지 시도한 뒤에도 실패하면 로그인 단계가 실패 처리됩니다.
- **금융인증서인증 / 공동인증서인증**: 실행 폼에는 표시되지만 현재 API에서 실행을 거부합니다.

실행 폼에서 **성별·내외국인·통신사**는 휴대폰인증에서만 보이고, **고객명·생년월일·휴대폰 번호**는 휴대폰·카카오 모두에서 입력합니다.

현재 HOM 샘플의 보험금청구 관련 동작은 아래 전제를 따릅니다.

- 보험금청구 접수 단계(`charge05`)에서는 로컬 Desktop의 PNG 파일을 첨부합니다.
- 우선 `스크린샷*.PNG` / `Screenshot*.png` 패턴을 찾고, 없으면 Desktop의 다른 `PNG` 파일을 사용합니다.
- 보험금청구 결과 조회 단계는 **오늘 접수된 청구 중 청구내용이 `IT직원 테스트입니다. 바로 취소할 예정입니다.` 인 진행중 건**을 찾아 상세 조회와 제출서류 확인까지 진행합니다.
- 이어지는 보험금청구 취소 단계는 동일한 진행중 건을 다시 찾아 접수 취소하고, 진행중 탭에서 사라지며 완료 탭에 취소 상태로 반영되는지 확인합니다.

### MHM 시스템

**MHM**(`대표홈페이지(모바일)`) Run은 HOM과 동일한 8개 모듈 순서(메인화면 접속 → 로그인(본인인증) → 계약목록 조회 → 계약상세 조회 → 보험금청구 접수 → 보험금청구 결과 조회 → 보험금청구 취소 → 장기보험증권 증명서 발급)로 실행되며, 모바일 웹(`m.hwgeneralins.com`)을 대상으로 합니다.

- 브라우저를 띄운 직후 **모바일 디바이스 모드를 먼저 적용**한 뒤 모바일 메인화면에 접속합니다. (PC 레이아웃으로 열리거나 리다이렉트되는 것을 막기 위함)
- 실행 폼 입력과 인증 수단 동작(휴대폰 OTP / 카카오 30초 대기·최대 3회 재시도)은 HOM과 동일합니다.
- 보험금청구 접수도 데스크탑 PNG 첨부, 청구내용 `IT직원 테스트입니다. 바로 취소할 예정입니다.` 입력, 결과 조회·취소까지 HOM과 같은 전제를 따릅니다. (모바일 화면 UI에 맞춘 selector 사용)

각 화면별 상세 동작은 시나리오 문서를 참고하세요.

- HOM: `docs/scenarios/hom.md`
- MHM: `docs/scenarios/mhm.md`
- FP: `docs/scenarios/fp.md`
- HRP: `docs/scenarios/hrp.md`
- HWTC: `docs/scenarios/hwtc.md`
- CHBOT: `docs/scenarios/chbot.md`

## 결과 확인

테스트 실행 후 로그와 스크린샷은 로컬 프로젝트 폴더 아래 `artifacts/`에 저장됩니다.

추가로 아래 사항을 알아두면 됩니다.

- Run/Suite 실행 이력·상태와 cron 예약은 **SQLite 파일에 영속**되어 서버를 재시작해도 남습니다. 저장 경로는 환경변수 `E2E_DB_PATH`(미설정 시 `data/e2etester.db`)로 지정합니다.
- Run 실행은 **감독되는 작업 큐**의 워커 풀이 소비합니다. 동시에 실행할 Run 수는 환경변수 `E2E_RUN_CONCURRENCY`(미설정 시 4)로 조정합니다. 헤디드 브라우저 자원을 고려해 보수적으로 두며, `1`이면 한 번에 한 Run만 실행합니다.
- 운영 로그는 **structlog** 로 출력합니다. `E2E_LOG_LEVEL`(기본 `INFO`)과 `E2E_LOG_FORMAT`(`console` 또는 `json`)으로 조정합니다. Run/Suite/스케줄 생명주기 이벤트는 관리자 **운영 관측** 페이지(`/admin/ops`)에서도 확인할 수 있습니다.
- 다만 서버를 내릴 때 **진행 중이던 Run/Suite**(RUNNING·OTP 대기)는 브라우저 세션이 함께 사라지므로 이어받을 수 없습니다. 재기동 시 자동으로 `CANCELLED` 로 정리되며, 필요하면 해당 Run을 **재실행(rerun)** 하면 됩니다. (OTP 대기는 **휴대폰인증** Run에서, manifest 에 `requires_user_input` 으로 선언된 모듈에서만 발생합니다 — 대부분 본인인증/로그인 단계이며, FP 는 본인인증과 서류작성 두 단계가 해당합니다.)
- 실시간 로그 라인 버퍼와 WebSocket 연결은 프로세스 메모리에만 있으므로 재시작 시 끊깁니다. 완료된 모듈의 로그는 Run 이력에 함께 저장되어 남습니다.
- 이미 생성된 아티팩트 파일은 로컬 `artifacts/` 폴더에 남아 있습니다.
- 종료 결과는 **정상(`PASSED`) / 이상징후(`ANOMALY`, 사이트에서 의미 있는 이상 발견) / 점검실패(`ERROR`, 점검 도구 자체 오류)** 로 구분됩니다. **점검실패·취소 Run 은 매일 정해진 시각에 자동 삭제**되고(정상·이상징후는 유지), 정상·이상징후만 관리자 사용량 통계에 집계됩니다. 보존 정리는 환경변수 `E2E_RUN_RETENTION_ENABLED`(기본 `true`)로 끄거나 `E2E_RUN_RETENTION_CRON`(기본 `0 3 * * *`, 기준 타임존 `E2E_SCHEDULE_TZ`)로 주기를 바꿉니다.

## 자가 치유 센터 (사이트가 바뀌어도 점검이 안 죽는다)

무인 실행 중 특정 스텝의 셀렉터가 깨지면, 라이브 화면을 스캔해 **대체 셀렉터를 신뢰도 점수와 함께 찾아
점검을 실패시키지 않고 복구**하고 그 내역을 기록합니다. 사이드바 **자가 치유 센터**(`/self-healing`)에서
관리합니다.

- **복구 콘솔** — 이번 달 자동 복구 N건·사람 개입 없이 넘어간 비율·평균 복구 시간(MTTR) KPI 와,
  치유 이벤트마다 `탐지 → AI 진단 → 대체 셀렉터 → 재실행 검증 → 결과` 5단계 파이프라인 카드·신뢰도 게이지를 보여 줍니다.
- **자동 복구 정책** — 시스템별 auto-heal on/off 와 신뢰도 임계치 슬라이더. 임계치 이상이면 이번 Run 을
  런타임 한정으로 자동 복구(1회 재시도)하고, 미만이면 자동 적용 없이 승인 대기 제안만 남깁니다.
- **승인 대기 패치** — 런타임 복구는 일회성이므로, 깨진 하드코딩 셀렉터를 대체 셀렉터로 바꾸는
  before/after diff 를 제안합니다. **자동 병합은 하지 않으며**, 담당자가 diff 를 리뷰해 승인하면 그 시점에
  소스 파일에 반영되고(또는 `.patch` 다운로드), 거절 사유까지 감사 이력으로 남습니다.
- **셀렉터 내구성 맵** — steps 소스의 모든 하드코딩 셀렉터를 안정(🟢 #id·name·role) / 주의(🟡 class) /
  취약(🔴 텍스트 매칭·인덱스 의존·xpath) 으로 점수화하고, 치유 이력과 결합해 "같은 셀렉터 3회+ 깨짐 → 정비 필요"
  만성 취약 지점을 깨지기 전에 보여 줍니다.

## 주의 사항

- 이 프로젝트는 사내 내부용 도구입니다.
- 반드시 회사 정책과 허가된 테스트 환경에서만 사용해야 합니다.
- 테스트 대상 사이트 구조가 바뀌면 일부 자동화 동작이 실패할 수 있습니다. 셀렉터 단위의 단순 변경은
  자가 치유 센터가 런타임에서 복구하고 코드 반영 패치를 제안하지만, 화면 흐름 자체가 바뀌면 스텝 수정이 필요합니다.

## 대시보드 로그인 및 관리자

대시보드·대부분의 API는 JWT 쿠키(`access_token`) 로그인이 필요합니다.

- 로그인 페이지: `GET /login` → `POST /auth/login` (폼 또는 JSON `Accept: application/json`)
- 로그아웃: `POST /auth/logout`
- 비밀번호 변경: `GET /account/password` → `POST /auth/change-password`
- 관리자(admin) 전용: `/admin` (Run 이력·사용자·모듈별 수동 업무 시간·통계)

최초 관리자 계정은 서버 기동 시 `.env` 값으로 시드됩니다.

```bash
E2E_JWT_SECRET=change-me-in-production
E2E_ADMIN_EMAIL=admin@example.com
E2E_ADMIN_PASSWORD=admin1234
```

`E2E_JWT_SECRET` 은 운영 환경에서 반드시 변경하세요. 일반 사용자는 관리자가 `/admin/users` 에서 생성하며, 시스템별 실행 권한을 부여할 수 있습니다.

## 선택 기능: 실패 원인 AI 분석

실패한 모듈에 대해 원인과 다음 조치를 자동 요약하는 선택 기능을 사용할 수 있습니다.

- 기본값은 비활성화이며, 설정하지 않으면 기존 실행 흐름은 그대로 유지됩니다.
- 현재 구현은 Gemini 계열 모델 호출을 전제로 하며, 실패 시에도 테스트 실행 자체는 계속 종료 처리됩니다.

이 기능은 아래 우선순위로 설정값을 읽습니다.

1. 터미널에서 직접 입력한 환경 변수
2. 프로젝트 폴더의 `.env` 파일

즉, 터미널에서 값을 입력하면 그 값을 먼저 사용하고, 터미널에 없으면 `.env` 파일 값을 사용합니다.

가장 쉬운 방법은 `.env.example` 파일을 복사해서 `.env` 파일을 만든 뒤 값을 채우는 것입니다.

```bash
cd e2eTester
cp .env.example .env
```

그다음 `.env` 파일을 열어서 아래 값을 실제 값으로 바꿉니다.

```bash
E2E_FAILURE_ANALYZER_ENABLED=true
GEMINI_API_KEY="실제_발급받은_API_KEY"
GEMINI_MODELS="gemini-3.5-flash|gemini-3.1-flash-lite|gemini-3-flash-preview|gemini-3.1-pro-preview"
E2E_GEMINI_SSL_VERIFY=true
```

설정이 끝나면 아래처럼 바로 서버를 실행하면 됩니다.

```bash
cd e2eTester
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 2222
```

터미널에서 일회성으로 값을 덮어쓰고 싶다면 아래처럼 입력할 수 있습니다.

```bash
cd e2eTester

export E2E_FAILURE_ANALYZER_ENABLED=true
export GEMINI_API_KEY="실제_발급받은_API_KEY"
export GEMINI_MODELS="gemini-3.5-flash|gemini-3.1-flash-lite|gemini-3-flash-preview|gemini-3.1-pro-preview"

python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 2222
```

한 줄로 실행하고 싶다면 아래처럼 입력할 수도 있습니다.

```bash
cd e2eTester

E2E_FAILURE_ANALYZER_ENABLED=true \
GEMINI_API_KEY="실제_발급받은_API_KEY" \
GEMINI_MODELS="gemini-3.5-flash|gemini-3.1-flash-lite|gemini-3-flash-preview|gemini-3.1-pro-preview" \
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 2222
```

브라우저에서 아래 주소로 접속하면 됩니다.

```text
http://127.0.0.1:2222
```

참고:

- `.env` 파일을 사용하면 터미널을 새로 열어도 다시 입력할 필요가 없습니다.
- `export`로 설정한 환경 변수는 해당 터미널 창을 닫으면 사라집니다.
- 터미널 환경 변수와 `.env` 파일에 같은 항목이 모두 있으면 터미널 환경 변수가 우선합니다.
- 회사망 프록시나 사설 인증서 때문에 Gemini API 에서 `CERTIFICATE_VERIFY_FAILED` 가 발생하면 `E2E_GEMINI_SSL_VERIFY=false` 로 SSL 인증서 검증을 우회할 수 있습니다.
- AI 분석 기능을 사용하지 않을 경우 기존처럼 `python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 2222`만 실행하면 됩니다.
- 홈 화면에는 AI 분석 상태 카드가 표시되며, 현재 설정값이 유효한지 바로 확인할 수 있습니다.
- AI 분석 설정이 잘못되어도 앱은 실행되지만, 실패 분석 결과는 생성되지 않을 수 있습니다.

환경에 따라 `python3` 대신 회사 PC에 설치된 Python 실행 경로를 사용해야 할 수 있습니다.

예:

```bash
/usr/local/bin/python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 2222
```

옵션 설명:

- `E2E_FAILURE_ANALYZER_ENABLED`: `true`일 때만 실패 분석 기능을 활성화합니다.
- `GEMINI_API_KEY`: Gemini API 호출 키입니다.
- `GEMINI_MODELS`: `|` 또는 `,`로 구분한 Gemini 모델 fallback 체인입니다. 비우면 기본 4모델 체인을 사용합니다.
- `E2E_GEMINI_SSL_VERIFY`: 기본값은 `true` 입니다. 회사망 SSL 검사 환경에서 Gemini API 인증서 검증 오류가 날 때만 `false` 로 바꿉니다.

## 선택 기능: 종료 메일 알림

테스트가 최종 종료되면 담당자에게 Gmail로 메일을 보낼 수 있습니다.

- `E2E_EMAIL_ENABLED=false`로 설정하면 메일 발송을 비활성화합니다(기본값은 `.env.example` 참고).
- 최종 종료 결과(`PASSED` 정상 · `ANOMALY` 이상징후 · `ERROR` 점검실패) 모두 메일을 보내되, **수신자는 결과 분류에 따라 다릅니다**.
  - 정상·이상징후: 시스템별 수신자(`E2E_EMAIL_RECIPIENTS_{시스템코드}`)에게 보냅니다.
  - **점검실패(`ERROR`)**: 대상 사이트 문제가 아니라 점검 도구 자체의 오류이므로, 시스템 담당자 대신 **도구 운영자(`E2E_EMAIL_OPERATOR_RECIPIENTS`, `|` 구분)에게만** 제목 접두사 `[E2E][OPERATOR]` 로 보냅니다. 운영자 수신자를 설정하지 않으면 점검실패 메일은 생략됩니다. (전체 점검 SUITE 의 점검실패도 동일 규칙)
- `WAITING_INPUT` 처럼 중간 대기 상태에서는 메일을 보내지 않습니다.
- 메일 본문 HTML은 항상 고정 디자인 템플릿(`report_renderer`)으로 결정적으로 렌더링하며, Gemini는 HTML이 아니라 분석 콘텐츠(핵심 요약·화면/로그 관찰·실패 분석)만 구조화 JSON으로 생성해 템플릿에 채웁니다. Gemini가 비활성이거나 호출에 실패하면 같은 템플릿이 AI 서술 없이(기본 문구로) 렌더링됩니다.
- 수신자 메일은 시스템(채널)별 환경 변수 `E2E_EMAIL_RECIPIENTS_{시스템코드}` 로 구분합니다. 기본 포함 시스템은 `HOM`·`MHM`·`FP`·`HRP`·`HWTC`·`CHBOT` 이며, 각각 `E2E_EMAIL_RECIPIENTS_HOM` 등으로 설정합니다.
- 한 채널에 여러 수신자를 넣고 싶다면 `|` 로 구분하면 됩니다.
- **전체 시스템 순차 점검(SUITE)** 이 종료되면, Suite에 포함된 각 시스템 Run의 수신자를 합쳐 **통합 결과 메일 1통**을 보냅니다. 개별 Run 종료 메일은 Suite 소속 Run에서는 보내지 않습니다.

예:

```bash
E2E_EMAIL_ENABLED=true
E2E_EMAIL_GMAIL_ACCOUNT="sender@gmail.com"
E2E_EMAIL_GMAIL_APP_PASSWORD="실제_앱비밀번호"
GEMINI_MODELS="gemini-3.5-flash|gemini-3.1-flash-lite|gemini-3-flash-preview|gemini-3.1-pro-preview"
E2E_GEMINI_SSL_VERIFY=true
E2E_EMAIL_RECIPIENTS_HOM="user1@company.com|user2@company.com"
E2E_EMAIL_RECIPIENTS_MHM="user1@company.com|user2@company.com"
E2E_EMAIL_RECIPIENTS_FP="user1@company.com"
E2E_EMAIL_RECIPIENTS_HRP="user1@company.com"
E2E_EMAIL_RECIPIENTS_HWTC="user1@company.com"
E2E_EMAIL_RECIPIENTS_CHBOT="user1@company.com"
E2E_EMAIL_OPERATOR_RECIPIENTS="operator1@company.com|operator2@company.com"
```

옵션 설명:

- `E2E_EMAIL_RECIPIENTS_{시스템코드}`: 시스템별 정상·이상징후 결과 메일 수신자(`|` 구분).
- `E2E_EMAIL_OPERATOR_RECIPIENTS`: 점검실패(`ERROR`) 메일을 받을 도구 운영자(`|` 구분). 미설정 시 점검실패 메일은 생략됩니다.

이 기능도 아래 우선순위로 값을 읽습니다.

1. 터미널에서 직접 입력한 환경 변수
2. 프로젝트 폴더의 `.env` 파일

즉, 터미널에 같은 항목을 넣으면 그 값이 우선이고, 없으면 `.env` 값을 사용합니다.

메일 동작 규칙:

- **개별 Run** 종료 메일:
  - 성공: 해당 Run 의 모든 스크린샷(`final.png`)을 **메일 본문에 CID 인라인**으로 포함
  - 실패: 위와 동일한 스크린샷 규칙 + 해당 Run 의 실행 로그(`execution.log`)만 **별도 첨부**
- **전체 점검(SUITE)** 종료 메일:
  - 선택되어 실행된 각 시스템 Run 결과를 하나의 보고서로 통합
  - `SKIPPED`(선택 제외) 시스템은 "제외"로 표시하고 통과 분모에는 포함하지 않음
  - 각 시스템·모듈별 스크린샷은 시스템별 상세 섹션 본문에 CID 인라인으로 포함
  - 실패 Suite는 관련 시스템의 로그를 첨부 대상으로 우선 수집
- Gemini 분석 콘텐츠 생성 입력:
  - 성공/실패와 무관하게 해당 Run 의 모든 스크린샷과 실행 로그를 함께 전달
  - 각 스크린샷/로그에는 어느 모듈의 산출물인지 식별할 수 있는 레이블(모듈 ID, 모듈명, 순번)을 붙여 전달
- 메일 본문 HTML은 항상 고정 디자인 템플릿(`report_renderer`)으로 렌더링하고, Gemini 는 스크린샷과 로그를 분석한 콘텐츠(구조화 JSON)만 만들어 그 템플릿에 채움
  - 실행 개요, 핵심 요약, 모듈별 결과표, **모듈별 스크린샷 갤러리(본문 CID 인라인)**, 화면 검증(AI 분석), 로그 분석, 실패 상세 분석(실패 시), 첨부 안내 섹션으로 구성
- 본문 스크린샷 크기 규칙(상하 스크롤 최소화, Outlook 호환):
  - 스크린샷 원본 픽셀 크기(PNG 헤더)를 읽어 **높이 최대 11cm(96dpi 기준 ≈416px)** 로 비율 유지 축소하고, Outlook(Word 엔진)이 CSS 크기를 무시하므로 HTML `width`/`height` 속성으로 고정
  - 세로형(모바일) 스크린샷은 **가로 2장씩** 테이블 2열로 나란히 배치, 가로형(PC) 스크린샷은 가독성을 위해 전체 폭(최대 600px) 1장씩 배치
- 본문 스크린샷·첨부 로그 용량이나 Gemini 입력 한도를 넘으면 가능한 만큼만 포함하고, 제외된 파일 목록을 메일 본문에 함께 표시

주의:

- 스크린샷과 로그에는 실제 테스트 데이터가 포함될 수 있으므로, 반드시 내부 담당자 메일 주소만 수신자로 사용해야 합니다.
- 첨부 파일과 일부 로그/스크린샷은 Gemini 분석 콘텐츠 생성을 위해 Gemini API로도 전달될 수 있습니다.
- 홈 화면에는 메일 알림 상태 카드가 표시되어 현재 설정이 유효한지 바로 확인할 수 있습니다.
- 회사망 SSL 검사로 Gemini API 인증서 오류가 나면 `E2E_GEMINI_SSL_VERIFY=false` 로 설정해 Gemini 호출의 SSL 검증만 우회할 수 있습니다.

## 선택 기능: OTP SMS 자동입력 (중계)

휴대폰인증 Run 은 SMS 요청 후 `WAITING_INPUT` 으로 멈춰 사람이 OTP 를 제출해야 재개됩니다. 이 단계를 무인 자동화하려면, **OTP 문자를 받는 휴대폰을 "SMS 중계기"** 로 두고 수신 OTP 를 서버로 전달하면 됩니다. 안드로이드 앱이 전체 시스템이 되는 것이 아니라, 폰은 **수신 SMS 의 OTP 를 서버로 POST 하는 얇은 중계기** 역할만 합니다. 대시보드는 이미 웹이라 폰 브라우저로도 접속해 볼 수 있습니다.

- 기본값은 비활성이며, `E2E_OTP_RELAY_TOKEN` 을 설정해야만 켜집니다(미설정 시 엔드포인트가 `503`).
- 인입 엔드포인트는 `POST /api/otp/inbound` 이며, **사용자 로그인 세션이 아니라 기기 토큰**(`X-OTP-Relay-Token` 헤더)으로 인증합니다.
- 서버는 `run_id` 없이도 **현재 OTP 를 기다리는 Run 을 자동으로 찾아** 코드를 주입·재개합니다(개별 Run·Suite 공통). 무인 점검은 순차 실행이라 보통 대기 Run 은 1건이며, 여러 건이면 가장 최근에 OTP 입력 대기에 들어간 Run(방금 도착한 SMS 에 대응)에 제출합니다. 안전을 위해 휴대폰인증 점검은 `E2E_RUN_CONCURRENCY=1` 로 순차 실행하길 권장합니다.
- OTP 코드 자체는 서버에 저장하지 않고, 살아 있는 브라우저 세션에 즉시 주입한 뒤 버립니다(기존 OTP 재개와 동일).
- 무인 100% 자동화는 **휴대폰인증** 에서만 가능합니다. 카카오인증은 휴대폰 카카오톡에서 사용자가 직접 승인해야 하므로 이 중계로는 자동화되지 않습니다.

설정 예:

```bash
E2E_OTP_RELAY_TOKEN="길고_무작위한_토큰"
# (선택) SMS 원문에서 OTP 를 추출할 정규식. 첫 캡처 그룹 사용. 미설정 시 (\d{4,8}).
E2E_OTP_RELAY_REGEX="(\d{4,8})"
```

중계기가 보내는 요청 형식(둘 중 하나):

```bash
# (1) 폰/앱이 OTP 숫자만 추출해 보내는 경우
curl -X POST http://<서버>:2222/api/otp/inbound \
  -H "X-OTP-Relay-Token: 길고_무작위한_토큰" \
  -H "Content-Type: application/json" \
  -d '{"code":"123456"}'

# (2) SMS 원문을 그대로 보내고 서버가 정규식으로 추출하는 경우
curl -X POST http://<서버>:2222/api/otp/inbound \
  -H "X-OTP-Relay-Token: 길고_무작위한_토큰" \
  -H "Content-Type: application/json" \
  -d '{"text":"[한화손해보험] 인증번호는 123456 입니다."}'
```

옵션 설명:

- `E2E_OTP_RELAY_TOKEN`: 중계기 인증용 기기 토큰. 설정해야 기능이 켜집니다. 길고 무작위하게 두고, 폰이 사내망 밖에 있으면 TLS/VPN 으로 전송 구간을 보호하세요.
- `E2E_OTP_RELAY_REGEX`: SMS 원문(`text`)에서 OTP 를 뽑는 정규식(첫 캡처 그룹). 회사 SMS 형식에 맞춰 조정합니다. 중계기가 `code` 만 보내면 쓰이지 않습니다.

안드로이드 쪽 구성(중계기 앱 선택, 서버 계약·예시 포함)은 [docs/otp_relay.md](docs/otp_relay.md) 를 참고하세요.

주의:

- OTP 문자를 받는 그 번호의 SIM 이 중계기 폰에 꽂혀 있어야 합니다(인증 계정·번호와 1:1).
- 토큰이 유출되면 누구나 대기 중 Run 에 임의 코드를 주입할 수 있으니, 토큰은 비밀로 관리하고 LAN 밖 노출 시 TLS 를 사용하세요.
