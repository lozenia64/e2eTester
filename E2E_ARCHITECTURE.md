# E2E Tester 아키텍처 문서

## 1. 문서 목적

이 문서는 두 가지를 동시에 설명한다.

1. 현재 워크스페이스에 이미 구현된 샘플 구조
2. 이 샘플을 바탕으로 확장할 때의 목표 아키텍처

즉, 추상적인 이상 구조만 설명하는 문서가 아니라, 현재 코드가 어느 단계까지 와 있는지와 앞으로 어떤 방향으로 정리할지를 함께 기록한다.

## 2. 현재 구현 한 줄 요약

현재 구현은 다음과 같다.

- FastAPI 서버가 웹 화면과 API, WebSocket을 제공한다.
- HOM 시스템은 manifest 기반으로 로드된다.
- Run 생성 후 모듈 상태가 실시간으로 갱신된다.
- 실행 엔진은 Playwright Python sync API 기반의 공유 브라우저 세션 워크플로우다.
- OTP는 Run 도중 `WAITING_INPUT` 상태로 전환한 뒤 웹 화면에서 제출한다.

현재는 완성형 플랫폼이 아니라, “운영 가능한 작은 샘플 플랫폼” 단계다.

## 3. 현재 코드 기준 실제 구조

```text
Browser
  -> FastAPI app
      -> RunService
          -> ModuleRegistry
          -> InMemoryRunRepository
          -> HomWorkflowExecutor
              -> Shared Playwright browser session
                  -> Split HOM modules
                      -> Site

FastAPI app
  -> HTML routes
  -> JSON APIs
  -> WebSocket stream
  -> Static artifacts mount
```

현재 구조의 핵심 특징:

- 웹 요청과 실행 orchestration은 같은 프로세스에 있다.
- 실제 Playwright 실행은 `asyncio.to_thread(...)`로 메인 이벤트 루프 바깥 스레드에서 수행한다.
- 하나의 Run 안에서는 공유 브라우저 세션을 유지한 채 단계형 모듈을 순차 실행한다.
- 모듈 로그와 상태 이벤트는 repository를 통해 WebSocket에 전파된다.

## 4. 현재 폴더 구조

```text
e2eTester/
  app/
    ai/
      failure_analyzer.py
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

## 5. 현재 계층별 역할

### 5.1 Web 계층

현재 구현:

- `routes_dashboard.py`
- `app/web/templates/index.html`
- `app/web/templates/run.html`
- `app/web/static/app.js`
- `app/web/static/app.css`

역할:

- 시스템 카드 렌더링
- 조건부 입력 폼 렌더링
- Run 화면 렌더링
- WebSocket 수신 후 노드/로그/OTP 패널 갱신

현재 UX 특징:

- 홈 화면은 “시스템 실행” 중심이다.
- 최근 Run 패널은 제거되어 있다.
- 홈 화면에는 AI 분석 설정 상태 카드가 표시된다.
- 실행하면 곧바로 Run 상세 화면으로 이동한다.
- 인증 수단 셀렉트는 존재하지만 현재 실제 실행은 휴대폰인증만 허용된다.

### 5.2 API 계층

현재 구현:

- `GET /`
- `GET /runs/{run_id}`
- `GET /api/systems`
- `POST /api/runs/systems/{system_code}`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/nodes`
- `POST /api/runs/{run_id}/otp`
- `WS /ws/runs/{run_id}`

역할:

- 시스템 목록 조회
- Run 생성
- Run 조회
- OTP 재개
- 실시간 상태 이벤트 스트리밍

### 5.3 Orchestrator 계층

현재 구현 핵심은 `app/orchestrator/run_service.py` 다.

역할:

- Run ID 발급
- manifest 기준 모듈 리스트 생성
- 모듈 상태 전이 관리
- 의존성 실패 시 `BLOCKED` 처리
- OTP 대기 상태 저장
- OTP 제출 후 중단된 단계부터 재개
- 이벤트 publish

현재 상태 전이:

Run:

- `PENDING`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED`
- `FAILED`

Module:

- `PENDING`
- `QUEUED`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED`
- `FAILED`
- `BLOCKED`

아직 없는 것:

- `CANCELLED`
- `SKIPPED`
- 재시도 정책
- 실패 모듈만 재실행

### 5.4 Registry 계층

현재 구현:

- `app/registry/loader.py`
- `app/registry/manifests/hom.yaml`

역할:

- 시스템 정의 로드
- Run form 정의 로드
- 모듈 메타데이터 로드

현재 `hom.yaml` 에 들어 있는 정보:

- 시스템 코드, 이름, 설명
- 폼 필드 정의
- `show_when` 기반 조건부 노출 규칙
- 모듈 순서와 의존성
- `workflow_step`

