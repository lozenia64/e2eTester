# E2E Tester Sample

이 워크스페이스는 한화손해보험 사이트를 대상으로 한 Python 기반 E2E 샘플이다. 현재 구현은 다음 두 축으로 구성된다.

- FastAPI + Jinja2 기반 웹 대시보드
- Playwright Python sync API 기반 단계형 테스트 모듈

핵심 목적은 웹에서 시스템 단위 테스트를 실행하고, 실행 중인 모듈 상태를 실시간으로 확인하며, 각 모듈의 로그와 스크린샷 아티팩트를 남기는 것이다.

중요:

- 현재 런타임은 Playwright MCP 직접 호출이 아니라 Playwright Python sync API를 사용한다.
- 문서와 코드 구조는 이후 Playwright MCP 기반 게이트웨이로 이관하기 쉽도록 유지하고 있다.

## 현재 구현 범위

현재 샘플 시스템은 `HOM` 하나이며, 휴대폰 본인인증 로그인 흐름을 기준으로 아래 4개 모듈을 순차 실행한다.

1. `메인화면 접속`
2. `로그인 이동`
3. `휴대폰 로그인`
4. `계약목록 조회`

웹에서 실행하면 `/runs/{run_id}` 화면으로 이동하고, 각 모듈이 노드 카드로 표시된다.

현재 동작 특징:

- 휴대폰 OTP는 실행 시작 전에 받지 않고, SMS 발송 후 Run 화면에서 입력한다.
- `브라우저 실행 모드`에서 `실제 브라우저 창 열기`를 선택하면 로컬 PC에 실제 Chromium/Chrome 창이 뜬다.
- 로그인 성공 후 `/my/main.do` 진입 시 후속 팝업을 정리한 뒤 다음 모듈로 진행하도록 로직을 넣어 두었다.
- 계약목록 조회 모듈은 `MY한화 > 개인계약 조회`로 이동해 `/fplaza/inquiry/contract01.do` 진입과 목록 건수를 확인한다.
- 스크린샷은 전체 페이지가 아니라 현재 뷰포트만 저장하며, 캡처 전에 항상 화면 최상단으로 스크롤한다.

## 현재 제한 사항

- 인증 수단 셀렉트에는 `휴대폰인증`, `카카오인증`, `금융인증서인증`, `공동인증서인증`이 보이지만 실제 실행은 `휴대폰인증`만 지원한다.
- 상태 저장소는 SQLite가 아니라 메모리 기반 `InMemoryRunRepository`다. 서버를 재시작하면 Run 이력과 대기 상태가 사라진다.
- 워커는 별도 프로세스가 아니라 FastAPI 프로세스 안에서 `asyncio.create_task` + `asyncio.to_thread`로 실행된다.
- Playwright MCP 게이트웨이 계층은 아직 없다.
- 동일 계정 동시 실행 제어, 재시도 정책, 실패 모듈 재실행, 영구 이벤트 저장은 아직 구현하지 않았다.

## 폴더 구조

실제 주요 파일은 아래와 같다.

```text
e2eTester/
  app/
    api/
      routes_dashboard.py
      routes_runs.py
      routes_systems.py
      ws_runs.py
    core/
      enums.py
      models.py
    orchestrator/
      run_service.py
    registry/
      loader.py
      manifests/
        hom.yaml
    runner/
      artifact_manager.py
      hom_workflow_executor.py
    storage/
      run_repository.py
    web/
      templates/
        index.html
        run.html
      static/
        app.css
        app.js
    main.py
  artifacts/
  hom_login_common.py
  hom_main_access.py
  hom_login_move.py
  hom_phone_login.py
  hom_contract_list.py
  hom_login_phone.py
  README.md
  E2E_ARCHITECTURE.md
```

## 웹 실행 흐름

홈 화면에서 할 수 있는 일:

- 시스템 카드 확인
- 브라우저 실행 모드 선택
- Base URL 입력
- 인증 수단 선택
- 휴대폰인증 선택 시에만 개인정보 입력
- `실행` 버튼으로 Run 생성

Run 화면에서 할 수 있는 일:

