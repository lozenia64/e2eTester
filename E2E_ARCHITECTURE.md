# E2E Tester 아키텍처 문서

> **문서 소유권(SSOT):** 이 문서는 **플랫폼 아키텍처·계층 역할·상태머신·이벤트 모델·아티팩트 전략·폴더 구조·API 엔드포인트 목록(§5.2)** 의 단일 진실원천이다. 시스템별 시나리오는 `docs/scenarios/{code}.md`, 실행 방법·환경변수는 `README.md` 가 소유한다. 전체 규칙과 PR 체크리스트는 [docs/DOCS_GOVERNANCE.md](docs/DOCS_GOVERNANCE.md) 참고. 코드로 추출 가능한 사실은 `scripts/check_docs_consistency.py` 가 소스와의 일치를 강제한다.

## 1. 문서 목적

이 문서는 두 가지를 동시에 설명한다.

1. 현재 워크스페이스에 이미 구현된 샘플 구조
2. 이 샘플을 바탕으로 확장할 때의 목표 아키텍처

즉, 추상적인 이상 구조만 설명하는 문서가 아니라, 현재 코드가 어느 단계까지 와 있는지와 앞으로 어떤 방향으로 정리할지를 함께 기록한다.

**시스템별 테스트 시나리오는 이 문서에 쓰지 않는다.** 각 시스템(HOM, MHM, FP, HRP, HWTC, CHBOT, ...)의 시나리오는 `docs/scenarios/{system_code}.md` 개별 문서로 관리한다. 자세한 규칙은 [6. 시스템 시나리오 문서](#6-시스템-시나리오-문서)를 참고한다.

## 2. 현재 구현 한 줄 요약

현재 구현은 다음과 같다.

- FastAPI 서버가 웹 화면과 API, WebSocket을 제공한다.
- 시스템은 manifest 기반으로 로드된다. (현재 기본 포함 시스템: 대표홈페이지 HOM·MHM, 업무 시스템 FP·HRP·HWTC·CHBOT — 각각 다단계 모듈·휴대폰 OTP 시나리오)
- Run 생성 후 모듈 상태가 실시간으로 갱신된다.
- **전체 시스템 순차 점검(Suite)** 으로 등록 시스템을 `display_order` 순으로 연속 실행할 수 있으며, 실행 전 시스템별 포함/제외(`selected_system_codes`)를 선택할 수 있다.
- 실행 엔진은 Playwright Python sync API 기반의 공유 브라우저 세션 워크플로우다.
- 모듈 실행 도중 사용자 입력이 필요하면 Run이 `WAITING_INPUT`으로 전환되고, 웹에서 입력을 제출해 재개할 수 있다. (예: HOM 휴대폰인증의 OTP)

현재는 완성형 플랫폼이 아니라, “운영 가능한 작은 샘플 플랫폼” 단계다.

## 3. 현재 코드 기준 실제 구조

```text
Browser
  -> FastAPI app
      -> RunService
          -> ModuleRegistry           (app/registry/loader.py + systems/*/manifest.yaml)
          -> RunRepositoryPort        (기본 SqliteRunRepository: SQLite 영속 / InMemory 대체 가능)
          -> WorkflowExecutor         (execution_mode -> RepHomepageExecutor(+ChannelProfile) / access_common executor)
              -> Shared Playwright browser session
                  -> Channel step adapters (app/systems/{code}/steps/*.py)
                      -> Site

Browser
  -> FastAPI app
      -> SuiteService
          -> RunService (시스템별 Run 순차 생성·대기)
          -> SuiteRepositoryPort (기본 SqliteSuiteRepository: SQLite 영속)

FastAPI app
  -> HTML routes (/, /runs/{id}, /suites/{id})
  -> JSON APIs
  -> WebSocket stream (/ws/runs, /ws/suites)
  -> Static artifacts mount
```

현재 구조의 핵심 특징:

- 웹 요청과 실행 orchestration은 같은 프로세스에 있다. 단, **오케스트레이션(상태머신)과 브라우저 실행(부작용)은 `ExecutionGateway` 포트(`app/execution/gateway.py`)로 분리**되어 있다. `RunService` 는 불투명하고 **직렬화 가능한** `ExecutionHandle`(frozen `execution_mode` + `session_id` 토큰, 라이브 런타임 참조 없음)만 들고 `open_session`/`run_step`/`submit_input`/`close_session` 을 호출할 뿐, Playwright 도 스레드 풀도 직접 다루지 않는다. 라이브 런타임은 게이트웨이 내부 세션 레지스트리(`_sessions`, `session_id` 키)에만 있어 오케스트레이터/`PendingOtpState` 로 새지 않는다.
- 포트의 현재 구현은 in-process 어댑터 `LocalExecutionGateway`(`app/execution/local_gateway.py`)다. 이 어댑터가 워크플로 실행기를 `execution_mode` 기준으로 `app/systems/loader.py` 로 로드하고, 실제 Playwright sync API 실행을 **세션마다 만든 단일 스레드 `ThreadPoolExecutor`(`max_workers=1`)** 에서 수행한다. 같은 세션의 build/step/submit_input/close 호출이 모두 이 스레드에서 돈다. 실행 스레드 → 이벤트 루프 로그 브리지는 **논블로킹**이다: 실행 스레드는 `loop.call_soon_threadsafe(queue.put_nowait, line)` 로 큐에 넣기만 하고(즉시 반환, 이벤트 루프 완료를 기다리지 않음), `run_step` 안의 async 드레인 태스크가 `asyncio.Queue` 를 FIFO 로 비우며 로그 콜백을 순서대로 호출한다(느린 이벤트 루프가 더는 브라우저 스레드를 라인 단위로 막지 못함; 센티넬로 드레인 완료를 await 하므로 순서·"`module_finished` 이전 로그 flush" 불변식은 유지). HOM·MHM 은 같은 대표홈페이지 시나리오를 공유하므로 공용 `RepHomepageExecutor` 한 클래스에 채널 프로파일(`PC_CHANNEL` / `MOBILE_CHANNEL`)만 주입해 만든다.
- 이 포트가 곧 "워커 경계"의 in-process 구현이다. 동일 포트로 별도 워커 프로세스/Playwright MCP 구현체를 끼우면 오케스트레이터를 손대지 않고 실행을 격리할 수 있다.
- AI 실패 분석·종료 메일 같은 **부수 관심사는 `EventBus`(`app/events/bus.py`) 구독자로 분리**되어 있다. 오케스트레이터는 Run/Suite 종료 시 `RunFinished`/`SuiteFinished` 도메인 이벤트만 발행하고, Gemini/SMTP 의 존재를 모른다.
- 하나의 Run 안에서는 공유 브라우저 세션을 유지한 채 단계형 모듈을 순차 실행한다.
- **Suite** 는 시스템 단위로 Run을 순차 생성한다. 각 시스템 Run은 별도 브라우저 세션을 갖고, Suite는 시스템 간 OTP 대기(`WAITING_INPUT`)를 중계한다.
- 모듈 로그와 상태 이벤트는 repository를 통해 WebSocket에 전파된다.
- Run REST/WS payload는 `RunView.dump` 프로젝션을 거치며, 일일 Run 보존(`RunRetentionScheduler`)·운영 스냅샷(`OpsService`)은 `main.py` lifespan 에서 기동된다.

## 4. 현재 폴더 구조

```text
e2eTester/
  app/
    ai/
      failure_analyzer.py
      gemini_client.py
      gemini_http.py
      gemini_models.py
      gemini_schemas.py
    api/
      dependencies.py              # FastAPI DI providers (get_run_service, get_app_settings, …)
      routes_dashboard.py
      routes_runs.py
      routes_schedules.py
      routes_suites.py
      routes_systems.py
      routes_admin.py
      routes_otp.py
      ws_runs.py
      ws_suites.py
    auth/
      router.py                    # /login, /auth/*, /account/password
      dependencies.py
      jwt.py
      service.py
      models.py
    core/
      enums.py
      env_utils.py
      logging.py                   # structlog 설정
      models.py
      ops_buffer.py                # 운영 이벤트 링 버퍼
      settings.py                  # E2ESettings (pydantic-settings SSOT)
      status_labels.py             # UI 상태 라벨·터미널 outcome·보존 purge 대상
    execution/
      gateway.py                 # ExecutionGateway 포트 + ExecutionHandle (오케스트레이션 ↔ 실행 경계)
      composite_gateway.py       # CompositeExecutionGateway: execution_mode 로 어댑터 라우팅
      local_gateway.py           # LocalExecutionGateway: in-process 어댑터(스레드 풀·런타임 수명·로그 브리지)
      simulated_gateway.py       # SimulatedExecutionGateway: simulated 모드 테스트 더블 어댑터
      run_queue.py               # RunExecutionQueue(+JobQueue 포트): 감독되는 실행 작업 큐(워커 풀)
    events/
      bus.py                     # EventBus + RunFinished/RunWaitingInput/RunResumed/SuiteFinished 도메인 이벤트
      subscribers/
        failure_analysis.py      # FailureAnalysisSubscriber (AI 실패 분석)
        email_notification.py    # EmailNotificationSubscriber (종료 메일)
    notifications/
      run_completion_email.py
      report_renderer.py
    domain/
      run_aggregate.py           # RunAggregate: Run 상태 전이 규칙·불변식(순수 도메인, I/O 무지)
    orchestrator/
      run_service.py             # RunService: 실행 순서·부작용 조율(규칙은 RunAggregate 에 위임)
      run_planner.py             # RunPlanner: 요청 검증 + 모듈 실행 계획(순수)
      run_comparator.py          # RunComparator: 직전 Run 대비 비교(저장소 의존)
      run_event_publisher.py     # RunEventPublisher: 도메인 상태 → DashboardEvent(WS 표현)
      run_view.py                # RunView: Run 읽기 모델 프로젝션(엔티티 직접 직렬화 금지 경계)
      run_summary.py             # summarize_run: 최근 Run 요약 뷰
      run_actor.py               # Run/Suite/예약 실행자 이름 해석(관리자 이력·통계)
      ops_service.py             # OpsService: Run/Suite/스케줄·큐 운영 스냅샷
      stats_charts.py            # Plotly 사용량 통계 차트 JSON 빌더
      suite_view.py              # Suite ACL·비관리자 steps 필터
      suite_service.py           # SuiteService: 이벤트 기반 Saga(RunFinished 구동, 폴링 없음)
      stats_service.py             # StatsService: 사용량·절감 시간 통계(admin)
    registry/
      loader.py
    scheduling/
      cron.py
      scheduler.py
      run_retention.py           # RunRetentionScheduler/Service: 일일 ERROR·CANCELLED 정리
    runner/
      artifact_manager.py
      screenshot.py              # 모듈 종료 시 공용 스크린샷 캡처 (시스템 무관)
      workflow_common.py
      workflow_engine.py         # BaseWorkflowExecutor (공용 실행 골격) + WorkflowRuntime 계약
    scenarios/
      rep_homepage/              # 대표홈페이지(PC·모바일) 공용 시나리오 (채널 무관 1벌)
        constants.py             # 청구 본문 문구 등 도메인 결합 규칙 SSOT
        channel.py               # ChannelProfile / ChannelSteps (채널 어댑터 계약)
        runtime.py               # RepHomepageRuntime (PC·모바일 단일 런타임)
        executor.py              # RepHomepageExecutor (단일 _run_step 시나리오 디스패치)
    systems/
      loader.py                  # execution_mode -> 시스템별 executor 로딩
      hom/
        channel.py               # PC 채널 프로파일(PC_CHANNEL): hom.steps 어댑터 주입
        executor.py              # 얇은 팩토리 (RepHomepageExecutor + PC_CHANNEL)
        manifest.yaml
        scripts/
          login_phone.py         # 수동 실행용 CLI (manifest 워크플로 아님)
        steps/
          login_common.py
          main_access.py
          login_move.py
          phone_login.py
          kakao_login.py
          contract_list.py
          contract_detail.py
          compensation_charge.py
          compensation_result_common.py
          compensation_result.py
          compensation_cancel.py
          long_term_policy_certificate.py
      mhm/
        channel.py               # 모바일 채널 프로파일(MOBILE_CHANNEL): mhm.steps 어댑터 주입(mobile=True)
        executor.py              # 얇은 팩토리 (RepHomepageExecutor + MOBILE_CHANNEL)
        manifest.yaml
        steps/                   # hom 과 동일한 시나리오 계약을 구현하는 모바일 셀렉터 어댑터
          login_common.py
          main_access.py
          login_move.py
          phone_login.py
          kakao_login.py
          contract_list.py
          contract_detail.py
          compensation_charge.py
          compensation_result_common.py
          compensation_result.py
          compensation_cancel.py
          long_term_policy_certificate.py
      access_common/
        browser.py                 # 공용 브라우저 기동/팝업/모바일 모드 헬퍼
        executor.py                # AccessWorkflowExecutor (FP/HRP/HWTC/CHBOT 공통 베이스)
        main_access.py             # main_access 단계
      fp/
        executor.py                # FpWorkflowExecutor
        manifest.yaml
        steps/
      hrp/
        executor.py                # HrpWorkflowExecutor
        manifest.yaml
        steps/
      hwtc/
        executor.py                # HwtcWorkflowExecutor
        manifest.yaml
        steps/
      chbot/
        executor.py                # ChbotWorkflowExecutor
        manifest.yaml
        steps/
    storage/
      ports.py                   # 저장소 포트(Protocol): Run/RunLog/RunControl/RunInput/Suite/SuiteControl/SuiteInput/Schedule
      sqlite_support.py          # JsonTableStore (stdlib sqlite3 + asyncio.to_thread)
      listener_registry.py       # WebSocket 리스너 큐 레지스트리(프로세스-로컬)
      sqlite_run_repository.py   # SQLite Run 상태 어댑터(기본 사용, blob 에 로그 제외)
      sqlite_run_log_store.py    # SQLite 모듈 로그 append-only 어댑터(기본 사용, run_logs 테이블)
      sqlite_run_control_store.py # SQLite Run 제어 상태 어댑터(취소·OTP 재개, run_control 테이블)
      sqlite_suite_repository.py # SQLite Suite 어댑터(기본 사용)
      sqlite_suite_control_store.py # SQLite Suite 제어 상태 어댑터(취소 의도, suite_control 테이블)
      sqlite_schedule_repository.py # SQLite 예약 어댑터(기본 사용)
      sqlite_user_repository.py    # SQLite 사용자 어댑터(기본 사용)
      sqlite_module_settings_repository.py # SQLite 모듈별 수동 업무 시간 설정
      user_repository.py         # UserRepositoryPort(Protocol)
      module_settings_repository.py # ModuleSettingsRepositoryPort(Protocol)
      run_control_store.py       # 인메모리 Run 제어 상태 어댑터
      run_input_store.py         # 인메모리 Run 입력값(PII) 어댑터(기본 사용)
      suite_control_store.py     # 인메모리 Suite 제어 상태 어댑터
      suite_input_store.py       # 인메모리 Suite 시스템별 입력값 어댑터(기본 사용)
      run_repository.py          # 인메모리 Run 어댑터(테스트·영속 불요용)
      run_log_store.py           # 인메모리 모듈 로그 어댑터
      schedule_repository.py     # 인메모리 예약 어댑터
      suite_repository.py        # 인메모리 Suite 어댑터
    web/
      templates/
        base.html
        index.html
        run.html
        suite.html
        login.html
        account/
          password.html
        admin/
          base.html
          index.html
          users.html
          modules.html
          stats.html
          ops.html
      static/
        app.css
        app.js
        admin-ops.js
        admin-stats.js
    main.py
  docs/
    DOCS_GOVERNANCE.md           # 문서 SSOT 매트릭스·PR 체크리스트
    otp_relay.md                 # OTP SMS 중계기(안드로이드) 구성 가이드
    scenarios/
      hom.md
      mhm.md
      fp.md
      hrp.md
      hwtc.md
      chbot.md
  scripts/
    check_docs_consistency.py    # 문서-코드 정합성 가드
  tests/                         # pytest (도메인·설정·ops·retention 등, 브라우저 없음)
    test_run_aggregate.py
    test_run_queue.py
    test_run_retention.py
    test_settings.py
    test_ops_service.py
    test_ops_buffer.py
    test_stats_service.py
    test_stats_charts.py
    test_suite_control_store.py
    test_gemini_client.py
    test_gemini_schemas.py
    test_email_attachment_selection.py
    test_email_inline_images.py
    test_otp_inbound.py
    test_env_utils.py
  .github/
    workflows/
      docs-consistency.yml       # 정합성 가드 CI
    pull_request_template.md      # PR DoD 체크리스트
  research/                      # 1회성 probe 스크립트 (앱 구성 요소 아님)
  artifacts/
  .env.example
  requirements.txt
  README.md
  E2E_ARCHITECTURE.md
```

## 5. 현재 계층별 역할

### 5.1 Web 계층

현재 구현:

- `app/api/routes_dashboard.py`
- `app/api/dependencies.py`
- `app/web/templates/base.html`
- `app/web/templates/index.html`
- `app/web/templates/run.html`
- `app/web/templates/suite.html`
- `app/web/static/app.js`
- `app/web/static/app.css`
- `app/web/templates/admin/ops.html`, `app/web/static/admin-ops.js` (운영 관측)
- `app/web/templates/admin/stats.html`, `app/web/static/admin-stats.js` (사용량 통계 차트)

역할:

- 시스템 카드 렌더링
- **전체 시스템 순차 점검(SUITE)** 카드: 시스템 체크박스 선택, 공통 브라우저 모드, `supported_auth_methods` 가 있는 시스템별 인증 입력 패널(선택된 시스템만), cron 예약 등록
- 조건부 입력 폼 렌더링
- 실행 모듈 선택 그래프(`module-graph`) 렌더링과 의존성 경고
- Run / Suite 화면 렌더링
- WebSocket 수신 후 노드/로그/OTP 패널 갱신

현재 UX 특징:

- 홈 화면은 “시스템 실행”과 “전체 순차 점검”을 함께 제공한다.
- 홈 화면 상단에는 상태 카드 3종(등록 시스템 수, AI 분석 설정 상태, 종료 메일 설정 상태)이 표시된다.
- 홈 화면에는 “진행 중 / 최근 Run” 패널이 있으며 `GET /api/runs` 요약을 주기적으로 불러와 렌더링한다. (SQLite 영속 — 서버 재시작 후에도 이력이 남음)
- 개별 시스템 실행 전 모듈 선택 그래프에서 모듈을 개별 해제할 수 있고, 선택값은 실행 요청의 `selected_module_ids` 로 전달된다.
- **SUITE** 실행 전 시스템 체크박스에서 시스템을 개별 해제할 수 있고, 선택값은 `selected_system_codes` 로 전달된다. 미선택 시스템은 Suite step `SKIPPED` 로 남는다.
- 개별 Run 실행 시 곧바로 Run 상세 화면으로, SUITE 실행 시 Suite 상세 화면(`/suites/{suite_id}`)으로 이동한다.
- 인증 수단처럼 시스템별 실행 옵션은 manifest 의 `run_form` 정의로 렌더링된다.

### 5.2 API 계층

현재 구현:

- `GET /` (홈 대시보드 HTML)
- `GET /login` (로그인 HTML)
- `POST /auth/login` (폼 또는 JSON 로그인 → JWT 쿠키)
- `POST /auth/logout`
- `GET /auth/me`
- `GET /account/password` (비밀번호 변경 HTML)
- `POST /auth/change-password`
- `GET /runs/{run_id}` (Run 상세 HTML)
- `GET /suites/{suite_id}` (Suite 상세 HTML)
- `GET /api/systems`
- `GET /api/runs` (최근 Run 요약 목록, 최대 50건)
- `POST /api/runs/systems/{system_code}`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/nodes`
- `POST /api/runs/{run_id}/otp`
- `POST /api/runs/{run_id}/cancel`
- `POST /api/runs/{run_id}/rerun`
- `GET /api/suites` (최근 Suite 요약 목록)
- `POST /api/suites` (`browser_mode`, `systems`, `selected_system_codes` 로 Suite 생성)
- `GET /api/suites/{suite_id}`
- `POST /api/suites/{suite_id}/cancel`
- `POST /api/suites/{suite_id}/otp` (현재 대기 중인 시스템 Run에 OTP 전달)
- `POST /api/otp/inbound` (SMS 중계기 → 현재 OTP 대기 Run 자동 탐색 후 OTP 주입·재개; 사용자 세션이 아닌 `X-OTP-Relay-Token` 기기 토큰 인증, `E2E_OTP_RELAY_TOKEN` 미설정 시 비활성)
- `GET /api/schedules` (예약 목록 요약, input_data / suite_systems 제외)
- `POST /api/schedules/systems/{system_code}` (개별 시스템 cron 예약 등록)
- `POST /api/schedules/suites` (전체 점검 cron 예약 등록, `selected_system_codes` 포함)
- `POST /api/schedules/{schedule_id}/toggle` (활성/비활성 전환)
- `POST /api/schedules/{schedule_id}/run-now` (즉시 1회 실행)
- `DELETE /api/schedules/{schedule_id}` (예약 삭제)
- `WS /ws/runs/{run_id}`
- `WS /ws/suites/{suite_id}`
- `GET /api/admin/runs` (전체 Run 목록, admin 전용; `system_code`·`user_name` 필터, `limit` 지원)
- `DELETE /api/admin/runs/{run_id}` (Run 영구 삭제 — DB·로그·아티팩트, admin 전용)
- `GET /api/admin/ops/snapshot` (Run/Suite/스케줄·실행 큐·최근 운영 이벤트 스냅샷, admin 전용)
- `GET /api/admin/stats/usage` (사용자·시스템별 사용량 통계, admin 전용)
- `GET /api/admin/stats/savings/csv` (절감 시간 통계 CSV 다운로드, admin 전용)
- `GET /api/admin/systems` (등록 시스템 코드·이름 목록, admin 전용)
- `GET /api/admin/module-settings` (시스템·모듈별 수동 업무 시간 설정 조회, admin 전용)
- `PUT /api/admin/module-settings/systems/{system_code}` (시스템별 수동 업무 시간 벌크 저장, admin 전용)
- `PUT /api/admin/module-settings/{module_id:path}` (모듈별 수동 업무 시간 저장, admin 전용)
- `GET /api/admin/users` (사용자 목록, admin 전용)
- `POST /api/admin/users` (사용자 생성, admin 전용)
- `PATCH /api/admin/users/{user_id}/active` (활성/비활성 전환, admin 전용)
- `DELETE /api/admin/users/{user_id}` (사용자 삭제, admin 전용)
- `PUT /api/admin/users/{user_id}/systems` (사용자 허용 시스템 목록 변경, admin 전용)
- `GET /admin` (관리자 대시보드 HTML)
- `GET /admin/users` (사용자 관리 HTML)
- `GET /admin/stats` (사용량 통계 HTML)
- `GET /admin/ops` (운영 관측 HTML — Run/Suite/스케줄·큐·최근 이벤트)
- `GET /admin/modules` (모듈별 수동 업무 시간 관리 HTML; 시스템 카드당 저장 버튼 1개로 변경분 일괄 저장)

역할:

- 시스템 목록 조회
- 최근 Run 요약 목록 조회 (`list_run_summaries`)
- Run 생성 (`selected_module_ids` 로 실행 모듈 부분 선택 가능)
- Suite 생성 (`selected_system_codes` 로 실행 시스템 부분 선택 가능, 미지정 시 전체)
- Run / Suite / 노드 조회
- OTP 재개 (`POST /api/runs/{run_id}/otp`, Suite 경유 `POST /api/suites/{suite_id}/otp`, SMS 중계 경유 `POST /api/otp/inbound` — run_id 없이 현재 대기 Run 자동 탐색)
- Run 취소 (`POST /api/runs/{run_id}/cancel`) — 진행 중/대기 중 Run을 `CANCELLED` 로 중단
- Suite 취소 (`POST /api/suites/{suite_id}/cancel`) — 진행 중 Suite와 현재 시스템 Run을 함께 중단
- 동일 입력 재실행 (`POST /api/runs/{run_id}/rerun`) — 같은 시스템·입력·모듈 선택으로 새 Run 생성
- 실시간 상태 이벤트 스트리밍

**참고:** OTP API는 Run이 `WAITING_INPUT` 상태로 멈춰 있을 때만 의미가 있다. 어떤 인증 수단이 이 상태를 만드는지는 각 시스템 시나리오 문서를 참고한다.

### 5.3 Orchestrator 계층

현재 구현 핵심은 `app/orchestrator/run_service.py` 다. `RunService` 는 **실행 순서와 부작용 조율**(영속·이벤트 발행·게이트웨이 호출)을 담당하는 애플리케이션 서비스이며, "무엇이 합법한 상태 전이인가"라는 규칙·불변식·상태 변경은 도메인 애그리거트 `RunAggregate` 에 위임한다. Playwright/스레드/Gemini/SMTP 를 전혀 import 하지 않는다(브라우저 없이 단위 테스트 가능).

위임 구조:

- `RunAggregate`(`app/domain/run_aggregate.py`): Run 상태 전이 규칙·불변식의 **단일 소유자**. `Run` 모델을 감싸 `begin`/`block_for_dependencies`/`mark_queued`/`mark_running`/`record_result`/`finish_timing`/`fail_module`/`mark_waiting_input`/`resume_after_input`/`cancel_modules`/`finalize`/`compute_final_status`/`select_failure_target`/`seal_interrupted` 같은 **순수 메서드**(await·I/O 없음, 시계만 참조)를 노출한다. 과거 `RunService._execute_run` 에 흩어져 있던 규칙(선행 모듈 차단·결과 기록·종료 상태 판정·취소 마킹·재기동 봉인)을 이 한곳으로 모아 I/O 없이 단독 단위 테스트한다(`tests/test_run_aggregate.py`).
- `RunPlanner`(`run_planner.py`): 입력값 검증·모듈 선택·인증 수단 검증, manifest 기준 모듈 리스트 생성(순수 로직).
- `ExecutionGateway` 포트: 브라우저 세션 열기/단계 실행/입력 제출/종료. 스레드·런타임은 어댑터가 소유.
- `RunComparator`(`run_comparator.py`): 직전 Run 대비 비교(저장소 의존). 종료 메일이 참조하므로 구독자가 아니라 finalize 시점에 결정적으로 계산.
- `RunEventPublisher`(`run_event_publisher.py`): 도메인 상태를 `DashboardEvent` 로 변환·발행(WS 표현 관심사). Run 본문은 `RunView` 프로젝션을 거친다.
- `RunView`(`run_view.py`): Run 의 **읽기 모델 프로젝션**. REST 응답·WebSocket payload·스냅샷은 엔티티를 직접 `model_dump` 하지 않고 이 프로젝션을 거쳐 나간다(와이어 필드를 명시 선언 → 엔티티에 내부 전용 필드가 생겨도 자동으로 새지 않음). 현재 노출 형태는 기존 `run.model_dump` 와 1:1 동일.
- `suite_view.py`(`suite_view.py`): 비관리자 Suite 요청·응답 ACL — `User.allowed_system_codes` 로 `resolve_suite_request_for_user` 가 선택 시스템을 제한하고, `filter_suite_for_user`/`filter_suite_event_for_user` 가 REST·WS 에서 허용되지 않은 `SuiteStep` 을 숨긴다.
- `OpsService`(`ops_service.py`): 관리자 운영 관측(`/admin/ops`)용 Run/Suite/스케줄·실행 큐·최근 운영 이벤트 스냅샷.
- `stats_charts.py`(`stats_charts.py`): `StatsService` 가 사용하는 Plotly 차트 JSON 빌더(사용량 통계 HTML).
- `run_actor.py`(`run_actor.py`): Run/Suite/예약의 실행자(사용자) 이름·이메일 해석 — 관리자 이력·통계 표시용.
- `EventBus` 구독자: AI 실패 분석·종료 메일(부수 관심사).
- `summarize_run`(`run_summary.py`): 최근 Run 요약 뷰.

오케스트레이터가 (도메인 애그리거트에 위임해) 담당하는 책임:

- 모듈 상태 전이 관리, 의존성 실패 시 `BLOCKED` 처리
- OTP 대기 상태 저장: 재개 컨텍스트(직렬화 세션 토큰 + resume index + module id)를 `RunControlStorePort`(기본 `SqliteRunControlStore`)에 영속한다. 더 이상 서비스-인스턴스 메모리 dict 가 아니다 — OTP 제출 시 토큰으로 핸들을 복원해 중단된 단계부터 재개한다. OTP 값 자체는 저장하지 않고 게이트웨이가 런타임에 직접 주입한다.
- Run 취소(`cancel_run`): 취소 의도를 `RunControlStorePort` 에 영속(취소 컬럼과 pending 컬럼이 분리돼 동시 갱신 충돌 없음)하고, 실행 루프가 모듈 사이에서 이를 **스토어에서 최신값으로 읽어** 협력적으로 중단한다. 진행 중인 단계는 끝나거나 timeout 된 뒤 멈추며, 남은 모듈은 `CANCELLED` 로 표시한다. OTP 입력 대기 중에는 루프가 돌지 않으므로 즉시 세션을 정리하고 종료한다.
- 동일 입력 재실행(`rerun_run`): Run 생성 시 `RunInputStorePort` 에 보관한 입력값(otp_code 미포함)으로 같은 시스템·모듈 선택의 새 Run을 만든다. 입력값은 PII 라 Run blob/이벤트 payload 로 직렬화하지 않고 전용 스토어에만 둔다(Phase 1 기본 인메모리; 암호화 SQLite 어댑터를 끼우면 재기동 후 rerun 까지 가능).
- Run 종료(finalize) 시 `RunFinished` 도메인 이벤트 발행

현재 상태 전이:

Run:

- `PENDING`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED` (정상)
- `ANOMALY` (이상징후 — 모듈 실패·비정상 종료)
- `ERROR` (점검실패 — 도구/환경 오류)
- `FAILED` (레거시 SQLite 호환; 신규 기록에는 사용하지 않으며 UI 에서는 `ANOMALY` 와 동일 라벨)
- `CANCELLED` (사용자가 취소한 Run)

Module:

- `PENDING`
- `QUEUED`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED`
- `ANOMALY`
- `ERROR`
- `FAILED` (레거시 호환; UI 에서는 `ANOMALY` 와 동일 라벨)
- `BLOCKED`
- `SKIPPED`
- `CANCELLED` (Run 취소로 실행되지 않거나 중단된 모듈)

아직 없는 것:

- 재시도 정책
- 실패 모듈만 부분 재실행 (현재는 `rerun_run` 으로 동일 입력 전체 재실행만 지원)

### 5.3.1 Suite Orchestrator 계층

현재 구현 핵심은 `app/orchestrator/suite_service.py` 다. **이벤트 기반 Saga(프로세스 매니저)** 로 동작한다 — 과거의 `_execute_suite` 백그라운드 루프(하위 Run 의 WebSocket 이벤트 큐 구독 + `get_run` 2초 폴링으로 종료 감지)는 제거됐다.

역할:

- `selected_system_codes` 검증·정규화 (`_resolve_selected_system_codes`, `None` 이면 전체 선택)
- 선택된 시스템에 대해서만 `RunService.validate_run_request` 호출 (HOM 해제 시 HOM 인증 입력 불필요)
- 등록된 모든 시스템에 대해 `SuiteStep` 생성, 미선택 시스템은 `SKIPPED`
- `start_suite` 는 첫 스텝의 Run 만 시작한다. 이후 각 스텝은 직전 스텝의 **`RunFinished` 도메인 이벤트**를 받은 `on_run_finished` 핸들러가 시작한다(`display_order` 순차, `triggered_by="suite"`, `suite_id` 태깅). `register(event_bus)` 로 `RunFinished`/`RunWaitingInput`/`RunResumed` 를 구독한다.
- 한 시스템 Run이 실패해도 다음 선택 시스템은 계속 실행
- 시스템 Run의 OTP 일시정지/재개는 `RunWaitingInput`/`RunResumed` 도메인 이벤트로 Suite `WAITING_INPUT`/`RUNNING` 에 반영한다(폴링·WS 큐 구독 없음). OTP 는 `POST /api/suites/{suite_id}/otp` → `RunService.submit_otp` 로 제출.
- **취소 의도는 영속**(`SuiteControlStorePort`, 기본 `SqliteSuiteControlStore`): `cancel_suite` 가 플래그를 세우고 활성 Run 을 취소 → `RunFinished(CANCELLED)` → Saga 가 나머지 스텝을 `CANCELLED` 로 마감. Saga 는 다음 스텝 진입 전에 이 플래그를 스토어에서 최신값으로 읽는다(서비스-인스턴스 메모리 set `_cancel_requested` 제거).
- 시스템별 입력값은 `SuiteInputStorePort`(기본 `InMemorySuiteInputStore`)가 소유한다(PII 를 Suite blob 에 싣지 않음, `RunInputStore` 와 동일 패턴).
- Suite 단위 임계영역은 `suite_id` 키 `asyncio.Lock` 으로 직렬화한다(이벤트 핸들러/advance 동시 접근 방지).
- Suite 종료 시 `SuiteFinished` 도메인 이벤트를 발행해 통합 결과 메일 1통 발송(`EmailNotificationSubscriber`); Suite 소속 개별 Run 종료 메일은 생략

Suite / SuiteStep 상태:

Suite:

- `PENDING`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED` (선택된 시스템이 모두 통과)
- `ANOMALY` (선택된 시스템 중 하나라도 이상징후 종료)
- `ERROR` (선택된 시스템 중 하나라도 점검실패 종료)
- `FAILED` (레거시 호환)
- `SKIPPED` (전체 Suite 가 선택 제외된 경우 등)
- `CANCELLED`

SuiteStep (시스템 단위):

- 위 상태 + `SKIPPED` (사용자가 시스템 선택에서 제외)

### 5.3.2 인증·ACL

- `User.allowed_system_codes`(`app/auth/models.py`): 비관리자가 실행·조회할 수 있는 시스템 코드 목록. 관리자는 전체 접근.
- 홈 대시보드(`routes_dashboard.py`): 비관리자에게는 허용된 시스템 카드만 노출.
- Suite 생성·조회(`suite_view.py`): `resolve_suite_request_for_user` 가 `selected_system_codes` 를 허용 범위로 제한하고, REST/WS 는 `filter_suite_for_user`/`filter_suite_event_for_user` 로 허용되지 않은 step 을 숨긴다.
- 관리자 사용자 ACL: `PUT /api/admin/users/{user_id}/systems` 로 허용 시스템 목록 변경.

### 5.4 Registry 계층

현재 구현:

- `app/registry/loader.py` (`app/systems/*/manifest.yaml` 글롭 로드 — 기본 포함 6시스템: `hom`, `mhm`, `fp`, `hrp`, `hwtc`, `chbot`)

역할:

- 시스템 정의 로드 (`display_order` 오름차순, 동률은 `system_code` 순)
- Run form 정의 로드
- 모듈 메타데이터 로드
- manifest 정합성 검증: `module_id` 중복, 모듈의 `system_code` 불일치, 알 수 없는 `depends_on`, 의존성 순서(선행 모듈 `order`가 더 작아야 함), 의존성 순환을 로드 시점에 검사하고 위반 시 `ValueError`

manifest 에 들어 있는 정보:

- 시스템 코드, 이름, 설명
- 폼 필드 정의
- `show_when` 기반 조건부 노출 규칙
- 모듈 순서와 의존성
- `workflow_step`
- 모듈별 `timeout_seconds`

실행 규칙:

- 모듈은 `order` 오름차순으로 순차 실행된다.
- `depends_on` 은 추가 실행 제약이며, 선행 모듈이 모두 `PASSED` 여야 다음 모듈이 실행된다.
- 실행 요청에는 선택된 모듈 집합(`selected_module_ids`)이 포함될 수 있다.
- 선택되지 않은 모듈은 Run 모델에 남겨 두되 `SKIPPED` 상태로 표시하고, 실제 실행 루프에는 들어가지 않는다.
- 잘못된 조합(선행 모듈 없이 후행 모듈만 선택)은 프런트에서 경고할 수 있지만 최종적으로는 `RunService.start_run` 에서 거부한다.

시스템별 실제 모듈 목록과 단계별 동작은 각 시스템 시나리오 문서(`docs/scenarios/`)를 참고한다.

### 5.5 Runtime / Runner 계층

이 계층은 `ExecutionGateway` 포트 뒤에 있다. 오케스트레이터는 포트만 보고, 실제 구현은 어댑터들이 캡슐화한다. 오케스트레이터는 실행/시뮬레이션을 구분하지 않고 단일 포트(`CompositeExecutionGateway`)만 호출하며, 합성 게이트웨이가 `execution_mode` 로 담당 어댑터를 고른다.

현재 구현:

- `app/execution/gateway.py` (`ExecutionGateway` 포트 + `ExecutionHandle`: 오케스트레이션 ↔ 실행 경계)
- `app/execution/composite_gateway.py` (`CompositeExecutionGateway` — 여러 어댑터를 `execution_mode` 로 라우팅하는 합성 게이트웨이. `supports`/`open_session` 은 모드 인자로, 세션 수명 메서드는 핸들의 `execution_mode` 로 어댑터 선택. 어댑터 목록 배선은 컴포지션 루트 `app/main.py` 가 소유)
- `app/execution/local_gateway.py` (`LocalExecutionGateway` — in-process 어댑터: `app/systems/loader.py` 로 executor 로딩, 세션별 단일 스레드 풀·런타임 수명·이벤트 루프↔실행 스레드 로그 브리지 소유)
- `app/execution/simulated_gateway.py` (`SimulatedExecutionGateway` — `execution_mode == "simulated"` 모듈을 브라우저 없이 매니페스트의 `simulated_duration_ms`/`simulated_outcome` 대로 처리하는 테스트 더블 어댑터. 시뮬레이션 로직이 더 이상 오케스트레이터에 인라인되지 않고 같은 포트 뒤의 어댑터로 분리됨)
- `app/systems/loader.py` (`execution_mode` → 시스템별 executor 로딩)
- `app/runner/workflow_engine.py` (`BaseWorkflowExecutor` — 시스템 무관 실행 골격: 로그 캡처·아티팩트 수집·예외→`StepExecutionResult` 변환·OTP 일시정지(`WAITING_INPUT_PREFIX`) 해석·브라우저 종료 보호. `WorkflowRuntime` 최소 계약 Protocol)
- `app/scenarios/rep_homepage/executor.py` (`RepHomepageExecutor(BaseWorkflowExecutor)`) — **대표홈페이지 PC·모바일 공용 시나리오 실행기**. 워크플로(메인접속→로그인→계약목록→계약상세→보험금청구→결과확인→취소→증명서)와 `_run_step` 디스패치가 채널 무관하게 단 한 번만 존재한다. PC/모바일 차이는 생성자에 주입되는 `ChannelProfile` 로만 표현한다.
- `app/scenarios/rep_homepage/channel.py` (`ChannelProfile` / `ChannelSteps`) — 채널(드라이버) 기술서와 셀렉터 어댑터 계약. `app/scenarios/rep_homepage/constants.py` 는 청구 본문 문구 등 charge↔result↔cancel 도메인 결합 규칙의 SSOT.
- `app/systems/hom/channel.py` (`PC_CHANNEL`) / `app/systems/hom/executor.py` (`create_executor` 얇은 팩토리, `execution_mode = "hom_workflow_step"`) — PC 채널 어댑터(`hom.steps`) 주입.
- `app/systems/mhm/channel.py` (`MOBILE_CHANNEL`, `mobile=True`) / `app/systems/mhm/executor.py` (`create_executor` 얇은 팩토리, `execution_mode = "mhm_workflow_step"`) — 모바일 채널 어댑터(`mhm.steps`) 주입.
- `app/systems/access_common/executor.py` (`AccessWorkflowExecutor(BaseWorkflowExecutor)`, FP/HRP/HWTC/CHBOT 공통 베이스 — `main_access` + 시스템별 `_run_step` 확장)
- `app/systems/fp/executor.py` (`FpWorkflowExecutor`) / `app/systems/hrp/executor.py` (`HrpWorkflowExecutor`) / `app/systems/hwtc/executor.py` (`HwtcWorkflowExecutor`) / `app/systems/chbot/executor.py` (`ChbotWorkflowExecutor`)
- `app/runner/workflow_common.py` (`StepExecutionResult`, 로그 라인 기록 `LineWriter` / `write_log_line`)
- `app/runner/artifact_manager.py`
- `app/systems/{system_code}/steps/` 아래 분할 모듈 파일들 — 각 채널이 공용 시나리오에 주입하는 셀렉터 어댑터

실행 모델:

- Run 단위로 Playwright 런타임 생성 (영속 프로파일 persistent context)
- 하나의 browser/context/page를 공유
- 모바일 채널(`ChannelProfile.mobile=True`, 예: MHM)은 공용 `build_runtime()` 에서 페이지 생성 직후 `apply_mobile_device_mode()` 로 모바일 디바이스 모드를 먼저 적용한 뒤 접속
- 단계형 모듈을 순차 실행 (manifest의 `workflow_step` → 공용 시나리오 실행기의 `_run_step` 디스패치, 채널은 `ChannelProfile.steps` 어댑터로 주입)
- 표준 출력/표준 에러를 가로채 모듈별 `execution.log` 와 라이브 WebSocket 로그로 저장
- 휴대폰인증 단계는 OTP 미입력 시 `WAITING_INPUT::` 표식을 반환해 Run을 일시정지시킴

이 구조를 택한 이유:

- 로그인 이후 세션을 다음 모듈에 전달해야 함
- 휴대폰 본인인증에서는 OTP 제출 이후에도 동일 세션으로 로그인 완료까지 이어져야 함
- 계약목록·계약상세·보험금청구·보험금청구 결과 조회/취소 등 후속 모듈은 동일 세션이 필요함

### 5.6 Storage 계층

저장소는 `ExecutionGateway` 와 같은 **포트-어댑터** 구조다. 오케스트레이터/스케줄러는 구체 구현이 아니라 `app/storage/ports.py` 의 포트(`RunRepositoryPort`/`RunLogStorePort`/`RunControlStorePort`/`RunInputStorePort`/`SuiteRepositoryPort`/`SuiteControlStorePort`/`SuiteInputStorePort`/`ScheduleRepositoryPort`)에만 의존하므로, 인메모리 ↔ 영속(SQLite) 어댑터를 무수정으로 교체할 수 있다. 제어 상태(취소 의도·OTP 재개)와 입력값(PII)은 상태 blob 과 분리된 형제 스토어가 소유한다 — Run 은 `RunControlStorePort`/`RunInputStorePort`, Suite 는 `SuiteControlStorePort`/`SuiteInputStorePort`.

**집합체(aggregate) 경계:** Run **상태**(status·모듈 전이·comparison)와 **모듈 로그**는 서로 다른 집합체다. 로그는 한 줄씩 추가되는 고빈도 텔레메트리라, Run blob 을 통째로 다시 쓰는 대신 `RunLogStorePort` 의 append-only 스토어에 한 줄당 한 번 INSERT 한다. **영속 Run blob 에는 모듈 로그가 담기지 않으며**(어댑터의 `save_run` 이 `model_dump_json(exclude=...)` 으로 방어적으로 제외), 읽기 시 `RunService.get_run` 이 로그 스토어에서 로그를 읽어 Run 읽기 모델에 하이드레이션한다(쓰기 모델/읽기 모델 분리). 이로써 로그 한 줄마다 Run 전체를 재직렬화하던 핫패스 쓰기(O(N²))가 사라지고, Run blob 쓰기는 상태 전이 시점으로만 한정된다.

현재 구현:

- `app/storage/ports.py` — 저장소 포트(Protocol) 정의 (`RunRepositoryPort` 는 Run 상태만, `RunLogStorePort` 는 로그 스트림만 책임)
- `app/storage/sqlite_support.py` — `JsonTableStore`(stdlib `sqlite3` + `asyncio.to_thread`, JSON blob 테이블) · `DEFAULT_DB_PATH`
- `app/storage/listener_registry.py` — `ListenerRegistry`(run_id/suite_id 별 WebSocket 리스너 큐, 프로세스-로컬 휘발성)
- `app/storage/sqlite_run_repository.py` / `sqlite_suite_repository.py` / `sqlite_schedule_repository.py` — **기본 사용되는 SQLite 어댑터**(`app/main.py` 에서 주입)
- `app/storage/sqlite_run_log_store.py` — **기본 사용되는** 모듈 로그 append-only SQLite 어댑터(`run_logs` 테이블, 한 줄당 한 행, `ORDER BY id` 로 입력 순서 복원)
- `app/storage/run_repository.py` / `suite_repository.py` / `schedule_repository.py` — 인메모리 어댑터(단위 테스트·영속 불요 실행용)
- `app/storage/run_log_store.py` — `InMemoryRunLogStore`(로그 스트림 인메모리 어댑터)
- `app/storage/user_repository.py` / `module_settings_repository.py` — `UserRepositoryPort`/`ModuleSettingsRepositoryPort`(Protocol)
- `app/storage/sqlite_user_repository.py` / `sqlite_module_settings_repository.py` — SQLite 어댑터(기본 사용, 사용자·모듈별 수동 업무 시간)

역할:

- Run / Suite / 예약(Schedule) **상태** 객체 저장 (Pydantic 모델을 JSON 으로 직렬화해 `id` PK 테이블에 저장; Run blob 은 모듈 로그를 제외)
- 모듈 로그 스트림 저장 (`(run_id, module_id)` 키의 append-only)
- WebSocket listener 큐 관리(프로세스-로컬 휘발성)

특징과 제약:

- **영속:** Run/Suite/예약 본체는 SQLite 파일(`E2E_DB_PATH`, 기본 `data/e2etester.db`)에 저장돼 서버 재시작 후에도 이력·상태·예약이 남는다. **모듈 로그도 같은 DB 파일의 `run_logs` 테이블에 append-only 로 영속**되며, Run blob 과는 분리돼 있다. 읽기 시 Run 모델에 하이드레이션된다.
- **휘발:** WebSocket 리스너 큐는 살아있는 연결에 묶인 프로세스-로컬 상태라 영속화하지 않는다(라이브 로그 전파는 `module_log` 이벤트가 담당). 인메모리 어댑터를 쓰면 로그 스트림도 휘발한다.
- **재기동 정리:** 서버가 내려갈 때 진행 중이던 Run/Suite(RUNNING·WAITING_INPUT)는 브라우저 세션·OTP 핸들이 사라져 이어받을 수 없으므로, 기동 시 `RunService.reconcile_interrupted_runs`/`SuiteService.reconcile_interrupted_suites` 가 이를 `CANCELLED` 로 봉인한다(인메모리 어댑터에서는 복원될 대상이 없어 no-op). 과거로 밀린 예약은 `SchedulerService` 가 다음 cron 시각으로 재계산해 시작 직후 일괄 실행을 막는다.

### 5.7 AI 실패 분석 계층

현재 구현:

- `app/events/subscribers/failure_analysis.py` (`FailureAnalysisSubscriber` — `EventBus` 의 `RunFinished` 구독자)
- `app/ai/failure_analyzer.py` (`GeminiFailureAnalyzer`)
- `app/ai/gemini_client.py` (Gemini API 클라이언트·모델 체인 호출)
- `app/ai/gemini_schemas.py` (실패 분석·메일 콘텐츠용 Pydantic 스키마)
- `app/ai/gemini_http.py` (Gemini HTTP 호출 / SSL 검증 모드 처리)
- `app/ai/gemini_models.py` (기본 Gemini 모델 체인 `DEFAULT_GEMINI_MODEL_CHAIN`·`GEMINI_MODELS` 파싱/검증)
- `app/core/settings.py` (`E2ESettings`, pydantic-settings — 환경변수·기본값 SSOT; `env_utils.py` 는 레거시 호환 주석만 유지)

역할:

- 환경 변수와 `.env` 기준으로 Gemini 설정을 읽는다. (터미널 환경 변수 우선, 없으면 `.env`)
- **부수 관심사로 분리됨**: 오케스트레이터가 인라인으로 호출하지 않고, Run 종료(`RunFinished`) 이벤트를 받은 구독자가 실패 모듈을 사후 분석한다. 분석에 필요한 진단 정보(현재 URL·다이얼로그·스크린샷)는 단계 실행 시점에 `RunModule`(`current_url`/`dialog_messages`/아티팩트)에 영속되므로, 구독자는 실행 컨텍스트 없이 종료된 Run 만으로 분석을 재구성한다.
- 분석 결과가 준비되면 해당 모듈을 갱신·저장하고 `module_finished` 이벤트를 다시 발행해 대시보드가 반영하도록 한다(계약상세는 PII 보호를 위해 URL/로그/다이얼로그/스크린샷을 보내지 않음).
- 홈 화면에 현재 AI 분석 설정 상태(`inspect_env_status`)를 표시한다.

제약:

- 기본값은 비활성화다.
- 설정이 잘못되어도 앱은 계속 실행되며, 실패 분석만 생략될 수 있다.
- 회사망 SSL 검사 환경에서는 `E2E_GEMINI_SSL_VERIFY=false` 로 Gemini 호출의 SSL 검증만 우회할 수 있다.

### 5.8 종료 메일 알림 계층

현재 구현:

- `app/events/subscribers/email_notification.py` (`EmailNotificationSubscriber` — `EventBus` 의 `RunFinished`/`SuiteFinished` 구독자)
- `app/notifications/run_completion_email.py` (`RunCompletionEmailNotifier`, `GeminiReportContentComposer`)
- `app/notifications/report_renderer.py` (고정 디자인 HTML 렌더러)

역할:

- **부수 관심사로 분리됨**: 오케스트레이터/Suite 서비스가 인라인으로 보내지 않고, `RunFinished`/`SuiteFinished` 이벤트를 받은 구독자가 발송 정책(취소 Run 제외, Suite 소속 Run 은 통합 메일로 갈음)까지 소유한다.
- Run이 터미널 종료(`PASSED`/`ANOMALY`/`ERROR`; 레거시 `FAILED` 포함)되면 Gmail SMTP로 결과 메일을 보낸다. (`WAITING_INPUT` 등 중간 상태에서는 보내지 않음)
- **Suite** 가 최종 종료되면 포함 시스템 Run 결과를 통합한 메일 1통을 보낸다. `SKIPPED` 시스템은 제외로 표시한다.
- 수신자는 시스템(채널)별 환경 변수 `E2E_EMAIL_RECIPIENTS_{SYSTEM_CODE}` 로 구분한다. (예: `E2E_EMAIL_RECIPIENTS_HOM`, `E2E_EMAIL_RECIPIENTS_MHM`, `E2E_EMAIL_RECIPIENTS_FP`, … — 여러 명은 `|` 로 구분)
- Suite 메일 수신자는 실행된(선택된) 시스템들의 수신자 집합을 합친다.
- **메일 본문 HTML은 항상 `report_renderer` 의 고정 템플릿으로 결정적으로 렌더링한다.** 디자인(레이아웃·색·간격)은 코드에 박혀 있어 매 실행 동일하다. Gemini(`GeminiReportContentComposer`)는 HTML 이 아니라 분석 '콘텐츠'(핵심 요약·모듈별 화면/로그 관찰·실패 분석)만 구조화 JSON 으로 생성해 템플릿에 채운다. Gemini 가 비활성/실패면 동일 템플릿이 AI 서술 없이(결정적 기본 문구로) 렌더링되므로 디자인은 그대로 유지된다.
- 홈 화면에 현재 메일 알림 설정 상태(`inspect_env_status`)를 표시한다.

제약:

- 기본값은 비활성화다.
- 설정이 잘못되어도 앱은 계속 실행되며, 메일 발송만 생략될 수 있다.

### 5.9 예약 실행(스케줄러)과 이력 비교 계층

현재 구현:

- `app/scheduling/cron.py` — 외부 의존성 없는 최소 cron(5필드 `분 시 일 월 요일`) 파서·다음 실행 시각 계산기. `* , - /` 와 요일 0/7(일요일)을 지원하고, 일·요일이 모두 제한되면 둘 중 하나만 맞아도 실행하는 표준 cron 규칙을 따른다.
- `app/scheduling/scheduler.py` (`SchedulerService`) — 예약 CRUD 와, cron 기준으로 Run/Suite 를 자동 생성하는 백그라운드 루프(`run_forever`). `app/main.py` lifespan 에서 task 로 띄우고 종료 시 정리한다.
- `app/storage/sqlite_schedule_repository.py` (`SqliteScheduleRepository`, 기본 사용) / `app/storage/schedule_repository.py` (`InMemoryScheduleRepository`) — 예약 저장소. SQLite 어댑터는 `ScheduleRepositoryPort` 를 구현해 재시작 후에도 예약이 남는다.
- `app/api/routes_schedules.py` — 예약 REST API.
- `app/scheduling/run_retention.py` (`RunRetentionScheduler`, `RunRetentionService`) — 매일 cron 시각에 **당일 00:00(기준 타임존) 이전**의 `ERROR`·`CANCELLED` Run 을 삭제한다. `PASSED`·`ANOMALY` 는 유지. 환경변수 `E2E_RUN_RETENTION_ENABLED`/`E2E_RUN_RETENTION_CRON`(의미·기본값은 `README.md`, 예시는 `.env.example`).

역할:

- 홈 화면 시스템 폼에서 입력값·모듈 선택 그대로 cron 식을 붙여 **개별 시스템** 예약을 등록한다. 등록 시 `RunService.validate_run_request` 로 검증한다.
- 홈 SUITE 카드에서 브라우저 모드·시스템 선택(`selected_system_codes`)·선택된 시스템별 인증 정보와 함께 **전체 점검** 예약을 등록한다 (`POST /api/schedules/suites`). 등록 시 `SuiteService.validate_suite_request` 로 검증한다.
- 예약은 `schedule_kind` 가 `system`(개별 Run) 또는 `suite`(전체 점검) 이다.
- 예약은 활성/비활성 전환, 즉시 실행(`run-now`), 삭제가 가능하다. 예약 트리거 Run 은 `triggered_by="schedule"`, `schedule_id` 로 태깅되고, Suite 예약은 `triggered_by="suite"` Run 들을 순차 생성한다.
- 백그라운드 루프는 주기적으로(기본 20초) `next_run_at` 이 지난 활성 예약을 찾아 실행하고 다음 시각을 다시 계산한다. 직전 예약 Run/Suite 가 아직 진행 중이면 중복 실행을 건너뛴다.
- 기준 타임존은 `E2E_SCHEDULE_TZ`(기본 `Asia/Seoul`).
- **이력 비교**: Run 이 터미널 종료(`PASSED`/`ANOMALY`/`ERROR`; 레거시 `FAILED` 포함)되면 `RunComparator`(`app/orchestrator/run_comparator.py`, `RunService` 에 주입)가 같은 시스템의 직전 종료 Run 을 기준선으로 `newly_failed`(새로 실패)/`recovered`(복구)/`still_failing`(계속 실패) 모듈을 계산해 `Run.comparison` 에 담는다. (종료 메일이 참조하므로 이벤트 구독자가 아니라 finalize 시점에 결정적으로 계산한다.) Run 화면의 "직전 실행 대비 변화" 패널과 종료 메일(고정 템플릿의 "직전 실행 대비 변화" 섹션 · Gemini 콘텐츠 프롬프트 · 평문)에 반영된다.

제약:

- 예약은 SQLite 에 영속되어 재시작 후에도 남는다. 비교 기준선은 같은 시스템의 직전 종료 Run(역시 영속) 을 조회해 계산하므로, 재시작 후에도 이력만 있으면 정상 동작한다. 단, 서버 다운 중 지나간 예약은 catch-up 하지 않고 다음 cron 시각으로 미룬다.
- 예약 실행은 무인 실행이라, 휴대폰/카카오 인증처럼 사람 개입이 필요한 단계가 포함되면 해당 Run/Suite 는 `WAITING_INPUT` 에서 멈출 수 있다.
- 입력값(`input_data`, `suite_systems`)은 PII 를 포함할 수 있어 예약 요약(API/UI)에는 직렬화하지 않는다. Suite 예약 요약에는 `selected_system_count`, `step_total` 등 선택 시스템 수만 노출한다.

## 6. 시스템 시나리오 문서

시스템별 테스트 시나리오(워크플로우 단계, 모듈 목록, 화면별 검증 항목, 입력 모델)는 이 문서에 직접 쓰지 않고, 시스템마다 개별 문서로 분리해 관리한다.

규칙:

- 위치: `docs/scenarios/{system_code}.md`
- manifest(`app/systems/{system_code}/manifest.yaml`)와 1:1로 대응한다.
- 새 시스템(FP, HRP, HWTC, CHBOT 등)을 추가할 때는 manifest와 함께 시나리오 문서도 같이 추가한다.
- 시나리오 문서에는 시스템 개요, 모듈 목록, 단계별 상세 동작(selector·URL 검증 포함), Run form 입력 모델을 기록한다.
- 시스템의 흐름이나 selector 를 바꾸면 해당 시나리오 문서도 함께 갱신한다.
- **전체 순차 점검(SUITE)** 에서의 시스템 포함/제외는 시나리오 문서가 아니라 홈 SUITE 카드·`selected_system_codes` 로 제어한다. SUITE 실행 시 각 시스템은 모듈 부분 선택 없이 manifest 전체 모듈이 실행된다.

현재 작성된 시나리오 문서:

- [HOM (한화손해보험 샘플)](docs/scenarios/hom.md)
- [MHM (모바일 대표홈페이지)](docs/scenarios/mhm.md)
- [FP (영업가족 위촉서류 등록 / PC)](docs/scenarios/fp.md)
- [HRP (현장출동 홈페이지 / PC)](docs/scenarios/hrp.md)
- [HWTC (연수원 / PC)](docs/scenarios/hwtc.md)
- [CHBOT (챗봇 / 모바일)](docs/scenarios/chbot.md)

## 7. 현재 UI 입력 모델

홈 화면의 시스템 실행 카드 입력 폼은 각 시스템 manifest 의 `run_form` 정의로 렌더링된다.

**SUITE 카드** 추가 입력:

- 공통 `browser_mode` (`headed` / `headless`)
- `selected_system_codes` (체크박스, 기본 전체 선택)
- HOM/MHM `systems.{code}` 인증 필드 (해당 시스템이 선택된 경우만 표시·검증)

공통 규칙:

- 현재 사용 중인 필드 타입은 `text` / `select` 다.
- `show_when` 으로 다른 필드 값에 따른 조건부 노출을 정의한다.
- `required`, `default`, `placeholder`, `help_text` 를 지원한다.

시스템별 실제 입력 항목과 조건부 노출 규칙은 각 시스템 시나리오 문서를 참고한다.

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

- 워크플로 단계 모듈(`hom_workflow_step` / `mhm_workflow_step`)은 로그를 `execution.log` 로 남긴다.
- 스크린샷(`final.png`)은 **공용 실행 엔진**이 책임진다. 개별 단계 함수는 스크린샷을 직접 찍지 않으며, `BaseWorkflowExecutor.execute_step` 이 각 모듈 종료 시점(성공·실패 공통)에 `runtime.page` 로 한 번 캡처한다(`app/runner/screenshot.py`의 `capture_screenshot`). 모든 등록 시스템(HOM/MHM/FP/HRP/HWTC/CHBOT)에 동일하게 적용된다.
- 캡처는 로그 리다이렉트 안에서 수행되므로 스크린샷 관련 로그도 `execution.log` / WebSocket 으로 함께 남는다.
- 표준 캡처 → 폰트 폴백 재시도 → CDP 폴백 순으로 시도하며, 캡처가 모두 실패해도 단계 성공/실패 판정에는 영향을 주지 않는다(예외를 삼킨다).
- Run 화면에서 아티팩트 링크 노출
- 링크 경로는 `/artifacts/{run_id}/{module_id}/{filename}` 형식이다.

주의:

- 사용자 입력 대기(`WAITING_INPUT`, 예: 휴대폰 OTP 대기)는 모듈 종료가 아니라 일시정지이므로 그 시점에는 스크린샷을 찍지 않는다. OTP 제출 후 모듈이 실제로 끝날 때 캡처된다.
- 초기 단계에서 페이지/브라우저 자체가 깨지면 스크린샷이 없을 수 있다.
- `ModuleDefinition.execution_mode` 의 기본값은 `simulated` 지만 현재 등록된 시스템 manifest는 모두 워크플로 단계 모드를 쓰므로 시뮬레이션 경로는 사용되지 않는다. 시뮬레이션은 `SimulatedExecutionGateway`(포트 어댑터)가 `execution_mode == "simulated"` 모듈에 한해 `simulated_duration_ms`/`simulated_outcome` 대로 처리하며, 아티팩트는 생성되지 않는다. 실제 실행기가 없는 **알 수 없는** `execution_mode` 는 더 이상 조용히 시뮬레이션되지 않고 `open_session` 에서 예외가 나 해당 모듈이 명확히 FAILED 처리된다.

아직 없는 것:

- `fail.png`
- `dom.html`
- `trace.zip`
- `result.json`

## 9. 현재 이벤트 모델

WebSocket으로 흐르는 주요 이벤트:

Run (`/ws/runs/{run_id}`):

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

Suite (`/ws/suites/{suite_id}`):

- `snapshot`
- `suite_created`
- `suite_started`
- `suite_step_started`
- `suite_step_run_linked` — 단계 Run 생성 직후 (`active_run_id`, `step.run_id` 확정). Suite UI가 Run WebSocket에 연결해 모듈 진행률을 실시간 표시하는 시점
- `suite_step_finished`
- `suite_waiting_input`
- `suite_resumed`
- `suite_finished`

현재 payload 특징:

- Run 이벤트·REST 응답 본문은 `RunView.dump(run)` (`app/orchestrator/run_view.py`; `RunEventPublisher`, `ws_runs.py`, `routes_runs.py` 경유) — 엔티티 `run.model_dump` 직접 사용 안 함
- Suite 이벤트는 `suite.model_dump(mode="json")` (+ `step_index` 등 보조 필드). 비관리자에게는 `suite_view.filter_suite_event_for_user` 로 허용되지 않은 step 이 필터링될 수 있음
- Module 이벤트는 `module` 스냅샷과 `run_status`
- Log 이벤트는 `module_id`, `message`

## 10. 현재 구현과 초기 목표의 차이

초기 목표는 `웹 트리거형 실행 플랫폼` 이었고, 현재 샘플은 그 방향에 맞는 첫 단계까지 구현되어 있다. 다만 아래는 아직 목표 상태가 아니다.

### 10.1 아직 구현되지 않은 것

- Postgres 등 다중 프로세스/원격 영구 저장소 (SQLite 단일 파일 영속은 **구현됨** — 포트로 분리돼 있어 어댑터만 추가하면 됨)
- 별도 worker process (단, `ExecutionGateway` 포트로 **교체 지점은 이미 마련됨** — `LocalExecutionGateway` 를 out-of-process 구현체로 바꾸면 됨)
- Playwright MCP 게이트웨이 구현체 (포트는 `ExecutionGateway` 로 이미 존재)
- `ModuleContext`, `ModuleResult` 표준화
- 병렬 실행 스케줄러 (영속 프로파일 단일 잠금 때문에 현재는 순차 전제)
- 재시도 정책
- 실패 모듈만 부분 재실행 (취소·동일 입력 전체 재실행은 구현됨)
- 오류 분류 체계

### 10.2 이미 방향이 맞는 것

- 웹 트리거 방식
- manifest 기반 시스템/모듈 로딩
- 모듈별 노드 대시보드
- 실시간 이벤트 스트림
- 아티팩트 분리 저장
- **저장소 포트-어댑터 분리 + SQLite 영속** (`app/storage/ports.py` + `Sqlite*Repository`; Run/Suite/예약이 재시작 후에도 유지, 진행 중 실행은 기동 시 정리)
- 모놀리식 스크립트의 단계 모듈 분리
- 로그인 세션 공유형 워크플로우
- **오케스트레이션 ↔ 브라우저 실행 분리** (`ExecutionGateway` 포트 + `LocalExecutionGateway` 어댑터; 워커 경계의 in-process 구현)
- **부수 관심사(AI 분석·메일) 이벤트 구독자 분리** (`EventBus` + 구독자)
- **상태머신 단위 테스트 가능** (`RunService` 가 Playwright/스레드/Gemini/SMTP 비의존)

## 11. 왜 현재 구조가 합리적인가

현재 구현은 일부 이상적인 구조를 의도적으로 미뤘다. 이유는 다음과 같다.

- 실제 사이트 흐름을 먼저 안정화하는 것이 중요했다.
- 로그인, OTP, 팝업, 후속 GNB 탐색처럼 상태를 공유해야 하는 흐름이 많아서, 초기에는 공유 세션 기반 직렬 모듈 구조가 가장 현실적이었다.
- SQLite, 워커, MCP abstraction을 한 번에 넣으면 디버깅 복잡도가 급격히 올라간다.

즉, 현재 샘플은 “플랫폼의 골격”과 “현실적인 사이트 자동화 로직”을 먼저 맞춘 버전이다.

## 12. 다음 단계 권장안

### Phase 1. 현재 샘플 안정화

- 로그인 후 팝업 종료 안정성 보강 (휴대폰·카카오 공통)
- 카카오 인증 팝업·동의 UI 변경에 대한 selector·대기 조건 보강
- 계약목록·계약상세 조회 selector 보강
- 실패 시 디버그 아티팩트 확장 (`trace.zip`, `dom.html` 등)

### Phase 2. 저장소와 실행 모델 개선 — (대부분 완료)

- ✅ 저장소 포트(`app/storage/ports.py`) 도입 + `InMemory*Repository` 를 `Sqlite*Repository`(SQLite 영속)로 교체
- ✅ 서버 재시작 복구 시나리오: 진행 중 Run/Suite 는 기동 시 `CANCELLED` 로 봉인, 과거 예약은 다음 cron 시각으로 재계산
- 남은 작업: OTP 대기 상태는 살아있는 브라우저 세션에 묶여 영구 저장으로 이어받을 수 없음(재실행으로 대체). 다중 프로세스가 필요하면 Postgres 어댑터 추가

### Phase 3. 런타임 추상화 — (대부분 완료)

- ✅ `ExecutionGateway` 포트 도입 (`BrowserGateway` 역할)
- ✅ sync API 호출·스레드 모델·런타임 수명을 gateway(`LocalExecutionGateway`) 뒤로 이동
- 남은 작업: Playwright MCP 구현체 추가 (포트는 이미 존재하므로 새 어댑터만 작성)

### Phase 4. 실행 분리

- Web 프로세스와 Worker 프로세스 분리 (`ExecutionGateway` 의 out-of-process 구현체로 교체; 오케스트레이터 무수정)
- timeout, kill, concurrency 정책 추가
- 시스템/계정 단위 동시 실행 제어 (영속 프로파일 격리 필요)

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
```

```text
Backend
  -> WebSocket Event Hub
  -> Persistent Run State Store
  -> Artifact Store
  -> Module Registry
```

> **진행 상태:** 위 목표 중 `Run Orchestrator → BrowserGateway → Browser` 경계는 이미 `ExecutionGateway` 포트(+`LocalExecutionGateway`)로 구현되었고, `Worker Process` 만 아직 in-process 다(동일 포트로 교체 가능). 부수 관심사 분리(`EventBus`)도 완료. `Persistent Run State Store` 도 저장소 포트(`app/storage/ports.py`) + SQLite 어댑터로 구현됐다(단일 파일; 다중 프로세스용 원격 저장소는 어댑터 추가로 확장). 남은 큰 축은 out-of-process 워커다.

이 목표 구조로 가면 아래가 가능해진다.

- 서버 재시작 후 Run 상태 유지
- 실행 격리
- 병렬도 제어
- 테스트 모듈과 브라우저 구현 분리 (✅ `ExecutionGateway` 로 달성)
- Playwright MCP 기반 이관 (포트 준비 완료)

## 14. 결론

현재 소스코드는 단순한 Playwright 스크립트 모음이 아니라, 이미 웹 트리거형 E2E 플랫폼의 최소 실행 골격을 갖춘 샘플이다.

정리하면 현재 상태는 아래다.

- 웹에서 시스템 실행 가능
- **전체 시스템 순차 점검(Suite)** 과 시스템별 선택 실행 가능
- 실시간 모듈 노드 대시보드 존재
- 입력 대기(`WAITING_INPUT`) pause/resume 구조 존재 (Run·Suite)
- 로그인 이후 후속 모듈 실행 구조 존재
- manifest 기반 확장 포인트 존재

앞으로의 핵심 작업은 “새 모듈 추가” 자체보다, 현재 구조를 깨지 않고 저장소, 워커, MCP abstraction을 점진적으로 넣는 것이다.