실행 규칙:

- 모듈은 `order` 오름차순으로 순차 실행된다.
- `depends_on` 은 추가 실행 제약이며, 선행 모듈이 모두 `PASSED` 여야 다음 모듈이 실행된다.

현재 HOM 모듈 목록:

1. `hom.main.access`
2. `hom.login.move`
3. `hom.login.phone_login`
4. `hom.contract.list`

### 5.5 Runtime / Runner 계층

현재 구현:

- `app/runner/hom_workflow_executor.py`
- `app/runner/artifact_manager.py`
- 루트 레벨 분할 모듈 파일들

실행 모델:

- Run 단위로 Playwright 런타임 생성
- 하나의 browser/context/page를 공유
- 단계형 모듈을 순차 실행
- 표준 출력/표준 에러를 가로채 실행 로그로 저장

이 구조를 택한 이유:

- 로그인 이후 세션을 다음 모듈에 전달해야 함
- OTP 이후 인증 상태를 유지해야 함
- 계약목록 조회 같은 후속 모듈은 동일 세션이 필요함

### 5.6 Storage 계층

현재 구현:

- `app/storage/run_repository.py`

역할:

- Run 객체 저장
- 모듈 로그 저장
- WebSocket listener 큐 관리

제약:

- 메모리 기반 저장소다.
- 서버 재시작 시 Run, 로그, OTP 대기 상태가 모두 사라진다.

### 5.7 AI 실패 분석 계층

현재 구현:

- `app/ai/failure_analyzer.py`

역할:

- 환경 변수와 `.env` 기준으로 Gemini 설정을 읽는다.
- 실패한 모듈의 최근 로그, 다이얼로그, 현재 URL, 스크린샷을 바탕으로 원인 요약을 시도한다.
- 홈 화면에 현재 AI 분석 설정 상태를 표시한다.

제약:

- 기본값은 비활성화다.
- 설정이 잘못되어도 앱은 계속 실행되며, 실패 분석만 생략될 수 있다.

## 6. 현재 HOM 샘플 워크플로우

현재 실제 흐름은 아래와 같다.

```text
메인화면 접속
  -> 로그인 이동
      -> 휴대폰 로그인
          -> OTP 대기/재개
              -> 로그인 성공 후 팝업 정리
                  -> 계약목록 조회
```

### Step 1. 메인화면 접속

파일:

- `hom_main_access.py`

역할:

- 브라우저 클릭 기반 메인 URL 진입
- 랜딩 팝업 정리

### Step 2. 로그인 이동

파일:

- `hom_login_move.py`

역할:

- 상단 로그인 링크 탐색
- 로그인 페이지 이동

### Step 3. 휴대폰 로그인

파일:

- `hom_phone_login.py`
- `hom_login_common.py`

역할:

- 휴대폰 인증 페이지 이동
- 사용자 정보 입력
- SMS 요청
- OTP 제출
- `/my/main.do` 포함 URL 진입 확인
- 로그인 후 팝업 정리 시도
- 스크린샷 저장

### Step 4. 계약목록 조회

파일:

- `hom_contract_list.py`

역할:

- `MY한화 > 개인계약 조회` 이동
- `/fplaza/inquiry/contract01.do` 포함 URL 확인
- 목록 건수 확인
- 스크린샷 저장

### Step 5. 계약상세 조회

파일:

- `hom_contract_detail.py`

역할:

- `/fplaza/inquiry/contract01.do` 화면에서 증권번호 중 하나로 이동
- `/fplaza/inquiry/contract02.do` 포함 URL 확인
- 계약일반정보,수익자정보,자동이체현황,우편물 수령지/연락처,담당자정보,계약자정보 확인
- 스크린샷 저장

## 7. 현재 UI 입력 모델

홈 화면의 `HOM` 실행 카드에는 아래 입력이 있다.

- 브라우저 실행 모드
- Base URL
- 인증 수단
- 고객명
- 생년월일
- 성별
- 내외국인 구분
- 통신사
- 휴대폰 번호

조건부 규칙:

- 인증 수단이 `휴대폰인증`일 때만 개인정보 입력 필드 노출
- 다른 인증 수단은 아직 placeholder이며 API에서 실행을 거부

## 8. 현재 아티팩트 전략

모듈별 저장 경로:

```text
artifacts/
  {run_id}/
    {module_id}/
      execution.log
      final.png
```

현재 구현 내용:

- 현재 HOM manifest의 `hom_workflow_step` 모듈은 로그를 `execution.log` 로 남긴다.
- 현재 HOM manifest의 `hom_workflow_step` 모듈은 스크린샷을 `final.png` 로 남긴다.
- Run 화면에서 아티팩트 링크 노출
- 링크 경로는 `/artifacts/{run_id}/{module_id}/{filename}` 형식이다.