- 각 모듈의 상태를 실시간으로 확인
- `WAITING_INPUT` 상태에서 OTP 제출
- 모듈별 `execution.log`, `final.png` 아티팩트 열기
- 실시간 로그 스트림 확인

현재 홈 화면에는 최근 Run 패널이 없다. 실행 버튼을 누르면 바로 Run 상세 화면에서 진행 상황을 확인하는 흐름으로 정리되어 있다.

## API 및 WebSocket

현재 구현된 주요 엔드포인트:

- `GET /`
- `GET /runs/{run_id}`
- `GET /api/systems`
- `POST /api/runs/systems/{system_code}`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/nodes`
- `POST /api/runs/{run_id}/otp`
- `WS /ws/runs/{run_id}`

주요 이벤트 유형:

- `run_created`
- `run_started`
- `run_waiting_input`
- `run_resumed`
- `run_finished`
- `module_queued`
- `module_started`
- `module_waiting_input`
- `module_log`
- `module_finished`
- `snapshot`

## 상태 모델

현재 Run 상태:

- `PENDING`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED`
- `FAILED`

현재 모듈 상태:

- `PENDING`
- `QUEUED`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED`
- `FAILED`
- `BLOCKED`

## HOM 샘플 모듈 설명

### 1. 메인화면 접속

파일:

- `hom_main_access.py`

역할:

- 브라우저 클릭 기반으로 메인 페이지 진입
- 초기 랜딩 팝업 정리

### 2. 로그인 이동

파일:

- `hom_login_move.py`

역할:

- 상단 로그인 버튼 탐색
- 로그인 화면으로 이동

### 3. 휴대폰 로그인

파일:

- `hom_phone_login.py`
- `hom_login_common.py`

역할:

- 휴대폰인증 로그인 링크 진입
- 사용자 정보 입력
- SMS 인증 요청
- OTP 대기 및 제출
- 로그인 성공 URL 확인
- 로그인 후 팝업 정리
- 스크린샷 저장

### 4. 계약목록 조회

파일:

- `hom_contract_list.py`

역할:

- `MY한화` GNB 메뉴 열기
- `개인계약 조회` 진입
- `/fplaza/inquiry/contract01.do` 포함 URL 확인
- 목록 건수 확인
- 스크린샷 저장

## 아티팩트

모듈별 아티팩트는 아래 위치에 저장된다.

```text
artifacts/
  {run_id}/
    {module_id}/
      execution.log
      final.png
```

현재 기본 아티팩트 정책:

- 모든 모듈: `execution.log`
- 스크린샷을 남기는 모듈: `final.png`

실패 시 DOM dump, trace, JSON result 파일은 아직 표준화하지 않았다.

## 설치

```bash
/usr/local/bin/python3 -m pip install -r requirements.txt
/usr/local/bin/python3 -m playwright install chromium
```

## 실행

웹 서버 실행:

```bash
/usr/local/bin/python3 -m uvicorn app.main:app --reload
```

브라우저에서 접속:

```text
http://127.0.0.1:8000
```

## CLI 스크립트

`hom_login_phone.py`는 현재도 유지되고 있는 CLI 엔트리포인트다.

역할:

- 공통 설정 파싱
- 브라우저 런타임 생성
- `hom_main_access.py`
- `hom_login_move.py`
- `hom_phone_login.py`

즉, 기존 단일 스크립트를 완전히 버린 상태가 아니라, 분리된 모듈을 조합하는 래퍼 역할로 남겨 둔 상태다.

예시 실행:

```bash
/usr/local/bin/python3 hom_login_phone.py \
  --base-url "https://www.hwgeneralins.com" \
  --name "홍길동" \
  --birthdate "19840320" \
  --gender male \
  --residency domestic \
  --carrier skt \
  --phone-number 01012345678
```

## 주의 사항

- 실제 운영 사이트를 대상으로 하므로, 반드시 허가된 환경과 테스트 가능한 데이터로만 사용해야 한다.
- OTP, 팝업, GNB 구조, 계약목록 구조는 실사이트 변화에 따라 selector 보강이 필요할 수 있다.
- 현재 문서는 “지금 있는 샘플 코드” 기준 문서이며, 장기 목표 구조는 `E2E_ARCHITECTURE.md`에 따로 정리한다.# e2eTester