주의:

- 초기 단계에서 실패하면 스크린샷이 없을 수 있다.
- `simulated` 실행 모드는 현재 HOM 샘플에서 쓰이지 않으며, 이 경우 아티팩트가 생성되지 않을 수 있다.

아직 없는 것:

- `fail.png`
- `dom.html`
- `trace.zip`
- `result.json`

## 9. 현재 이벤트 모델

WebSocket으로 흐르는 주요 이벤트:

- `snapshot`
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

현재 payload 특징:

- Run 이벤트는 `run.model_dump(mode="json")`
- Module 이벤트는 `module` 스냅샷과 `run_status`
- Log 이벤트는 `module_id`, `message`

## 10. 현재 구현과 초기 목표의 차이

초기 목표는 `웹 트리거형 실행 플랫폼` 이었고, 현재 샘플은 그 방향에 맞는 첫 단계까지 구현되어 있다. 다만 아래는 아직 목표 상태가 아니다.

### 10.1 아직 구현되지 않은 것

- SQLite 또는 Postgres 기반 영구 저장소
- 별도 worker process
- Playwright MCP 게이트웨이 추상화
- 표준 `BrowserGateway`
- `ModuleContext`, `ModuleResult` 표준화
- 병렬 실행 스케줄러
- 재시도 정책
- 취소/중단/재실행
- 오류 분류 체계

### 10.2 이미 방향이 맞는 것

- 웹 트리거 방식
- manifest 기반 시스템/모듈 로딩
- 모듈별 노드 대시보드
- 실시간 이벤트 스트림
- 아티팩트 분리 저장
- 모놀리식 스크립트의 단계 모듈 분리
- 로그인 세션 공유형 워크플로우

## 11. 왜 현재 구조가 합리적인가

현재 구현은 일부 이상적인 구조를 의도적으로 미뤘다. 이유는 다음과 같다.

- 실제 사이트 흐름을 먼저 안정화하는 것이 중요했다.
- 로그인, OTP, 팝업, 후속 GNB 탐색처럼 상태를 공유해야 하는 흐름이 많아서, 초기에는 공유 세션 기반 직렬 모듈 구조가 가장 현실적이었다.
- SQLite, 워커, MCP abstraction을 한 번에 넣으면 디버깅 복잡도가 급격히 올라간다.

즉, 현재 샘플은 “플랫폼의 골격”과 “현실적인 사이트 자동화 로직”을 먼저 맞춘 버전이다.

## 12. 다음 단계 권장안

### Phase 1. 현재 샘플 안정화

- 로그인 후 팝업 종료 안정성 보강
- 계약목록 조회 selector 보강
- 실패 시 디버그 아티팩트 확장
- `계약 상세 조회` 모듈 추가

### Phase 2. 저장소와 실행 모델 개선

- `InMemoryRunRepository` 를 SQLite 기반으로 교체
- OTP 대기 상태를 영구 저장
- 서버 재시작 복구 시나리오 고려

### Phase 3. 런타임 추상화

- `BrowserGateway` 도입
- 현재 sync API 호출을 gateway 뒤로 이동
- 이후 Playwright MCP 구현체 추가

### Phase 4. 실행 분리

- Web 프로세스와 Worker 프로세스 분리
- timeout, kill, concurrency 정책 추가
- 시스템/계정 단위 동시 실행 제어

## 13. 목표 아키텍처

현재 샘플이 향후 도달해야 할 목표 구조는 아래와 같다.

```text
Web UI
  -> FastAPI Backend
      -> Run Orchestrator
          -> Module Scheduler
              -> Worker Process
                  -> BrowserGateway
                      -> Playwright MCP Gateway
                          -> Browser

Backend
  -> WebSocket Event Hub
  -> Persistent Run State Store
  -> Artifact Store
  -> Module Registry
```

이 목표 구조로 가면 아래가 가능해진다.

- 서버 재시작 후 Run 상태 유지
- 실행 격리
- 병렬도 제어
- 테스트 모듈과 브라우저 구현 분리
- Playwright MCP 기반 이관

## 14. 결론

현재 소스코드는 단순한 Playwright 스크립트 모음이 아니라, 이미 웹 트리거형 E2E 플랫폼의 최소 실행 골격을 갖춘 샘플이다.

정리하면 현재 상태는 아래다.

- 웹에서 시스템 실행 가능
- 실시간 모듈 노드 대시보드 존재
- OTP pause/resume 존재
- 로그인 이후 후속 모듈 실행 구조 존재
- manifest 기반 확장 포인트 존재

앞으로의 핵심 작업은 “새 모듈 추가” 자체보다, 현재 구조를 깨지 않고 저장소, 워커, MCP abstraction을 점진적으로 넣는 것이다.