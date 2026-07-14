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
  -> FastAPI app (app/main.py — lifespan만; 배선은 AppContainer)
      -> AppContainer (app/composition/container.py — 컴포지션 루트: 저장소·게이트웨이·OutboxRelay·서비스 조립)
      -> RunService (실행 순서 + 부작용 조율만)
          -> ProfilePartitionedRunQueue / JobQueuePort (execution_profile 별 동시성: heavy/light/interactive)
          -> RunStateMachine / RunAggregate (app/domain/ — 결정 전이표 + 상태 변이·불변식, 순수)
          -> RunSnapshot / SuiteSnapshot (app/domain/snapshots.py — aggregate.to_snapshot() 읽기 전용 스냅샷)
          -> ModuleRegistry           (app/registry/loader.py + systems/*/manifest.yaml, execution_profile 포함)
          -> RunWriteRepositoryPort + RunLogStorePort + RunControlStorePort + RunInputStorePort
          -> CQRS 조회 포트(app/orchestrator/queries/ 질의 핸들러가 소비): RunSummaryQueryPort / ModuleHistoryQueryPort / SuiteSummaryQueryPort / AnomalyInboxQueryPort / DailyStatusQueryPort / StatsQueryPort (projection 테이블, blob 미접근)
          -> ExecutionGateway PORT    (app/execution/gateway.py — 오케스트레이션 ↔ 실행 경계)
              -> CompositeExecutionGateway (execution_mode 로 어댑터 라우팅)
                  -> WorkerExecutionGateway (→ 워커 SessionServer) / SimulatedExecutionGateway
                      -> WorkflowExecutor + app/automation/ (Flow + PageObject — systems/*/steps/ 삭제됨)
                          -> Shared Playwright browser session → Site
          -> SqliteRunWriteRepository + transactional outbox
              -> OutboxRelay → ProjectionHandlers + EventBus + RealtimeProjector (단일 알림 파이프라인)

OutboxRelay → EventBus 구독자
  -> SuiteService (이벤트 기반 Saga)
      -> SuiteStateMachine / SuiteAggregate / RunCommandPort
  -> FailureAnalysisSubscriber / EmailNotificationSubscriber

FastAPI app
  -> HTML routes / JSON APIs / WebSocket stream (WS payload는 OutboxRelay→RealtimeProjector 경유)
  -> Static artifacts mount
```

현재 구조의 핵심 특징:

- 웹 요청과 실행 orchestration은 같은 프로세스에 있다. 단, **오케스트레이션(상태머신)과 브라우저 실행(부작용)은 `ExecutionGateway` 포트(`app/execution/gateway.py`)로 분리**되어 있다. `RunService` 는 불투명하고 **직렬화 가능한** `ExecutionHandle`(frozen `execution_mode` + `session_id` 토큰, 라이브 런타임 참조 없음)만 들고 `open_session`/`run_step`/`submit_input`/`close_session` 을 호출할 뿐, Playwright 도 스레드 풀도 직접 다루지 않는다. 라이브 런타임은 게이트웨이 내부 세션 레지스트리(`_sessions`, `session_id` 키)에만 있어 오케스트레이터/`PendingOtpState` 로 새지 않는다.
- 포트의 실 브라우저 구현은 워커 프로세스의 세션 호스트 `SessionServer`(`worker/session_server.py`)이며, API 는 `WorkerExecutionGateway`(`app/execution/worker_gateway.py`)로 HTTP 위임한다(실행 평면 분리 — API 프로세스에는 Playwright·실행 스레드가 없다; 구 in-process `LocalExecutionGateway` 는 폐기). `SessionServer` 가 워크플로 실행기를 `execution_mode` 기준으로 `app/systems/loader.py` 로 로드하고, 실제 Playwright sync API 실행을 **세션마다 만든 단일 스레드 `ThreadPoolExecutor`(`max_workers=1`)** 에서 수행한다. 같은 세션의 build/step/submit_input/close/capture_storage_state 호출이 모두 이 스레드에서 돈다. **이 스레드 풀은 세션의 `_Session`(명시적 "워커 경계" 객체)이 소유한다 — 과거처럼 `runtime.executor` 로 도메인 런타임에 몽키패치하지 않는다.** 예전에는 모든 시스템 런타임 dataclass 와 `WorkflowRuntime` Protocol 이 오직 게이트웨이를 위해 `executor` 필드를 들고 있어야 했다(인프라 관심사가 도메인 런타임으로 누수). 이제 풀은 세션에만 있고, `close_session` 이 세션이 소유한 풀을 정리한다. 실행 스레드 → 이벤트 루프 로그 브리지는 **논블로킹**이다: 실행 스레드는 `loop.call_soon_threadsafe(queue.put_nowait, line)` 로 큐에 넣기만 하고(즉시 반환, 이벤트 루프 완료를 기다리지 않음), `run_step` 안의 async 드레인 태스크가 `asyncio.Queue` 를 FIFO 로 비우며 로그 콜백을 순서대로 호출한다(느린 이벤트 루프가 더는 브라우저 스레드를 라인 단위로 막지 못함; 센티넬로 드레인 완료를 await 하므로 순서·"`module_finished` 이전 로그 flush" 불변식은 유지). HOM·MHM 은 같은 대표홈페이지 시나리오를 공유하므로 공용 `RepHomepageExecutor` 한 클래스에 채널 프로파일(`PC_CHANNEL` / `MOBILE_CHANNEL`)만 주입해 만든다.
- 이 포트가 곧 "워커 경계"의 in-process 구현이다. 동일 포트로 별도 워커 프로세스/Playwright MCP 구현체를 끼우면 오케스트레이터를 손대지 않고 실행을 격리할 수 있다.
- **세션 체크포인트(Phase C)**: 라이브 브라우저 세션은 프로세스-로컬이라 재기동/워커 교체 시 소실된다. `ExecutionGateway.capture_storage_state`(기본 no-op, 지원 어댑터만 구현)로 모듈 경계·OTP 일시정지 시 Playwright `storage_state`(쿠키+localStorage)를 캡처해 `SessionCheckpointStorePort`(암호화 SQLite `session_checkpoints`)에 저장한다. 재기동 시 `RunService.reconcile_interrupted_runs` 는 체크포인트가 있는 Run 을 봉인하지 않고 이어받는다(WAITING_INPUT 은 그대로 두어 `submit_otp` 가 재개, 그 외는 재개 잡 재발행). 복원 상태가 무효(로그인 만료)면 `RunStateMachine.decide_rehydration` 이 로그인 모듈부터 재실행하도록 결정한다(순수 규칙). 로컬 통합 기동은 `scripts/run_local.py`(API + 워커 동시 기동, `E2E_EXECUTION_MODE=remote`, Redis 필수).
- AI 실패 분석·종료 메일 같은 **부수 관심사는 `EventBus`(`app/events/bus.py`) 구독자로 분리**되어 있다. 오케스트레이터는 Run/Suite 종료 시 `RunFinished`/`SuiteFinished` 도메인 이벤트만 발행하고, Gemini/SMTP 의 존재를 모른다.
- 하나의 Run 안에서는 공유 브라우저 세션을 유지한 채 단계형 모듈을 순차 실행한다.
- **Suite** 는 시스템 단위로 Run을 순차 생성한다. 각 시스템 Run은 별도 브라우저 세션을 갖고, Suite는 시스템 간 OTP 대기(`WAITING_INPUT`)를 중계한다.
- **상태 전이 이벤트**는 **OutboxRelay → RealtimeProjector** 단일 파이프라인을 통해 WebSocket에 전파된다(오케스트레이터가 저장소 리스너에 직접 publish 하지 않음). **모듈 로그는 예외다(WP-B5)**: 로그는 도메인 이벤트가 아니라 유실 허용 가능한 고빈도 스트림이므로, 이벤트 스토어·아웃박스·프로젝션을 경유하지 않고 `RunService._handle_module_log` 가 `RunLogStorePort`(영속)와 실시간 채널(`module_log` DashboardEvent)에 **직접** 넣는다.
- **이벤트 = 진실의 원천(WP-B2/B3)**: Run 상태는 `domain_events` 스트림에서 유도된다. `app/domain/run_decider.py` 의 순수 함수 `decide(cmd, state) → events` / `evolve(state, event) → state` 가 커맨드를 이벤트로, 이벤트를 상태로 접는다(`rebuild_state` = 스트림 전체 폴드). 각 이벤트는 스트림 내 단조 `stream_position`(낙관적 동시성 좌표, `UNIQUE(aggregate_type, aggregate_id, stream_position)`)을 갖고, `aggregate_snapshots` 테이블은 이 폴드의 **파생 캐시**일 뿐이다 — `scripts/rebuild_snapshots.py --validate`(CI `snapshot_validate` 게이트)가 "이벤트 폴드 == 라이브 스냅샷"을 상시 실증한다. 레거시 blob 은 `scripts/migrate_blob_to_events.py` 가 `RunImported` genesis 이벤트 + 스냅샷으로 1회 이관한다(FAILED→ANOMALY 정규화 포함).

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
      dependencies.py              # FastAPI Depends 프로바이더 (HTTP·WS 공용, app.state 직접 접근 금지)
      routes_dashboard.py          # HTML 페이지 라우트 (/, /runs/execute, /runs/history, /schedules, /anomalies, /insights, /self-healing, /admin/*)
      routes_daily.py              # 일간 점검 현황 데이터 API (/api/dashboard/daily)
      routes_runs.py
      routes_presets.py            # 인증 프리셋 CRUD (/api/presets)
      routes_suites.py
      routes_systems.py
      routes_schedules.py
      routes_trigger.py            # 모바일 즉시 점검 (/m/{trigger_token}, /api/trigger/*)
      routes_anomalies.py          # 이상징후 인박스 (/api/anomalies*)
      routes_insights.py           # 시스템 인사이트 (/api/systems/{code}/health|timeline|modules/breakdown)
      routes_healing.py            # 자가 치유 센터 (/api/healing/*)
      routes_admin.py
      routes_otp.py                # SMS 중계 인바운드 OTP (/api/otp/inbound)
      ws_runs.py
      ws_suites.py
    contexts/identity/             # 인증·사용자(identity) 컨텍스트 (구 app/auth)
      router.py                    # /login, /auth/*, /account/password
      dependencies.py
      jwt.py
      service.py
      models.py
    core/
      enums.py                     # RunStatus/SuiteStatus/ModuleStatus (PASSED/ANOMALY/ERROR/...)
      env_utils.py
      logging.py                   # 구조적 로거 + 로그 컨텍스트 바인딩
      system_models.py             # ModuleDefinition/SystemDefinition/RunForm* (매니페스트 정적 구조)
      run_models.py                # Run/RunModule/FailureAnalysis/RunComparison/PendingExecution/DashboardEvent
      suite_models.py              # SuiteRun/SuiteStep/SuiteEvent
      schedule_models.py           # Schedule/ScheduleChangeEntry (+ record_change/to_summary/to_detail)
      preset_models.py             # AuthPreset (+ to_public)
      stats_models.py              # UsageStats/SystemUsageStat/UserUsageStat/ModuleSettings
      requests.py                  # HTTP 요청 DTO (StartRunRequest 등 — 공유 커널, api 역방향 의존 회피)
      ops_buffer.py                # 최근 운영 이벤트 링 버퍼(관리자 운영 관측)
      settings.py                  # E2ESettings (환경변수 기반 설정)
      status_labels.py             # 상태 라벨·집계 분류(정상/이상징후/점검실패) SSOT
    contexts/                      # 바운디드 컨텍스트(WP-B1) — 컨텍스트별 domain/application/views
      run/
        domain/
          aggregate.py             # RunAggregate: Run 상태 전이 규칙·불변식(순수, I/O 무지)
          state_machine.py         # RunStateMachine: Run 실행 결정 전이표 + decide_rehydration(순수)
          decider.py               # Run Decider: decide/evolve/rebuild_state (순수, 이벤트=진실)
          commands.py              # RunCommand 군(decide 입력 의도)
        application/
          service.py               # RunService: 실행 순서·부작용 오케스트레이션(결정=StateMachine, 변경=Aggregate 위임)
          comparator.py            # RunComparator: 직전 Run 대비 비교(저장소 의존)
          planner.py               # RunPlanner: 선택 모듈·실행 순서 계획
          command_port.py          # RunCommandPort: suite saga 가 의존하는 Run 커맨드 포트(Protocol)
          event_publisher.py       # RunEventPublisher: 도메인 상태 → DashboardEvent(WS 표현)
        views/
          view.py                  # RunView: Run 읽기 모델 프로젝션(엔티티 직접 직렬화 금지 경계)
          summary.py               # summarize_row: 최근 Run 요약 뷰(행 기반)
          actor.py                 # resolve_run_actor: 표시·집계용 실행자(user) 해석
          module_view.py           # ModuleView: 모듈 읽기 모델 프로젝션
      suite/
        domain/
          aggregate.py             # SuiteAggregate: Suite 상태 전이 규칙·불변식(순수, RunAggregate 와 동형)
          state_machine.py         # SuiteStateMachine: Suite 사가 결정 전이표(순수)
          decider.py               # Suite Decider: decide(cmd,state)→events / evolve (순수, 이벤트=진실)
          commands.py              # SuiteCommand 군(BeginSuite/StartStep/... — decide 입력 의도)
        application/
          service.py               # SuiteService: 이벤트 기반 Saga(결정=StateMachine, 변경=Aggregate 위임)
        views/
          view.py                  # SuiteView: Suite 읽기 모델 프로젝션(RunView 와 동일 규율)
    domain/                        # 공유 도메인 커널(run+suite 공용)
      events.py                    # 도메인 이벤트 카탈로그(Run/Suite/RunImported)
      execution_policy.py          # ModuleExecutionPolicy / SystemExecutionPolicy (재시도·부분재실행·execution_profile)
      snapshots.py                 # RunSnapshot / SuiteSnapshot (frozen, aggregate.to_snapshot())
      summary_fields.py            # run_summary_fields / suite_summary_fields (fat event 요약)
    composition/
      container.py                 # AppContainer — 컴포지션 루트(저장소·게이트웨이·OutboxRelay·서비스 배선)
    eventsourcing/
      event_store.py               # SqliteEventStore (domain events append-only)
      outbox.py                    # SqliteOutbox (transactional outbox)
      relay.py                     # OutboxRelay → projection · EventBus · RealtimeProjector
      support.py                   # SqliteDatabase + projection 스키마
    projections/
      handlers.py                  # ProjectionHandlers (CQRS read-model 테이블 갱신)
    realtime/
      adapter.py                   # RealtimeNotificationPort 구현
      projector.py                 # RealtimeProjector (OutboxRelay가 WS fan-out 담당)
      ports.py                     # RealtimeNotificationPort
      redis_fanout.py              # Redis pub/sub fan-out (다중 API 프로세스)
    events/
      bus.py                       # EventBus + RunFinished/RunWaitingInput/RunResumed/SuiteFinished 도메인 이벤트
      subscribers/
        failure_analysis.py        # FailureAnalysisSubscriber (AI 실패 분석)
        email_notification.py      # EmailNotificationSubscriber (종료 메일)
    execution/
      gateway.py                   # ExecutionGateway 포트 + ExecutionHandle (오케스트레이션 ↔ 실행 경계)
      results.py                   # StepExecutionResult: 실행 결과 계약(WP-C4 — runner 에서 이관)
      session_checkpoint.py        # SessionCheckpointStorePort + SessionCheckpoint (모듈 경계 내구 체크포인트)
      composite_gateway.py         # CompositeExecutionGateway: execution_mode 로 어댑터 라우팅
      worker_gateway.py            # WorkerExecutionGateway: worker/ HTTP API 클라이언트(실 브라우저 실행을 워커 SessionServer 로 위임)
      simulated_gateway.py         # SimulatedExecutionGateway: simulated 모드 테스트 더블 어댑터
      profile_queue.py             # ProfilePartitionedRunQueue: execution_profile 별 JobQueue 라우팅
      job_queue_port.py            # JobQueuePort / JobDescriptor (execution_profile 태깅)
      protocol.py                  # 워커 HTTP 프로토콜 DTO (OpenSession/RunStep/resume-from-step 등)
      run_queue.py                 # RunExecutionQueue(+JobQueue 포트): 감독되는 실행 작업 큐(워커 풀)
    contexts/healing/              # 자가 치유 컨텍스트
      engine.py                    # SelfHealingEngine: 셀렉터 파싱→DOM 스캔→후보 검증→오버라이드(실행 스레드)
      selector_healer.py           # 순수 스코어러: 깨진 셀렉터 파싱·요소 지문·후보 신뢰도
      page_proxy.py                # HealedPage/HealedFrame: 런타임 오버라이드 적용 프록시
      metrics.py                   # 복구 콘솔 KPI·만성 지점 승격(순수 빌더)
      durability.py                # 셀렉터 내구성 맵: steps 소스 정적 스캔 + 치유 이력 결합(순수 빌더)
      patch_builder.py             # 셀렉터 오토픽스 diff 생성(순수 빌더)
      models.py                    # HealingAttempt/정책·패치 모델 + 기본 신뢰도 임계치
      ports.py                     # HealingRecorderPort (어댑터 → 기록 위임 포트)
      service.py                   # HealingService: 치유 기록·정책·패치 얇은 I/O 인터프리터
    notifications/
      run_completion_email.py
      report_renderer.py
    contexts/insights/application/ # 운영 인텔리전스 컨텍스트(읽기 전용 — 프로젝션 소비)
      insights_service.py          # InsightsService: 운영 인텔리전스 얇은 I/O 인터프리터
      insights_anomalies.py        # 이상징후 인박스 목록 도출(순수 빌더)
      insights_health.py           # 시스템 헬스 대시보드(순수 빌더)
      insights_timeline.py         # 시스템 수직 타임라인(순수 빌더)
      insights_breakdown.py        # 모듈 딥다이브(순수 빌더)
      insights_charts.py           # 인사이트 Plotly figure JSON 구성
      insights_common.py           # 인사이트 공용 헬퍼
      stats_service.py             # StatsService: 사용량·절감 시간 통계(admin)
      stats_charts.py              # 통계 차트 데이터 구성
      ops_service.py               # OpsService: Run/Suite/스케줄·큐 운영 스냅샷(admin)
      daily_dashboard.py           # 일간 점검 현황 집계(순수 빌더, GET /api/dashboard/daily)
    contexts/preset/application/
      service.py                   # PresetService: 인증 프리셋(사용자별 격리·검증 후 저장)
    orchestrator/                  # 공유 CQRS 질의 계층(run/suite/insights/preset/healing 서비스는 contexts/ 로 이동됨)
      queries/                     # RunQueries / DailyDashboardQueries (읽기 전용 질의 핸들러)
    registry/
      loader.py
    contexts/scheduling/           # 예약 컨텍스트
      cron.py
      scheduler.py
      schedule_center.py           # 예약 점검 관리 센터 순수 빌더(관제 보드·캘린더·이력 통계)
      run_retention.py             # 일일 점검실패·취소 Run 보존 정리 배치
      command_port.py              # ScheduleRunQueryPort 등 스케줄러 의존 포트
    automation/                    # Automation BC (Flow + PageObject 4-layer)
      ports.py                     # AutomationPort / AutomationContext / Flow
      scenario_engine.py           # workflow_step → Flow 디스패치
      wiring.py                    # 시스템별 ScenarioEngine 팩토리
      flows/
        rep_homepage/              # 대표홈페이지 시나리오 Flow
          access_flow.py
          login_flow.py
          contract_flow.py
          compensation_flow.py
        access/                    # 접속 점검 공용 Flow
          access_flow.py
          login_flow.py
        fp/
        hrp/
        hwtc/
        chbot/
      page_objects/
        hom/
        mhm/
        fp/
        hrp/
        hwtc/
        chbot/
      scenarios/
        rep_homepage/
          constants.py             # 청구 본문 문구 등 도메인 결합 규칙 SSOT
      fixtures/                    # 계약 테스트용 최소 HTML
    platform/                      # 공유 인프라·기술 유틸(특정 컨텍스트 무소속)
      artifact_manager.py          # 아티팩트 경로·파일 관리(실행 평면 아님 — 오케스트레이션이 경로 계산)
    runner/                        # 실행 평면(Playwright 구동 — contexts/api 는 import 금지, AG-009)
      screenshot.py                # 모듈 종료 시 공용 스크린샷 캡처 (시스템 무관)
      step_outcome.py              # StepOutcome 타입드 결과 (StepCompleted/StepNeedsInput)
      workflow_common.py           # write_log_line + StepExecutionResult 재노출(계약은 execution/results.py)
      workflow_engine.py           # BaseWorkflowExecutor (공용 실행 골격) + WorkflowRuntime 계약
    scenarios/
      rep_homepage/                # 대표홈페이지(PC·모바일) 공용 시나리오 (채널 무관 1벌)
        constants.py               # → app/automation/scenarios/rep_homepage/constants.py shim
        channel.py                 # ChannelProfile / ChannelSteps (PageObject 어댑터 계약)
        runtime.py                 # RepHomepageRuntime (PC·모바일 단일 런타임)
        executor.py                # RepHomepageExecutor (런타임 기동; 단계는 automation Flow)
    systems/
      loader.py                    # execution_mode -> executor 로딩 + ScenarioEngine 부착
      hom/
        channel.py                 # PC 채널 프로파일(PC_CHANNEL): hom PageObject 주입
        executor.py                # 얇은 팩토리 (RepHomepageExecutor + PC_CHANNEL)
        manifest.yaml
        scripts/
          login_phone.py           # 수동 실행용 CLI (manifest 워크플로 아님)
      mhm/
        channel.py                 # 모바일 채널 프로파일(MOBILE_CHANNEL): mhm PageObject 주입
        executor.py                # 얇은 팩토리 (RepHomepageExecutor + MOBILE_CHANNEL)
        manifest.yaml
      access_common/
        browser.py                 # 공용 브라우저 기동/팝업/모바일 모드 헬퍼
        executor.py                # AccessWorkflowExecutor (FP/HRP/HWTC/CHBOT 공통 베이스)
        main_access.py             # main_access 단계
      fp/
        executor.py                # FpWorkflowExecutor
        manifest.yaml
      hrp/
        executor.py                # HrpWorkflowExecutor
        manifest.yaml
      hwtc/
        executor.py                # HwtcWorkflowExecutor
        manifest.yaml
      chbot/
        executor.py                # ChbotWorkflowExecutor
        manifest.yaml
    storage/
      ports.py                     # 저장소 포트(Protocol): Run/RunLog/RunControl/RunInput/Suite/SuiteControl/SuiteInput/Schedule 등
      records.py                   # 영속 DTO + 매퍼(RunRecord/SuiteRecord 등): 도메인 ↔ 온디스크 스키마 분리, 로그 제외는 타입 수준
      sqlite_support.py            # JsonTableStore (stdlib sqlite3 + asyncio.to_thread)
      listener_registry.py         # WebSocket 리스너 큐 레지스트리(프로세스-로컬)
      sqlite_run_write_repository.py # RunWriteRepositoryPort + outbox 동시 기록
      sqlite_run_summary_query.py  # RunSummaryQueryPort (run_history_index 화면형 행, SQL 필터/정렬/페이지)
      sqlite_module_history_query.py # ModuleHistoryQueryPort (module_history_index 모듈 실행 이력 행)
      sqlite_suite_summary_query.py # SuiteSummaryQueryPort (suite_history_index 요약 행)
      in_memory_run_summary_query.py # RunSummaryQueryPort 인메모리 어댑터(테스트 전용)
      sqlite_anomaly_inbox_query.py # AnomalyInboxQueryPort
      sqlite_daily_status_query.py # DailyStatusQueryPort
      sqlite_stats_query.py        # StatsQueryPort (stats_rollup + run/module 이력 행, blob 미접근)
      sqlite_run_log_store.py      # SQLite 모듈 로그 append-only 어댑터(기본 사용, run_logs 테이블)
      sqlite_run_control_store.py  # SQLite Run 제어 상태 어댑터(취소·OTP 재개, run_control 테이블)
      sqlite_suite_repository.py   # SQLite Suite 어댑터(기본 사용)
      sqlite_suite_control_store.py # SQLite Suite 제어 상태 어댑터(취소 의도, suite_control 테이블)
      sqlite_schedule_repository.py # SQLite 예약 어댑터(기본 사용)
      sqlite_user_repository.py    # SQLite 사용자 어댑터(기본 사용)
      sqlite_preset_repository.py  # SQLite 인증 프리셋 어댑터(auth_presets 테이블, PII 의도 영속)
      sqlite_anomaly_handling_store.py # SQLite 이상건 처리상태 어댑터(anomaly_handling 테이블)
      sqlite_healing_stores.py     # SQLite 치유 이벤트/정책/패치 어댑터 + 동기 정책 리더
      sqlite_module_settings_repository.py # SQLite 모듈별 수동 업무 시간 설정
      module_settings_repository.py # ModuleSettingsRepositoryPort + 인메모리 어댑터
      user_repository.py           # 인메모리 사용자 어댑터(테스트용)
      run_control_store.py         # 인메모리 Run 제어 상태 어댑터
      run_input_store.py           # 인메모리 Run 입력값(PII) 어댑터(기본 사용)
      suite_control_store.py       # 인메모리 Suite 제어 상태 어댑터
      suite_input_store.py         # 인메모리 Suite 시스템별 입력값 어댑터(기본 사용)
      run_repository.py            # 인메모리 Run 어댑터(테스트·영속 불요용)
      run_log_store.py             # 인메모리 모듈 로그 어댑터
      schedule_repository.py       # 인메모리 예약 어댑터
      suite_repository.py          # 인메모리 Suite 어댑터
    web/
      templates/
        base.html
        dashboard.html             # 일간 점검 현황 대시보드 (로그인 후 첫 화면)
        execute.html               # 시스템 단위 점검 실행 (Run 트리거 UI)
        run.html
        runs_history.html          # 당일 이전 Run 이력
        suite.html
        schedules.html             # 예약 점검 관리 센터
        anomalies.html             # 이상징후 인박스
        insights.html              # 시스템 인사이트
        self_healing.html          # 자가 치유 센터
        mobile_trigger.html        # 모바일 즉시 점검 (JWT 불필요, 토큰 인증)
        login.html
        account/
          password.html
        admin/
          base.html
          index.html
          users.html
          modules.html
          ops.html                 # 운영 관측
          stats.html
      static/
        app.css
        app.js                     # 실행 화면(execute)·Run/Suite 화면 공용 스크립트
        dashboard.js               # 일간 대시보드 렌더링
        schedules.js               # 예약 관리 센터 (페이지 전용)
        anomalies.js               # 이상징후 인박스 (페이지 전용)
        insights.js                # 시스템 인사이트 (페이지 전용)
        healing.js                 # 자가 치유 센터 (페이지 전용)
        admin-ops.js
        admin-stats.js
        favicon.ico / favicon.svg / apple-touch-icon*.png
    main.py                        # FastAPI 앱 팩토리 + lifespan (AppContainer.start/stop 위임)
  worker/
    main.py                        # out-of-process 브라우저 워커 진입점
    http_server.py                 # ExecutionGateway HTTP surface (resume-from-step 포함)
    session_server.py              # SessionServer: 유일한 in-process Playwright 세션 호스트(스레드 풀·런타임 수명·로그 브리지·storage_state 캡처/복원)
  docs/
    DOCS_GOVERNANCE.md             # 문서 SSOT 매트릭스·PR 체크리스트
    CI.md                          # GitHub Actions·게이트 계층·branch protection 운영
    otp_relay.md                   # OTP SMS 중계기 구성 가이드
    ARCHITECTURE_REVIEW_IDEAL.md   # 아키텍처 냉정 평가 (시점 고정 스냅샷 + 적용 현황 부록)
    scenarios/
      hom.md
      mhm.md
      fp.md
      hrp.md
      hwtc.md
      chbot.md
  scripts/
    check_docs_consistency.py      # 문서-코드 정합성 가드
    check_architecture_gates.py    # 아키텍처 정책 게이트 (AG-001~003)
    ci/
      gates.py                     # CI 게이트 SSOT
      run_all_gates.py             # 로컬 pre-PR 전체 게이트 실행
  tests/                           # 순수 계층 단위 테스트 (브라우저/외부 사이트 불필요, CI 실행)
  .github/
    workflows/
      ci.yml                       # CI: docs·architecture·ruff·pytest·(조건부) security
    dependabot.yml
    pull_request_template.md       # PR DoD 체크리스트
  research/                        # 1회성 probe 스크립트 (앱 구성 요소 아님)
  artifacts/
  .env.example
  requirements.txt
  requirements-dev.txt             # 개발/CI 의존성 (pytest·ruff)
  pyproject.toml                   # ruff·pytest 설정
  README.md
  E2E_ARCHITECTURE.md
  CLAUDE.md
```

## 5. 현재 계층별 역할

### 5.1 Web 계층

현재 구현:

- `app/api/routes_dashboard.py`
- `app/api/routes_daily.py` (일간 점검 현황 데이터 API)
- `app/web/templates/base.html`
- `app/web/templates/dashboard.html` (일간 점검 현황 대시보드 — 로그인 후 첫 화면)
- `app/web/templates/execute.html` (시스템 단위 점검 실행 — 기존 홈의 Run 트리거 UI)
- `app/web/templates/run.html`
- `app/web/templates/suite.html`
- `app/web/static/app.js`
- `app/web/static/dashboard.js` (일간 대시보드 렌더링 — 라디얼 링·세그먼트 바·카운트업 애니메이션)
- `app/web/static/app.css`

역할:

- 시스템 카드 렌더링
- **전체 시스템 순차 점검(SUITE)** 카드: 시스템 체크박스 선택, 공통 브라우저 모드, `supported_auth_methods` 가 있는 시스템별 인증 입력 패널(선택된 시스템만), cron 예약 등록
- 조건부 입력 폼 렌더링
- 실행 모듈 선택 그래프(`module-graph`) 렌더링과 의존성 경고
- Run / Suite 화면 렌더링
- WebSocket 수신 후 노드/로그/OTP 패널 갱신

현재 UX 특징:

- 로그인 후 첫 화면은 **일간 점검 현황 대시보드**(`GET /`, `dashboard.html`)다. 접근 가능한 전체 시스템·모듈의 오늘(KST) 점검 상태를 전체 통과율 히어로 링·KPI 타일·시스템별 그래프 카드(라디얼 링 + 세그먼트 바 + 모듈 상태 칩)로 보여 준다. 데이터는 `dashboard.js` 가 `GET /api/dashboard/daily` 로 불러와 라디얼 링 채우기·카운트업·스태거 진입 애니메이션으로 렌더링하며, 30초마다 자동 갱신(탭 비활성 시 일시정지)하고 `prefers-reduced-motion` 을 존중한다. 상태 색은 라벨과 항상 함께 노출한다.
- **점검 실행** 화면(`GET /runs/execute`, `execute.html`)은 기존 홈의 Run 트리거 UI로, “시스템 실행”과 “전체 순차 점검”을 함께 제공한다. **시스템** 섹션(SUITE + 개별 시스템 카드)이 상태 메트릭 직후 상단에 배치되고, **진행 중 / 최근 Run** 패널은 시스템 목록 하단에 위치한다.
- 홈 화면 상단에는 상태 카드 3종(등록 시스템 수, AI 분석 설정 상태, 종료 메일 설정 상태)이 표시된다.
- **인증 프리셋(내 점검 세트)**: 매번 인증 정보를 다시 입력하는 반복을 없애기 위해, 사용자가 자주 쓰는 인증 수단·정보(+선택 모듈)를 이름 붙여 저장하고 원클릭으로 불러온다. 개별 시스템 카드에는 프리셋 칩 행 + "현재 설정 저장" 버튼이 있고, 칩을 클릭하면 폼(인증 수단·조건부 인증 정보·브라우저 모드·모듈 선택)이 그대로 채워진다. **전체 점검(SUITE) 카드에서는 인증 정보를 직접 입력할 수 없고**, 선택한 시스템마다 저장된 프리셋을 하나씩 골라야 한다 — 프리셋이 없거나 고르지 않은(인증이 필요한) 시스템은 실행/예약이 차단된다(제출 시 검증 + 시스템별 상태 배지 `선택됨`/`미선택`/`프리셋 없음`). 프리셋은 사용자별로 격리되고 소유자만 조회/수정/삭제한다. 프런트 로직은 `app/web/static/app.js`(`loadPresets`/`renderIndividualPresetPanels`/`renderSuitePresetLists`), 스타일은 `app/web/static/app.css`(`.preset-*`).
- 홈 **진행 중 / 최근 Run** 패널은 `GET /api/runs?scope=today` 요약을 주기적으로 불러와 렌더링한다 — 진행 중(PENDING/RUNNING/WAITING_INPUT) Run 은 날짜와 무관하게 포함하고, 그 외 Run 은 KST(`E2E_SCHEDULE_TZ`) 당일 `requested_at` 만 표시한다(최대 8건, 진행 중 우선). 당일·진행 중 Run 이 없으면 섹션을 숨긴다.
- **Run 이력** 페이지(`GET /runs/history`)에서 당일 이전 Run 을 `GET /api/runs?scope=before_today` 로 조회한다(SQLite 영속 — 서버 재시작 후에도 이력이 남음).
- 개별 시스템 실행 전 모듈 선택 그래프에서 모듈을 개별 해제할 수 있고, 선택값은 실행 요청의 `selected_module_ids` 로 전달된다.
- **SUITE** 실행 전 시스템 체크박스에서 시스템을 개별 해제할 수 있고, 선택값은 `selected_system_codes` 로 전달된다. 미선택 시스템은 Suite step `SKIPPED` 로 남는다.
- 개별 Run 실행 시 곧바로 Run 상세 화면으로, SUITE 실행 시 Suite 상세 화면(`/suites/{suite_id}`)으로 이동한다.
- 인증 수단처럼 시스템별 실행 옵션은 manifest 의 `run_form` 정의로 렌더링된다.

### 5.2 API 계층

현재 구현:

- `GET /` (로그인 후 첫 화면 — 일간 점검 현황 대시보드 HTML, 비관리자; admin 은 `/admin` 으로 리다이렉트. 데이터는 페이지 스크립트가 `GET /api/dashboard/daily` 로 로드)
- `GET /runs/execute` (시스템 단위 점검 실행 HTML — Run 트리거 UI, 비관리자; admin 은 `/admin` 으로 리다이렉트)
- `GET /login` (로그인 HTML)
- `POST /auth/login` (폼 또는 JSON 로그인 → JWT 쿠키)
- `POST /auth/logout`
- `GET /auth/me`
- `GET /account/password` (비밀번호 변경 HTML)
- `POST /auth/change-password`
- `GET /runs/history` (당일 이전 Run 이력 HTML, 비관리자; admin 은 `/admin` 으로 리다이렉트)
- `GET /runs/{run_id}` (Run 상세 HTML)
- `GET /suites/{suite_id}` (Suite 상세 HTML)
- `GET /schedules` (예약 점검 관리 센터 HTML — 무인 점검 관제실: KPI/조치 필요/목록/시간표 캘린더/상세 드로어; admin 포함, 리다이렉트 없음. 수정 폼 렌더링을 위해 접근 가능 시스템의 manifest 를 함께 내려준다)
- `GET /anomalies` (이상징후 인박스 HTML — 팀 전체 이상건 작업목록; admin 포함 모든 로그인 사용자, 리다이렉트 없음)
- `GET /self-healing` (자가 치유 센터 HTML — 복구 콘솔(KPI/치유 이벤트 파이프라인/정책/만성 지점)·승인 대기 패치·셀렉터 내구성 맵 3탭; admin 포함, 리다이렉트 없음)
- `GET /insights` (시스템 인사이트 HTML — 헬스/타임라인/모듈 딥다이브 3탭; admin 포함)
- `GET /systems/{system_code}/insights` (특정 시스템 프리셀렉트 인사이트 HTML)
- `GET /api/systems`
- `GET /api/systems/{system_code}/health` (시스템 헬스 대시보드 데이터 — 통과율 스코어·일별 추이·모듈 안정성 랭킹·캘린더 히트맵; `days` 쿼리)
- `GET /api/systems/{system_code}/timeline` (시스템 수직 타임라인 — Run 카드·회귀 시작점·recovered/newly_failed 변화 칩; `limit` 쿼리)
- `GET /api/systems/{system_code}/modules/breakdown` (모듈 딥다이브 — depends_on 파이프라인 노드·소요/실패유형 분포·스크린샷 스트립·단계별 누적 소요)
- `GET /api/anomalies` (이상징후 인박스 — ANOMALY/ERROR 모듈 + 처리상태·담당자·메모; 비관리자는 `allowed_system_codes` 스코프)
- `GET /api/anomalies/assignees` (담당자 배정 드롭다운용 사용자 목록)
- `PATCH /api/anomalies/{module_run_id}` (이상건 처리상태/담당자/메모 갱신 — `module_run_id` = `{run_id}::{module_id}`)
- `GET /api/healing/events` (치유 이벤트 목록 — 무엇이 깨졌나/어떻게 복구했나/신뢰도/재실행 검증 결과, 최신순; `system` 쿼리 필터, 비관리자는 `allowed_system_codes` 스코프)
- `GET /api/healing/metrics` (복구 콘솔 KPI — 이번 달 자동 복구 N건·사람 개입 없이 넘어간 비율·MTTR + 일별 추이 + 만성 지점 표)
- `GET /api/healing/durability` (셀렉터 내구성 맵 — steps 소스 정적 스캔(안정/주의/취약 점수화) + 치유 이력 결합 만성 취약 Top N/정비 필요 묶음)
- `GET /api/healing/policy` (자동 복구 정책 조회 — 전역 `*` 기본값 + 시스템별 auto-heal on/off·신뢰도 임계치)
- `PUT /api/healing/policy` (정책 upsert — 전역 `*` 행은 admin 전용, 시스템 행은 접근 범위 내에서만)
- `GET /api/healing/patches` (셀렉터 오토픽스 패치 목록 — 승인 대기 diff + 승인/거절 감사 이력; `status` 쿼리 필터)
- `POST /api/healing/patches/{patch_id}/approve` (패치 승인 — 사람 승인 게이트 통과 시점에 steps 소스 파일에 셀렉터 교체 반영; 소스가 변경돼 적용 불가면 409)
- `POST /api/healing/patches/{patch_id}/reject` (패치 거절 — 사유 `note` 와 함께 감사 이력에 기록)
- `GET /api/healing/patches/{patch_id}/download` (패치 diff 다운로드(.patch) — 소스 반영 대신 코드리뷰 도구로 가져갈 때)
- `GET /api/dashboard/daily` (로그인 사용자의 접근 가능 시스템별 **일간 점검 현황** — 시스템·모듈 단위 오늘(KST) 점검 상태 집계, PII 미포함)
- `GET /api/runs` (Run 요약 목록; `scope=today|before_today`, `limit` 쿼리 지원 — 생략 시 기존과 동일 전체 목록, 기본 limit 50)
- `POST /api/runs/systems/{system_code}`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/nodes`
- `POST /api/runs/{run_id}/otp`
- `POST /api/runs/{run_id}/cancel`
- `POST /api/runs/{run_id}/rerun`
- `GET /api/presets` (로그인 사용자의 인증 프리셋 목록; `system_code` 쿼리로 시스템 필터, 소유자 본인에게만 `input_data` 포함)
- `POST /api/presets` (인증 프리셋 저장 — `system_code`·`name`·`input_data`·`selected_module_ids`, `RunService.validate_run_request` 로 검증)
- `PUT /api/presets/{preset_id}` (프리셋 이름/인증 정보/모듈 선택 수정, 소유자 전용)
- `DELETE /api/presets/{preset_id}` (프리셋 삭제, 소유자 전용)
- `GET /api/suites` (최근 Suite 요약 목록)
- `POST /api/suites` (`browser_mode`, `systems`, `selected_system_codes` 로 Suite 생성)
- `GET /api/suites/{suite_id}`
- `POST /api/suites/{suite_id}/cancel`
- `POST /api/suites/{suite_id}/otp` (현재 대기 중인 시스템 Run에 OTP 전달)
- `POST /api/otp/inbound` (SMS 중계기 → 현재 OTP 대기 Run 자동 탐색 후 OTP 주입·재개; 사용자 세션이 아닌 `X-OTP-Relay-Token` 기기 토큰 인증, `E2E_OTP_RELAY_TOKEN` 미설정 시 비활성)
- `GET /api/schedules` (예약 목록 요약, input_data / suite_systems 제외; `cron_label`(한글 주기)·`paused` 파생 필드 포함)
- `GET /api/schedules/board` (예약 관제 보드 — KPI(전체/활성/오늘 예정/조치 필요) + 예약별 문제 분류 `issues`(stuck=OTP 멈춤/failing=연속 실패/missed=실행 누락/stale=꺼진 지 오래) 파생 필드. 문제 예약만 `attention` 으로 승격)
- `GET /api/schedules/calendar` (점검 시간표 — `from`/`to`(최대 14일) 구간의 cron 미래 전개(계획) + schedule-triggered Run/Suite 매칭(실적) 블록. 계획됐는데 실행이 없으면 `missed`, 계획 없는 수동 실행은 `unplanned`. 시스템별 최근 24h 커버리지 + 같은 시각 몰림 경고 포함)
- `POST /api/schedules/systems/{system_code}` (개별 시스템 cron 예약 등록)
- `POST /api/schedules/suites` (전체 점검 cron 예약 등록, `selected_system_codes` 포함)
- `GET /api/schedules/{schedule_id}` (예약 상세 — 요약 + 변경 이력 `change_log` + 저장된 입력값 키 목록 `input_data_keys`; 값(PII)은 미노출, 소유자/admin 전용)
- `PUT /api/schedules/{schedule_id}` (예약 in-place 수정 — 이름/cron/모듈 선택/인증값 병합(비어있지 않은 키만 교체), suite 는 시스템 선택/브라우저 모드. 생성과 동일한 검증을 통과해야 하며 변경 이력에 기록)
- `GET /api/schedules/{schedule_id}/history` (예약 단위 실행 이력 — 최근 N회(기본 30) 점 스트립 + 성공률/평균 소요/연속 성공 streak)
- `POST /api/schedules/{schedule_id}/toggle` (활성/비활성 전환)
- `POST /api/schedules/{schedule_id}/run-now` (즉시 1회 실행)
- `POST /api/schedules/{schedule_id}/pause-until` (일시 중지(~시각까지) — 기한이 지나면 스케줄러 tick 이 자동 재개, `paused_until=null` 은 즉시 재개)
- `POST /api/schedules/{schedule_id}/duplicate` (예약 복제 — 같은 대상/주기/입력의 새 예약을 비활성 상태로 생성)
- `DELETE /api/schedules/{schedule_id}` (예약 삭제 — 모바일 트리거 URL 도 함께 폐기)
- `GET /m/{trigger_token}` (모바일 즉시 점검 HTML — 예약별 비밀 토큰 인증, JWT 불필요. **부수효과 없음**: 실제 실행은 페이지 스크립트가 아래 POST 를 호출한다 — 메신저 링크 미리보기·브라우저 프리페치가 실 사이트 점검을 오발사하지 않게 하는 설계)
- `POST /api/trigger/{trigger_token}` (예약 "지금 실행"과 동일한 즉시 실행 — 직전 실행이 아직 진행 중이면 새로 만들지 않고 `already_running: true` 로 그 실행에 합류)
- `GET /api/trigger/{trigger_token}/status` (최근 실행 상태 요약 폴링 — 상태·통과 개수·OTP 대기 여부만, 입력값/전체 blob 미노출)
- `POST /api/trigger/{trigger_token}/otp` (대기 중 실행에 OTP 제출·재개)
- `WS /ws/runs/{run_id}`
- `WS /ws/suites/{suite_id}`
- `GET /api/admin/dashboard` (전체 시스템 7일×3타임 점검 커버리지 매트릭스, admin 전용, PII 없음)
- `GET /api/admin/runs` (전체 Run 목록, admin 전용; `system_code`·`user_name` 필터, `limit` 지원)
- `DELETE /api/admin/runs/{run_id}` (Run 영구 삭제 — `domain_events`·스냅샷·`run_history_index`·`module_history_index`·레거시 `runs` blob·로그·아티팩트 등 Run-scoped 행 전부 제거, 재기동 backfill 대상 아님, admin 전용)
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
- `GET /admin` (관리자 관제 대시보드 HTML — 7일×3타임 커버리지 히트맵 + 오늘 모듈 현황)
- `GET /admin/runs` (Run 이력 HTML — 전체 완료 Run 목록·필터·삭제)
- `GET /admin/users` (사용자 관리 HTML)
- `GET /admin/stats` (사용량 통계 HTML)
- `GET /admin/ops` (운영 관측 HTML — Run/Suite/스케줄·큐·최근 이벤트)
- `GET /admin/modules` (모듈별 수동 업무 시간 관리 HTML; 시스템 카드당 저장 버튼 1개로 변경분 일괄 저장)

> **인프라 라우트 제외 규칙:** 브라우저/OS 가 자동 요청하는 자산 라우트(`/favicon.ico`,
> `/apple-touch-icon*.png` — `app/main.py`, `include_in_schema=False`)와 정적 마운트(`/static`,
> `/artifacts`)는 API 계약이 아니므로 이 목록에 넣지 않는다. 규칙은 FastAPI 의
> `include_in_schema=False` 와 동일한 의미론이다 — **이 플래그가 붙은 라우트는 §5.2 문서화
> 대상에서 제외**되며, 정합성 가드도 같은 규칙으로 건너뛴다(`docs/DOCS_GOVERNANCE.md` §3).

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
- **부분 재실행** (`POST /api/runs/{run_id}/rerun?from_module={module_id}`) — 매니페스트 `partial_rerun_allowed` 및 `RunStateMachine.decide_partial_rerun` 정책을 통과하면 실패 모듈부터 재개(기존 브라우저 세션 `ExecutionGateway.resume_from_step` 재사용)
- 실시간 상태 이벤트 스트리밍

**참고:** OTP API는 Run이 `WAITING_INPUT` 상태로 멈춰 있을 때만 의미가 있다. 어떤 인증 수단이 이 상태를 만드는지는 각 시스템 시나리오 문서를 참고한다.

### 5.3 Orchestrator 계층

현재 구현 핵심은 `app/orchestrator/run_service.py` 다. `RunService` 는 **실행 순서와 부작용 조율**(영속·이벤트 발행·게이트웨이 호출)을 담당하는 애플리케이션 서비스이며, "무엇을 할지"(결정)와 "무엇이 합법한 상태 변경인가"(전이)는 두 순수 도메인 컴포넌트 `RunStateMachine`·`RunAggregate` 에 위임한다. Playwright/스레드/Gemini/SMTP 를 전혀 import 하지 않는다(브라우저 없이 단위 테스트 가능).

위임 구조:

- `RunStateMachine`(`app/domain/run_state_machine.py`): 실행 루프의 **결정 규칙(명시적 전이표)** 소유자. `(상태·신호) → 명령` 으로 매핑하는 순수 함수(`decide_module_entry` → `CancelRemaining`/`BlockModule`/`ExecuteModule`, `decide_post_step` → `CancelRemaining`/`PauseForInput`/`CompleteStep`/`RejectUnexpectedInput`). 과거 `_execute_run_inner` 의 절차적 for 루프에 if/return 으로 흩어져 있던 분기(취소 관측·선행 차단·OTP 일시정지·결과 기록)를 이 표 한곳으로 끌어내 I/O 없이 단독 단위 테스트한다(`tests/test_run_state_machine.py`). `RunService` 는 이 명령을 받아 효과(I/O)만 수행하는 얇은 해석기다.
- `RunAggregate`(`app/domain/run_aggregate.py`): Run 상태 **전이(변경)** 규칙·불변식의 **단일 소유자**. `Run` 모델을 감싸 `begin`/`block_for_dependencies`/`mark_queued`/`mark_running`/`record_result`/`finish_timing`/`fail_module`/`mark_waiting_input`/`resume_after_input`/`cancel_modules`/`finalize`/`compute_final_status`/`select_failure_target`/`seal_interrupted` 같은 **순수 메서드**(await·I/O 없음, 시계만 참조)를 노출한다. 결정(`RunStateMachine`)이 "무엇을 할지"를, 이 애그리거트가 "그 변경을 어떻게 적용할지"를 책임진다(I/O 없이 `tests/test_run_aggregate.py` 로 단독 테스트). **애그리거트는 도메인 상태의 유일한 변이자다** — 로그 스트리밍(`note_module_message`)·AI 실패 분석 부착(`attach_failure_analysis`) 같은 잔여 직접 변이까지 애그리거트 메서드로 흡수해, `app/domain/` 밖에서 `run.x = y` 류의 직접 도메인 필드 대입이 존재하지 않는다(grep 으로 증명 가능).
- `RunPlanner`(`run_planner.py`): 입력값 검증·모듈 선택·인증 수단 검증, manifest 기준 모듈 리스트 생성(순수 로직).
- `ExecutionGateway` 포트: 브라우저 세션 열기/단계 실행/입력 제출/종료. 스레드·런타임은 어댑터가 소유.
- `RunComparator`(`run_comparator.py`): 직전 Run 대비 비교(저장소 의존). 종료 메일이 참조하므로 구독자가 아니라 finalize 시점에 결정적으로 계산.
- `RunEventPublisher`(`run_event_publisher.py`): 도메인 상태를 `DashboardEvent` 로 변환·발행(WS 표현 관심사). Run 본문은 `RunView` 프로젝션을 거친다.
- `RunView`(`run_view.py`): Run 의 **읽기 모델 프로젝션**. REST 응답·WebSocket payload·스냅샷은 엔티티를 직접 `model_dump` 하지 않고 이 프로젝션을 거쳐 나간다. 내부 경로는 `RunAggregate.to_snapshot()` → `RunSnapshot` → `RunView.from_snapshot` (애그리거트 `.run` 직접 노출 금지, AG-005). Suite 도 동일 — `SuiteAggregate.to_snapshot()` → `SuiteView.from_snapshot`.
- `OutboxRelay`(`app/eventsourcing/relay.py`): 도메인 이벤트를 transactional outbox 에서 소비해 **단일 알림 파이프라인**을 구동한다 — (1) `ProjectionHandlers` 로 CQRS read-model 갱신, (2) `EventBus` 로 부수 관심사(Suite 사가·AI 분석·메일), (3) `RealtimeProjector` 로 WebSocket fan-out. 오케스트레이터·저장소가 WS 리스너에 직접 publish 하지 않는다.
- `EventBus` 구독자: AI 실패 분석·종료 메일(부수 관심사).
- `summarize_run`(`run_summary.py`): 최근 Run 요약 뷰.

오케스트레이터가 (도메인 애그리거트에 위임해) 담당하는 책임:

- 모듈 상태 전이 관리, 의존성 실패 시 `BLOCKED` 처리
- OTP 대기 상태 저장: 재개 컨텍스트(직렬화 세션 토큰 + resume index + module id)를 `RunControlStorePort`(기본 `SqliteRunControlStore`)에 영속한다. 더 이상 서비스-인스턴스 메모리 dict 가 아니다 — OTP 제출 시 토큰으로 핸들을 복원해 중단된 단계부터 재개한다. OTP 값 자체는 저장하지 않고 게이트웨이가 런타임에 직접 주입한다.
- Run 취소(`cancel_run`): 취소 의도를 `RunControlStorePort` 에 영속(취소 컬럼과 pending 컬럼이 분리돼 동시 갱신 충돌 없음)하고, 실행 루프가 모듈 사이에서 이를 **스토어에서 최신값으로 읽어** 협력적으로 중단한다. 진행 중인 단계는 끝나거나 timeout 된 뒤 멈추며, 남은 모듈은 `CANCELLED` 로 표시한다. OTP 입력 대기 중에는 루프가 돌지 않으므로 즉시 세션을 정리하고 종료한다.
- 동일 입력 재실행(`rerun_run`): Run 생성 시 `RunInputStorePort` 에 보관한 입력값(otp_code 미포함)으로 같은 시스템·모듈 선택의 새 Run을 만든다. `from_module_id` 가 주어지면 `execution_policy`·`decide_partial_rerun` 을 거쳐 **부분 재실행**으로 기존 세션을 재개한다(`resume_from_step`).
- Run 종료(finalize) 시 domain event + outbox 기록 → `OutboxRelay` 가 projection·EventBus·WS 를 갱신

**실행 정책(재시도·부분 재실행):** `app/domain/execution_policy.py` 가 매니페스트 `execution_profile`·`max_retries`·`retryable_on`·`partial_rerun_allowed` 를 `ModuleExecutionPolicy`/`SystemExecutionPolicy` 로 해석한다. 모듈 실패 시 `RunStateMachine.decide_post_step_failure` 가 즉시 재시도(`RunAggregate.record_retry`)·부분 재실행 대상 선정·종료를 결정한다. 실행 큐는 `ProfilePartitionedRunQueue` 가 `execution_profile`(heavy/light/interactive) 별로 `E2E_RUN_CONCURRENCY_{HEAVY,LIGHT,INTERACTIVE}` 동시성을 적용한다.

현재 상태 전이:

**종료 결과는 3분류다(이진 PASSED/FAILED 아님).** 도메인은 단계 결과를 `정상`/`이상징후`/`점검실패` 로 나눈다 — 이 구분이 보존 정리·관리자 통계·메일 정책을 가른다(`app/core/enums.py`, `app/core/status_labels.py`).

- `PASSED`(정상): 단계가 `StepCompleted` 로 끝남.
- `ANOMALY`(이상징후): 단계 핸들러가 `RuntimeError` 를 던짐 — 점검 자체는 정상 동작했고 **대상 사이트에서 의미 있는 이상(검증 실패)을 발견**한 상태. 보존 정리에서 **유지**되고 관리자 통계에 **포함**된다.
- `ERROR`(점검실패): 그 외 예외(셀렉터·런타임 크래시 등) — **점검 도구 자체가 제대로 실행되지 못한** 상태. 일일 보존 정리에서 **삭제**되고 관리자 통계에서 **제외**된다.
- `FAILED`: **레거시 호환 값**. 신규 기록에는 쓰지 않으며, 과거 SQLite/JSON 데이터를 읽을 때 집계·표시상 `이상징후(ANOMALY)`로 취급한다.

종료 판정 우선순위(`RunAggregate.compute_final_status`): **ERROR > ANOMALY > PASSED**. 모듈 중 하나라도 ERROR 면 Run 은 ERROR, ERROR 없이 ANOMALY 가 있으면 ANOMALY, 모두 PASSED 면 PASSED.

UI 라벨(`app/core/status_labels.py`): `PASSED`→정상, `ANOMALY`→이상징후, `ERROR`→점검실패, `CANCELLED`→취소.

Run:

- `PENDING`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED` (정상)
- `ANOMALY` (이상징후 — 점검은 수행됐고 사이트 이상 발견)
- `ERROR` (점검실패 — 점검 도구 오류)
- `FAILED` (레거시 호환; 표시·집계 시 이상징후로 취급)
- `CANCELLED` (사용자가 취소한 Run)

Module:

- `PENDING`
- `QUEUED`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED` (정상)
- `ANOMALY` (이상징후)
- `ERROR` (점검실패)
- `FAILED` (레거시 호환; 이상징후로 취급)
- `BLOCKED`
- `SKIPPED`
- `CANCELLED` (Run 취소로 실행되지 않거나 중단된 모듈)

### 5.3.1 Suite Orchestrator 계층

현재 구현 핵심은 `app/contexts/suite/application/service.py` 다. **이벤트 기반 Saga(프로세스 매니저)** 로 동작한다 — 과거의 `_execute_suite` 백그라운드 루프(하위 Run 의 WebSocket 이벤트 큐 구독 + `get_run` 2초 폴링으로 종료 감지)는 제거됐다. Run 쪽과 마찬가지로 **결정·변경을 순수 도메인으로 분리**한다(서비스 안의 인라인 `suite.status = …`/`step.status = …` 변이 제거):

- `SuiteStateMachine`(`app/contexts/suite/domain/state_machine.py`): 사가의 **결정 규칙(전이표)**. `decide_after_run_finished` → `RecordAndAdvance`/`RecordAndCancel`(하위 Run 결과를 스텝 상태로 매핑 + 전진/취소 판정), `decide_advance` → `StartStep`/`FinalizeSuite`/`CancelSuite`. `RunStateMachine` 과 동형의 순수 함수이며 `tests/test_suite_state_machine.py` 로 단독 테스트.
- `SuiteAggregate`(`app/contexts/suite/domain/aggregate.py`): Suite 상태 **전이(변경)·불변식의 단일 소유자**. `SuiteRun` 모델을 감싸 `begin`/`start_step`/`link_run`/`record_step_result`/`mark_step_error`/`mark_waiting_input`/`mark_resumed`/`finalize`/`seal_interrupted`/`next_pending_index`/`compute_final_status` 같은 순수 메서드(await·I/O 없음, 시계만 참조)를 노출한다. `RunAggregate` 와 동형이며 `tests/test_suite_aggregate.py` 로 단독 테스트. `SuiteService` 는 결정을 받아 효과(영속·이벤트·하위 Run 명령)만 수행하는 얇은 해석기다.
- `RunCommandPort`(`app/orchestrator/run_command_port.py`): 사가가 하위 Run 을 구동하기 위한 **명령 포트**(`validate_run_request`/`start_run`/`cancel_run`/`submit_otp`/`get_run` 을 선언한 `Protocol`). `SuiteService` 는 구체 `RunService` 가 아니라 이 포트에 의존하며, `RunService` 가 구조적으로(structural typing) 이를 만족해 컴포지션 루트가 `run_commands=run_service` 로 주입한다(사가가 애플리케이션 서비스에 용접되지 않음).

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

Suite (Run 과 동일하게 3분류 종료 결과):

- `PENDING`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED` (선택된 시스템이 모두 정상)
- `ANOMALY` (이상징후 — 점검은 됐고 일부 시스템에서 사이트 이상 발견)
- `ERROR` (점검실패 — 일부 시스템의 점검 도구 오류)
- `FAILED` (레거시 호환; 표시·집계 시 이상징후로 취급)
- `CANCELLED`

SuiteStep (시스템 단위):

- 위 상태 + `SKIPPED` (사용자가 시스템 선택에서 제외)

### 5.4 Registry 계층

현재 구현:

- `app/registry/loader.py` (`app/systems/*/manifest.yaml` 글롭 로드)
- `app/systems/hom/manifest.yaml`
- `app/systems/mhm/manifest.yaml`
- `app/systems/fp/manifest.yaml`
- `app/systems/hrp/manifest.yaml`
- `app/systems/hwtc/manifest.yaml`
- `app/systems/chbot/manifest.yaml`

역할:

- 시스템 정의 로드 (`display_order` 오름차순, 동률은 `system_code` 순)
- Run form 정의 로드
- 모듈 메타데이터 로드
- manifest 정합성 검증: `module_id` 중복, 모듈의 `system_code` 불일치, 알 수 없는 `depends_on`, 의존성 순서(선행 모듈 `order`가 더 작아야 함), 의존성 순환을 로드 시점에 검사하고 위반 시 `ValueError`

manifest 에 들어 있는 정보:

- 시스템 코드, 이름, 설명
- `execution_profile` — `heavy` | `light` | `interactive` (실행 큐 프로필·동시성 파티션)
- `max_retries` / `retryable_on` / `partial_rerun_allowed` (모듈·시스템 실행 정책, `execution_policy.py` 가 해석)
- 폼 필드 정의
- `show_when` 기반 조건부 노출 규칙
- 모듈 순서와 의존성
- `workflow_step`
- 모듈별 `timeout_seconds`
- `requires_user_input`: 이 모듈이 사람 입력(휴대폰 OTP 등)으로 Run 을 일시정지시킬 수 있는지를 **선언**한다(일시정지 정책의 단일 출처). 도메인(`RunStateMachine.decide_post_step`)이 이 선언을 근거로 일시정지를 허가하며, 선언하지 않은 모듈이 입력을 요구하면 정책 위반(`RejectUnexpectedInput` → ERROR)으로 처리한다.

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

- `app/execution/composite_gateway.py` (`CompositeExecutionGateway` — 여러 어댑터를 `execution_mode` 로 라우팅하는 합성 게이트웨이. 어댑터 목록 배선은 컴포지션 루트 `app/composition/container.py`(`AppContainer`)가 소유)
- `app/execution/worker_gateway.py` (`WorkerExecutionGateway` — `worker/` HTTP API 클라이언트, `resume-from-step`·`storage-state` 포함; 실 브라우저는 워커 `SessionServer` 가 구동)
- `app/execution/simulated_gateway.py` (`SimulatedExecutionGateway` — simulated 테스트 더블)
- `app/execution/profile_queue.py` (`ProfilePartitionedRunQueue` — manifest `execution_profile` 별 큐 라우팅)
- `app/automation/` — Automation BC (Scenario → Flow → PageObject). **site automation은 `app/systems/*/steps/` 가 아니라 여기**에 있다(6시스템 전부 이전 완료).
- `app/systems/loader.py` (`execution_mode` → executor + ScenarioEngine 로딩)
- `app/runner/workflow_engine.py` (`BaseWorkflowExecutor` — 로그·아티팩트·`StepOutcome`·레지스트리 디스패치)
- `app/scenarios/rep_homepage/executor.py` (`RepHomepageExecutor`) — 대표홈페이지 PC·모바일 공용; 채널은 `ChannelProfile` + `app/automation/page_objects/{hom,mhm}/`
- `app/systems/hom/channel.py` (`PC_CHANNEL`) / `app/systems/mhm/channel.py` (`MOBILE_CHANNEL`) — PageObject 주입만 담당(얇은 executor 팩토리)
- `app/systems/access_common/executor.py` (`AccessWorkflowExecutor` 베이스) + fp/hrp/hwtc/chbot executor
- `app/runner/workflow_common.py` / `app/runner/artifact_manager.py`

실행 모델:

- Run 단위로 Playwright 런타임 생성 (영속 프로파일 persistent context)
- 하나의 browser/context/page를 공유
- 모바일 채널(`ChannelProfile.mobile=True`, 예: MHM)은 공용 `build_runtime()` 에서 페이지 생성 직후 `apply_mobile_device_mode()` 로 모바일 디바이스 모드를 먼저 적용한 뒤 접속
- 단계형 모듈을 순차 실행 (manifest의 `workflow_step` → 실행기의 `build_step_registry` 레지스트리 조회로 단계 핸들러 디스패치, 채널은 `ChannelProfile.steps` 어댑터로 주입)
- 표준 출력/표준 에러를 가로채 모듈별 `execution.log` 와 라이브 WebSocket 로그로 저장
- 휴대폰인증 단계는 OTP 미입력 시 단계 핸들러가 `StepNeedsInput(prompt)` 타입드 결과로 입력 필요 '사실'만 보고한다(과거 `WAITING_INPUT::` 매직 문자열 반환 대체). 일시정지를 '허가'하는 정책은 어댑터가 아니라 도메인이 매니페스트의 `requires_user_input` 선언으로 가진다 — 선언한 모듈만 `WAITING_INPUT` 으로 일시정지하고, 선언하지 않은 모듈의 입력 요구는 ERROR 로 거부된다.

이 구조를 택한 이유:

- 로그인 이후 세션을 다음 모듈에 전달해야 함
- 휴대폰 본인인증에서는 OTP 제출 이후에도 동일 세션으로 로그인 완료까지 이어져야 함
- 계약목록·계약상세·보험금청구·보험금청구 결과 조회/취소 등 후속 모듈은 동일 세션이 필요함

### 5.6 Storage 계층

저장소는 `ExecutionGateway` 와 같은 **포트-어댑터** 구조다. **쓰기(CQRS command)** 는 `RunWriteRepositoryPort` + domain event store + transactional outbox, **읽기(CQRS query)** 는 projection 테이블 + 전용 조회 포트다:

- `RunSummaryQueryPort` — Run 요약 목록 (`run_history_index` 화면형 행; 필터·정렬·페이지는 전부 SQL, `Run` 엔티티 반환 금지, AG-001: `list_runs()` 전수 스캔 금지)
- `ModuleHistoryQueryPort` — 모듈 실행 이력 (`module_history_index` projection; 인사이트/통계/일간 소요시간 소비)
- `SuiteSummaryQueryPort` — Suite 요약 목록 (`suite_history_index` projection)
- `AnomalyInboxQueryPort` — 이상징후 인박스 (`anomaly_inbox_index` projection)
- `DailyStatusQueryPort` — 일간 점검 현황 (`daily_system_status` projection)
- `StatsQueryPort` — 관리자 통계 롤업 (`stats_rollup` + run/module 이력 행, blob 미접근)

오케스트레이터/인사이트 서비스는 구체 SQLite 어댑터가 아니라 위 포트에만 의존한다(`app/storage/ports.py`). **읽기 경로는 blob 을 읽지 않는다**: 목록/집계/실시간 팬아웃은 화면형 projection 행만 소비하고, 단건 애그리거트 로드(`RunWriteRepositoryPort.get_run`)는 상세 화면과 쓰기 경로에만 허용된다. 목록 질의는 커맨드 서비스(`RunService`)가 아니라 전용 질의 핸들러(`app/orchestrator/queries/` 의 `RunQueries`/`DailyDashboardQueries`)가 라우트에 직접 주입돼 담당한다. 제어 상태(취소 의도·OTP 재개)와 입력값(PII)은 상태 blob 과 분리된 형제 스토어가 소유한다.

**영속 DTO ↔ 도메인 엔티티 분리(persistence model):** 저장소 포트는 도메인(`Run`/`SuiteRun`)으로 말하지만, 어댑터는 도메인 엔티티를 직접 직렬화하지 않고 **영속 DTO**(`app/storage/records.py` 의 `RunRecord`/`RunModuleRecord`/`SuiteRecord`/`SuiteStepRecord` + `from_domain`/`to_domain` 매퍼)로 매핑한다. SQLite·인메모리 **두 어댑터가 같은 매퍼**를 쓰므로, 과거 어댑터마다 중복되던 "로그 strip" 매직(`_PERSIST_EXCLUDE` exclude / `_persist_copy` deep-copy 후 비우기)이 사라졌다. 온디스크 JSON 형태는 종전과 동일해 기존 SQLite 데이터와 호환된다.

**집합체(aggregate) 경계:** Run **상태**(status·모듈 전이·comparison)와 **모듈 로그**는 서로 다른 집합체다. 로그는 한 줄씩 추가되는 고빈도 텔레메트리라, Run blob 을 통째로 다시 쓰는 대신 `RunLogStorePort` 의 append-only 스토어에 한 줄당 한 번 INSERT 한다. **영속 Run blob 에는 모듈 로그가 담기지 않는다 — `RunModuleRecord` 스키마에 `logs` 필드가 아예 없어 blob 에 들어갈 수 없는 타입 수준 사실**이지(어댑터의 방어적 exclude 가 아니라), 읽기 시 `RunService.get_run` 이 로그 스토어에서 로그를 읽어 Run 읽기 모델에 하이드레이션한다(쓰기 모델/읽기 모델 분리). 이로써 로그 한 줄마다 Run 전체를 재직렬화하던 핫패스 쓰기(O(N²))가 사라지고, Run blob 쓰기는 상태 전이 시점으로만 한정된다.

현재 구현:

- `app/storage/ports.py` — 저장소 포트(Protocol) 정의 (`RunRepositoryPort` 는 Run 상태만, `RunLogStorePort` 는 로그 스트림만 책임)
- `app/storage/records.py` — 영속 DTO(`RunRecord`/`RunModuleRecord`/`SuiteRecord`/`SuiteStepRecord`) + `from_domain`/`to_domain` 매퍼. 모든 어댑터가 도메인 엔티티를 직접 직렬화하지 않고 이 레코드를 거친다(영속 스키마 ↔ 도메인 분리; `RunModuleRecord` 에 `logs` 없음). `tests/test_storage_records.py` 로 라운드트립·로그 제외·DB 호환 검증.
- `app/storage/sqlite_support.py` — `JsonTableStore`(stdlib `sqlite3` + `asyncio.to_thread`, JSON blob 테이블) · `DEFAULT_DB_PATH`
- `app/storage/listener_registry.py` — `ListenerRegistry`(run_id/suite_id 별 WebSocket 리스너 큐, 프로세스-로컬 휘발성)
- `app/storage/sqlite_run_write_repository.py` / `sqlite_suite_repository.py` / `sqlite_schedule_repository.py` — **기본 SQLite write 어댑터**(`AppContainer` 에서 주입)
- `app/storage/sqlite_run_log_store.py` — **기본 사용되는** 모듈 로그 append-only SQLite 어댑터(`run_logs` 테이블, 한 줄당 한 행, `ORDER BY id` 로 입력 순서 복원)
- `app/storage/run_repository.py` / `suite_repository.py` / `schedule_repository.py` — 인메모리 어댑터(단위 테스트·영속 불요 실행용)
- `app/storage/run_log_store.py` — `InMemoryRunLogStore`(로그 스트림 인메모리 어댑터)
- `app/storage/sqlite_preset_repository.py` — 인증 프리셋(`AuthPreset`) SQLite 어댑터(`PresetRepositoryPort`, `auth_presets` 테이블). Run/Suite 입력값과 달리 **의도적으로 PII 를 영속**한다(프리셋의 목적이 인증 정보 저장). 사용자별 격리는 `PresetService`(`app/orchestrator/preset_service.py`)가 강제하고, 응답에는 소유자 본인에게만 `input_data` 를 돌려준다.

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
- `app/ai/gemini_http.py` (Gemini HTTP 호출 / SSL 검증 모드 처리)
- `app/ai/gemini_models.py` (기본 Gemini 모델 체인 `DEFAULT_GEMINI_MODEL_CHAIN`·`GEMINI_MODELS` 파싱/검증)
- `app/core/env_utils.py` (환경 변수·`.env` 우선순위 해석)

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
- Run이 최종 종료(`PASSED`/`ANOMALY`/`ERROR`, 레거시 `FAILED` 포함 — `RUN_TERMINAL_OUTCOME_STATUSES`)되면 Gmail SMTP로 결과 메일을 보낸다. (`WAITING_INPUT` 등 중간 상태에서는 보내지 않음)
- **Suite** 가 최종 종료되면 포함 시스템 Run 결과를 통합한 메일 1통을 보낸다. `SKIPPED` 시스템은 제외로 표시한다.
- **수신자 라우팅은 종료 결과 분류를 따른다**: `PASSED`(정상)·`ANOMALY`(이상징후)는 시스템(채널)별 환경 변수 `E2E_EMAIL_RECIPIENTS_{SYSTEM_CODE}` 수신자에게 보낸다(예: `E2E_EMAIL_RECIPIENTS_HOM`, … — 여러 명은 `|` 구분). **`ERROR`(점검실패)는 대상 사이트가 아니라 점검 도구 자체의 고장이므로 시스템 담당자가 아닌 도구 운영자(`E2E_EMAIL_OPERATOR_RECIPIENTS`)에게만** 제목 접두사 `[E2E][OPERATOR]` 로 보내며, 운영자 수신자가 미설정이면 ERROR 메일은 생략된다(Suite 도 동일 규칙).
- Suite 메일 수신자는 실행된(선택된) 시스템들의 수신자 집합을 합친다. (ERROR Suite 는 위 운영자 라우팅을 따른다.)
- **메일 본문 HTML은 항상 `report_renderer` 의 고정 템플릿으로 결정적으로 렌더링한다.** 디자인(레이아웃·색·간격)은 코드에 박혀 있어 매 실행 동일하다. Gemini(`GeminiReportContentComposer`)는 HTML 이 아니라 분석 '콘텐츠'(핵심 요약·모듈별 화면/로그 관찰·실패 분석)만 구조화 JSON 으로 생성해 템플릿에 채운다. Gemini 가 비활성/실패면 동일 템플릿이 AI 서술 없이(결정적 기본 문구로) 렌더링되므로 디자인은 그대로 유지된다.
- 홈 화면에 현재 메일 알림 설정 상태(`inspect_env_status`)를 표시한다.

제약:

- 기본값은 비활성화다.
- 설정이 잘못되어도 앱은 계속 실행되며, 메일 발송만 생략될 수 있다.

### 5.9 예약 실행(스케줄러)과 이력 비교 계층

현재 구현:

- `app/scheduling/cron.py` — 5필드 cron(`분 시 일 월 요일`) 파서·다음 실행 시각 계산기. 파싱·매칭·다음 실행 계산·경계 처리를 **`croniter` 라이브러리**(`requirements.txt` 의 `croniter>=2.0,<7.0`)에 위임하는 얇은 래퍼이며, 공개 API(`parse_cron`/`CronSchedule.matches`/`next_run_after`)만 유지한다.
- `app/scheduling/scheduler.py` (`SchedulerService`) — 예약 CRUD(수정·복제·일시 중지 포함)와, cron 기준으로 Run/Suite 를 자동 생성하는 백그라운드 루프(`run_forever`), 그리고 예약 관리 센터의 읽기 모델(`board`/`calendar`/`history`/`get_detail`). `app/main.py` lifespan 에서 task 로 띄우고 종료 시 정리한다.
- `app/scheduling/schedule_center.py` — **예약 점검 관리 센터 순수 빌더**(`insights_*` 빌더와 같은 패턴). 관제 보드의 문제 분류(`classify_issues`: stuck/failing/missed/stale), 캘린더의 cron 전개(`expand_occurrences`)·계획 vs 실적 매칭(`match_occurrences` — 매칭 실패는 `missed`, 계획 없는 실행은 `unplanned`)·몰림 경고(`cluster_warnings`)·커버리지(`build_coverage`), 예약 이력 통계(`build_history_stats`: 성공률/평균 소요/연속 성공), cron 한글 라벨(`cron_to_label`)을 순수 함수로 가진다. `SchedulerService` 는 데이터를 모아 넘기는 얇은 인터프리터이고, 규칙은 브라우저/DB 없이 단위 테스트한다(`tests/test_schedule_center.py`).
- `app/web/templates/schedules.html` + `app/web/static/schedules.js` — **예약 점검 관리 센터 화면**(`/schedules`, 사이드바 "예약 관리"). ① KPI 스트립(전체/활성/오늘 예정/조치 필요) + 화면 상단 고정 **조치 필요** 섹션(문제 예약만 자동 승격 — 🔴 OTP 멈춤은 OTP 입력 딥링크, 🟠 연속 실패, 🟡 실행 누락(`last_skipped_at`), ⚪ 꺼진 지 오래는 원클릭 켜기), ② **목록 뷰**(다음 실행 카운트다운 `T-2h 14m`·cron 한글 라벨·마지막 결과 배지·행별 토글/지금 실행/수정/복제/삭제), ③ **시간표 캘린더 뷰**(주간 요일×시간 그리드에 계획 vs 실적 대비, 누락 빗금, 24h 커버리지 바, 몰림 경고), ④ **상세 드로어**(최근 30회 점 스트립 + 성공률/평균 소요/연속 성공, in-place 수정 폼(cron 빌더 재사용, 인증값은 비어있지 않은 키만 교체), 일시 중지(~시각까지) 퀵칩, 복제, 변경 이력, 모바일 트리거 URL 복사). 사이드바 배지는 `GET /api/schedules/board` 의 조치 필요 건수를 표시한다.
- `app/storage/sqlite_schedule_repository.py` (`SqliteScheduleRepository`, 기본 사용) / `app/storage/schedule_repository.py` (`InMemoryScheduleRepository`) — 예약 저장소. SQLite 어댑터는 `ScheduleRepositoryPort` 를 구현해 재시작 후에도 예약이 남는다.
- `app/api/routes_schedules.py` — 예약 REST API.
- `app/api/routes_trigger.py` + `app/web/templates/mobile_trigger.html` — **모바일 즉시 점검 트리거**. 예약별 비밀 `trigger_token`(생성 시 발급, 레거시 예약은 목록 조회 시 지연 발급)으로 JWT 없이 접근하는 `/m/{trigger_token}` 페이지와 `POST /api/trigger/{trigger_token}` 실행 API. 홈 화면 예약 카드의 "모바일 URL" 버튼으로 URL 을 복사한다.
- `app/scheduling/run_retention.py` (`RunRetentionService` + `RunRetentionScheduler`) — **일일 Run 보존 정리 배치**(별개의 백그라운드 루프). `app/main.py` lifespan 에서 `from_env` 로 만들어 task 로 띄운다.

역할:

- 홈 화면 시스템 폼에서 입력값·모듈 선택 그대로 cron 식을 붙여 **개별 시스템** 예약을 등록한다. 등록 시 `RunService.validate_run_request` 로 검증한다.
- 홈 SUITE 카드에서 브라우저 모드·시스템 선택(`selected_system_codes`)·선택된 시스템별 인증 정보와 함께 **전체 점검** 예약을 등록한다 (`POST /api/schedules/suites`). 등록 시 `SuiteService.validate_suite_request` 로 검증한다.
- 예약은 `schedule_kind` 가 `system`(개별 Run) 또는 `suite`(전체 점검) 이다.
- 예약은 활성/비활성 전환, 즉시 실행(`run-now`), **in-place 수정(PUT — 삭제 후 재생성 불필요)**, **복제(비활성 상태로 생성)**, **일시 중지(~시각까지, 기한 경과 시 tick 이 자동 재개)**, 삭제가 가능하다. 등록/수정/켬끔/일시중지/복제는 예약의 `change_log`(최근 30건)에 누가·언제·무엇을 바꿨는지 기록되어 상세 드로어에 노출된다. 예약 트리거 Run 은 `triggered_by="schedule"`, `schedule_id` 로 태깅되고, **Suite 도 동일하게 `triggered_by="schedule"` + `schedule_id` 로 태깅**되어(예약 관리 센터가 이력/캘린더 실적을 `schedule_id` 로 조회) 그 하위 Run 들은 `triggered_by="suite"` 로 순차 생성된다.
- 백그라운드 루프는 주기적으로(기본 20초) `next_run_at` 이 지난 활성 예약을 찾아 실행하고 다음 시각을 다시 계산한다. 직전 예약 Run/Suite 가 아직 진행 중이면 중복 실행을 건너뛰며, 이때 `Schedule.last_skipped_at` 을 기록해 관제 보드의 '실행 누락/건너뜀' 신호로 노출한다(과거에는 로그에만 남던 `skipped_overlap`). `paused_until` 이 설정된 예약은 발사하지 않고 다음 주기로 미루되(의도된 침묵 — 누락 신호를 남기지 않음), 기한이 지나면 자동 재개한다.
- **모바일 즉시 점검(트리거 URL)**: 예약마다 발급되는 비밀 `trigger_token` 으로 `/m/{trigger_token}` 에 접속하면, 대시보드 로그인 없이 그 예약의 "지금 실행"과 동일한 점검이 실행된다. GET 페이지 자체는 부수효과가 없고(링크 미리보기·프리페치 오발사 방지) 페이지 스크립트가 `POST /api/trigger/{trigger_token}` 을 호출한다. 직전 실행이 진행 중이면 이중 발사 대신 그 실행에 합류하고(`SchedulerService.trigger_now` 의 멱등 가드), OTP 대기 시 같은 페이지에서 인증번호를 제출해 재개할 수 있다. 토큰 대조는 상수 시간 비교(`hmac.compare_digest`)이고 불일치는 일괄 404 이며, 예약 삭제가 곧 URL 폐기다.
- 기준 타임존은 `E2E_SCHEDULE_TZ`(기본 `Asia/Seoul`).
- **일일 보존 정리**: `RunRetentionScheduler` 가 매일 cron 시각(기본 `0 3 * * *`, 기준 타임존 `E2E_SCHEDULE_TZ`)에 당일 00:00 이전 `requested_at` 의 **점검실패(`ERROR`)·취소(`CANCELLED`)** Run 을 DB·로그·아티팩트째 삭제한다(`정상`·`이상징후`는 유지 — `RUN_DAILY_PURGE_STATUSES`). 기본 활성(`E2E_RUN_RETENTION_ENABLED=true`)이며 `E2E_RUN_RETENTION_ENABLED=false` 로 끄거나 `E2E_RUN_RETENTION_CRON` 으로 주기를 바꾼다. 60초마다 cron 일치 여부를 확인하고 하루 한 번만 정리한다.
- **이력 비교**: Run 이 종료 결과(`PASSED`/`ANOMALY`/`ERROR`, 레거시 `FAILED` 포함)로 끝나면 `RunComparator`(`app/orchestrator/run_comparator.py`, `RunService` 에 주입)가 같은 시스템의 직전 종료 Run 을 기준선으로 `newly_failed`(새로 실패)/`recovered`(복구)/`still_failing`(계속 실패) 모듈을 계산해 `Run.comparison` 에 담는다. (종료 메일이 참조하므로 이벤트 구독자가 아니라 finalize 시점에 결정적으로 계산한다.) Run 화면의 "직전 실행 대비 변화" 패널과 종료 메일(고정 템플릿의 "직전 실행 대비 변화" 섹션 · Gemini 콘텐츠 프롬프트 · 평문)에 반영된다.

제약:

- 예약은 SQLite 에 영속되어 재시작 후에도 남는다. 비교 기준선은 같은 시스템의 직전 종료 Run(역시 영속) 을 조회해 계산하므로, 재시작 후에도 이력만 있으면 정상 동작한다. 단, 서버 다운 중 지나간 예약은 catch-up 하지 않고 다음 cron 시각으로 미룬다.
- 예약 실행은 무인 실행이라, 휴대폰/카카오 인증처럼 사람 개입이 필요한 단계가 포함되면 해당 Run/Suite 는 `WAITING_INPUT` 에서 멈출 수 있다.
- 입력값(`input_data`, `suite_systems`)은 PII 를 포함할 수 있어 예약 요약(API/UI)에는 직렬화하지 않는다. Suite 예약 요약에는 `selected_system_count`, `step_total` 등 선택 시스템 수만 노출한다.

### 5.10 인증·관리자·운영 관측 계층

대시보드는 JWT 쿠키 기반 로그인 뒤에서 동작하며, 관리자 전용 운영/통계 화면이 따로 있다.

**인증(`app/auth/`):**

- `app/auth/jwt.py` / `service.py` / `models.py` / `router.py` / `dependencies.py` — JWT 쿠키 발급·검증, 사용자 CRUD, 비밀번호 변경, 사용자별 허용 시스템(`PUT /api/admin/users/{id}/systems`) 관리.
- 사용자 저장소는 포트-어댑터다: `app/storage/sqlite_user_repository.py`(기본) / `user_repository.py`(인메모리).
- 로그인 라우트(`/login`, `/auth/*`, `/account/password`)와 의존성 주입은 `app/auth/dependencies.py`(`get_user_service`).
- Run 목록은 사용자 스코프가 적용된다(비관리자는 자기 Run 만; `tests/test_run_list_scope.py`).

**관리자 통계(`StatsService`, `app/orchestrator/stats_service.py`):**

- `GET /api/admin/stats/usage` — 사용자·시스템별 사용량 통계. 집계 대상은 `ADMIN_VISIBLE_RUN_STATUSES`(= 정상 + 이상징후) 로, **점검실패(`ERROR`)·취소는 제외**한다. 통과 모듈·절감 시간은 `module_history_index` 프로젝션에 의존하며, 앱 시작 시 `rebuild_missing_run_snapshots` + `backfill_module_history_index` + `backfill_from_legacy_runs`(thin-event Run 의 레거시 `runs` blob) 가 누락 행을 채운다.
- `GET /api/admin/stats/savings/csv` — 절감 시간 통계 CSV. **모듈별 수동 업무 시간 설정**(`ModuleSettings`)을 기준으로 자동화가 절감한 시간을 산출한다.
- `app/orchestrator/stats_charts.py` — 통계 차트 데이터 구성. `app/orchestrator/run_actor.py`(`resolve_run_actor`/`load_actor_context`) — Suite·예약 하위 Run 처럼 저장 시점에 실행자 이름이 빠진 Run 의 표시·집계용 실행자(user_id/이름)를 상위 엔티티·사용자 조회로 보완.
- **모듈별 수동 업무 시간 설정**: `GET/PUT /api/admin/module-settings*` 로 시스템·모듈별 수동 업무 시간을 저장한다. 저장소는 `ModuleSettingsRepositoryPort`(`app/storage/module_settings_repository.py`) + 기본 `SqliteModuleSettingsRepository`. 관리 화면은 `/admin/modules`(시스템 카드당 저장 버튼 1개로 변경분 일괄 저장).

**운영 관측(`OpsService`, `app/orchestrator/ops_service.py`):**

- `GET /api/admin/ops/snapshot` / `GET /admin/ops` — 진행 중 Run/Suite, 예약, 실행 큐(`RunExecutionQueue`) 상태, 최근 운영 이벤트 스냅샷.
- 최근 운영 이벤트는 프로세스 내 링 버퍼 `app/core/ops_buffer.py`(`OpsEventBuffer`, 기본 250건, 프로세스-로컬 휘발성)에서 읽는다.
- 구조적 로깅: `app/core/logging.py`(`get_logger`/로그 컨텍스트 바인딩)와 `app/main.py` 의 요청 로그 컨텍스트 미들웨어가 `request_id`·HTTP 메서드/경로를 모든 로그에 바인딩한다. 설정은 `app/core/settings.py`(`E2ESettings`, `get_settings`).

**관리자 Run 관리:**

- `GET /api/admin/dashboard` / `GET /admin` — 최근 7일(KST)·하루 3타임(주간 06–18 / 저녁 18–22 / 야간 22–06) 기준 전체 시스템 점검 커버리지 매트릭스. 집계 규칙은 순수 빌더 `app/contexts/insights/application/admin_coverage_dashboard.py`, 질의는 `AdminDashboardQueries`(`run_history_index` 요약만 소비, PII 없음). 화면은 `app/web/static/admin-dashboard.js`(30초 자동 갱신).
- `GET /api/admin/runs` / `GET /admin/runs` — 전체 Run 목록(시스템·사용자·상태 필터). 집계 대상은 `ADMIN_DASHBOARD_RUN_STATUSES`(= 정상·이상징후·점검실패·취소). `DELETE /api/admin/runs/{run_id}` — Run 영구 삭제: `SqliteRunWriteRepository.delete_run` 이 `domain_events`·`outbox`·`aggregate_snapshots`·`run_history_index`·`module_history_index`·레거시 `runs` blob·`session_checkpoints`·치유 이력 등 Run-scoped 행을 한 트랜잭션으로 제거하고, 로그·아티팩트·입력·제어 상태는 `RunService` 가 함께 정리한다(재기동 startup backfill 로 부활하지 않음). 일간 롤업(`daily_system_status`·`stats_rollup`)은 기존 정책대로 보존. 일일 보존 정리 배치(§5.9)도 같은 삭제 경로(`RunService.purge_runs`)를 쓴다.

### 5.11 자가 치유 센터 계층

무인 실행이 사이트 UI 변경 한 번에 조용히 전부 실패하는 최대 약점을 막는 폐루프(2026 AIOps
closed-loop + 에이전트 오토픽스 관행): **탐지 → AI 진단 → 대체 셀렉터 → 재실행 검증 → 기록/코드 반영 제안**.

**런타임 치유(실행 스레드, `app/healing/engine.py` + `app/runner/workflow_engine.py`):**

- 스텝이 예외로 실패하면 `BaseWorkflowExecutor._dispatch_with_healing` 이 `SelfHealingEngine.try_heal` 을 부른다. 엔진은 Playwright 오류 메시지에서 깨진 셀렉터를 추출하고(`parse_broken_selector` — 체인이면 마지막 `locator(...)`), 라이브 DOM 을 스캔해 요소 지문(id·name·text·role·class)을 수집한 뒤 순수 스코어러(`app/healing/selector_healer.py`)로 후보 신뢰도를 매기고, 상위 후보를 라이브 페이지에서 검증(존재/유일성, 다중 매치는 `>> nth=0` 고정 + 신뢰도 감가)한다.
- **신뢰도 게이팅**: 정책(시스템별 → 전역 `*` → 코드 기본 0.75 순 해석) 임계치 이상이면 런타임 한정 오버라이드를 등록하고 스텝을 **1회 재시도**, 미만이면 자동 적용 없이 승인 대기 제안만 남긴다(무인 실행이 안 끊기는 것과 무단 병합 금지를 동시에 지킨다). 재치유 루프 방지: 이미 오버라이드된 셀렉터가 또 깨지면 치유하지 않는다.
- 오버라이드 적용은 `HealedPage`/`HealedFrame`(`app/healing/page_proxy.py`)이 담당한다 — `execute_step` 동안 `runtime.page` 를 프록시로 교체해 스텝이 `ctx.page`/`runtime.page` 어느 쪽을 쓰든 같은 셀렉터 문자열이 대체 셀렉터로 번역된다(스텝 코드 무수정). 치유 실패/엔진 오류는 절대 원래 실패를 가리지 않는다.
- 실행 스레드의 정책 조회는 비동기 스토어가 아니라 동기 리더 `SqliteHealingPolicyReader`(자기 커넥션 + 5초 TTL 캐시)로 한다.

**보고-사실 / 집행-정책 분리(OTP 일시정지와 동일 규율):** 어댑터는 치유 시도 '사실'만 `StepExecutionResult.healing_events`(`HealingAttempt` 목록)로 보고하고, `RunService` 가 주입된 `HealingRecorderPort`(구현 `HealingService`)로 영속·패치 제안을 위임한다. 기록 실패는 격리되어 점검 결과에 영향을 주지 않는다.

**애플리케이션 서비스(`HealingService`, `app/orchestrator/healing_service.py`):** `InsightsService` 와 같은 얇은 I/O 인터프리터. 집계 규칙은 순수 빌더가 담당한다 — 복구 콘솔 KPI(이번 달 자동 복구 N건·사람 개입 없이 넘어간 비율·MTTR)·만성 지점 승격(같은 셀렉터 3회+ 치유)은 `app/healing/metrics.py`, 셀렉터 내구성 맵(steps 소스 정적 스캔: #id/name/role 안정 🟢 · class 주의 🟡 · 텍스트 매칭/nth/xpath 취약 🔴 + 치유 이력 결합 위험 순위)은 `app/healing/durability.py`, 패치 diff 생성(양쪽 따옴표 리터럴 치환 + `difflib` unified diff + 취약 패턴 기술부채 경고)은 `app/healing/patch_builder.py`. 모두 브라우저/DB 없이 단위 테스트된다(`tests/test_selector_healer.py`/`test_healing_engine.py`/`test_healing_metrics.py`/`test_healing_durability.py`/`test_patch_builder.py`/`test_healing_service.py`).

**셀렉터 오토픽스 패치(사람 승인 게이트):** 런타임 복구는 일회성이므로, 성공/제안된 치유마다 깨진 하드코딩 셀렉터를 대체 셀렉터로 바꾸는 before/after diff 를 `PROPOSED` 패치로 만든다(같은 시스템·깨진→대체 조합의 열린 제안은 중복 생성 안 함). **자동 병합은 없다** — `/self-healing` 의 diff 리뷰에서 승인하면 그 시점에 소스 파일에 치환 적용(소스가 그새 변경돼 대상 리터럴이 없으면 409), 거절하면 사유와 함께 감사 이력으로 남는다. `.patch` 다운로드로 코드리뷰 도구에 가져갈 수도 있다. 어떤 셀렉터가 언제·누구 승인으로 바뀌었는지가 패치 레코드(`decided_by`/`decided_at`)로 남는다.

**영속(포트-어댑터, `app/storage/sqlite_healing_stores.py`):** `HealingEventStorePort`(append-only `healing_events`) / `HealingPolicyStorePort`(`healing_policy`) / `HealingPatchStorePort`(`healing_patches`) — 모두 컬럼형 SQLite 어댑터가 기본이고 배선은 컴포지션 루트(`app/main.py`)가 독점한다.

**화면:** 사이드바 "자가 치유 센터" → `GET /self-healing`(3탭: 복구 콘솔 = KPI 스트립 + 치유 이벤트 5단계 파이프라인 카드 + 신뢰도 게이지 + 자동 복구 정책 패널(on/off + 임계치 슬라이더) + 만성 지점 표 / 승인 대기 패치 = diff 카드 + 승인·거절·다운로드 / 내구성 맵 = 등급 요약 + 정비 필요 묶음(알림 피로 저감: 개별 실패 대신 "N회+ 깨짐" 한 건) + 만성 취약 Top 10 + 히트맵 테이블). 프런트는 페이지 전용 `app/web/static/healing.js`(`app.js` 에 얹지 않음). 승인 대기 패치 수는 사이드바 배지로 노출된다.

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

- 현재 사용 중인 필드 타입은 `text` / `select` / `password` 다. (`password` 는 입력값을 마스킹해 렌더링한다 — FP 주민등록번호 뒷자리, HRP·HWTC 비밀번호.)
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

- 모든 워크플로 단계 모듈(`{system_code}_workflow_step` — HOM/MHM/FP/HRP/HWTC/CHBOT 공통)은 로그를 `execution.log` 로 남긴다.
- 스크린샷(`final.png`)은 **공용 실행 엔진**이 책임진다. 개별 단계 함수는 스크린샷을 직접 찍지 않으며, `BaseWorkflowExecutor.execute_step` 이 각 모듈 종료 시점(성공·실패 공통)에 `runtime.page` 로 한 번 캡처한다(`app/runner/screenshot.py`의 `capture_screenshot`). 모든 등록 시스템(HOM/MHM/FP/HRP/HWTC/CHBOT)에 동일하게 적용된다.
- 캡처는 로그 리다이렉트 안에서 수행되므로 스크린샷 관련 로그도 `execution.log` / WebSocket 으로 함께 남는다.
- 표준 캡처 → 폰트 폴백 재시도 → CDP 폴백 순으로 시도하며, 캡처가 모두 실패해도 단계 성공/실패 판정에는 영향을 주지 않는다(예외를 삼킨다).
- Run 화면에서 아티팩트 링크 노출
- 링크 경로는 `/artifacts/{run_id}/{module_id}/{filename}` 형식이다.

주의:

- 사용자 입력 대기(`WAITING_INPUT`, 예: 휴대폰 OTP 대기)는 모듈 종료가 아니라 일시정지이므로 그 시점에는 스크린샷을 찍지 않는다. OTP 제출 후 모듈이 실제로 끝날 때 캡처된다.
- 초기 단계에서 페이지/브라우저 자체가 깨지면 스크린샷이 없을 수 있다.
- `ModuleDefinition.execution_mode` 의 기본값은 `simulated` 지만 현재 등록된 시스템 manifest는 모두 워크플로 단계 모드를 쓰므로 시뮬레이션 경로는 사용되지 않는다. 시뮬레이션은 `SimulatedExecutionGateway`(포트 어댑터)가 `execution_mode == "simulated"` 모듈에 한해 `simulated_duration_ms`/`simulated_outcome` 대로 처리하며, 아티팩트는 생성되지 않는다. 실제 실행기가 없는 **알 수 없는** `execution_mode` 는 더 이상 조용히 시뮬레이션되지 않고 `open_session` 에서 예외가 나 해당 모듈이 명확히 `ERROR`(점검실패) 처리된다.

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

- Run 이벤트는 `RunView` 프로젝션(`RunView.dump(run)`) — 엔티티를 직접 `model_dump` 하지 않는다.
- Suite 이벤트는 `SuiteView` 프로젝션(`SuiteView.dump(suite)`) (+ `step_index` 등 보조 필드) — REST 응답·WS 스냅샷·이벤트가 모두 이 경로를 거친다(과거의 직접 `suite.model_dump` 누수 제거).
- Module 이벤트는 `module` 스냅샷과 `run_status`
- Log 이벤트는 `module_id`, `message`

## 10. 현재 구현과 초기 목표의 차이

초기 목표는 `웹 트리거형 실행 플랫폼` 이었고, 현재 샘플은 그 방향에 맞는 첫 단계까지 구현되어 있다. 다만 아래는 아직 목표 상태가 아니다.

### 10.1 아직 구현되지 않은 것

- Postgres 등 다중 프로세스/원격 영구 저장소 (SQLite 단일 파일 영속은 **구현됨** — 포트로 분리돼 있어 어댑터만 추가하면 됨)
- Playwright MCP 게이트웨이 구현체 (포트는 `ExecutionGateway` 로 이미 존재; 현재는 워커 `SessionServer` 구현이 유일)
- 병렬 실행 스케줄러 (실행 큐의 프로필별 워커 수로 동시 Run 수는 제한되지만, 동일 `execution_profile` 내 순차 전제는 유지)

과거 이 목록에 있었으나 이후 **구현이 완료된 것**:

- ~~재시도 정책~~ → `execution_policy.py` + `decide_post_step_failure` + `record_retry`
- ~~실패 모듈만 부분 재실행~~ → `POST /api/runs/{run_id}/rerun?from_module=` + `resume_from_step`
- ~~`ModuleContext`, `ModuleResult` 표준화~~ → `StepContext`(능력 인터페이스: `log`/`page`/`dialog_messages`/`artifact_dir`)와 타입드 `StepOutcome`(`StepCompleted`/`StepNeedsInput`, `app/runner/step_outcome.py`)으로 실현됨.
- ~~오류 분류 체계~~ → 종료 결과 3분류(`PASSED` 정상 / `ANOMALY` 이상징후 / `ERROR` 점검실패, §5.3)로 실현됨. 남은 확장은 ERROR 내부의 세부 원인 분류(셀렉터/네트워크/타임아웃 등) 정도다.

### 10.2 이미 방향이 맞는 것

- 웹 트리거 방식
- manifest 기반 시스템/모듈 로딩
- 모듈별 노드 대시보드
- 실시간 이벤트 스트림
- 아티팩트 분리 저장
- **저장소 포트-어댑터 분리 + SQLite 영속** (`app/storage/ports.py` + `Sqlite*Repository`; Run/Suite/예약이 재시작 후에도 유지, 진행 중 실행은 기동 시 정리)
- 모놀리식 스크립트의 단계 모듈 분리
- 로그인 세션 공유형 워크플로우
- **오케스트레이션 ↔ 브라우저 실행 분리** (`ExecutionGateway` 포트 + `WorkerExecutionGateway` 어댑터 → 워커 `SessionServer`; API 프로세스에 브라우저 없음)
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

### Phase 2. 저장소와 실행 모델 개선 — ✅ 완료

- ✅ 저장소 포트(`app/storage/ports.py`) 도입 + `Sqlite*Repository`(SQLite 영속)
- ✅ **CQRS write/read 분리**: `RunWriteRepositoryPort` + 화면형 질의 포트(`RunSummaryQueryPort`/`ModuleHistoryQueryPort`/`SuiteSummaryQueryPort`) + projection tables (`app/projections/`) — 읽기 경로 blob 재수화 제거
- ✅ **Transactional Outbox** + `OutboxRelay` (`app/eventsourcing/`) — domain event → projection · EventBus · WS fan-out
- ✅ **RealtimeNotificationPort** (`app/realtime/`) — WebSocket pub/sub을 저장소에서 분리
- ✅ PII 영속: `EncryptedSqliteRunInputStore` / `EncryptedSqliteSuiteInputStore` (AES-GCM)
- ✅ `list_runs()` 전수 스캔 제거 — `scripts/check_architecture_gates.py` (AG-001~AG-005)

### Phase 3. 런타임 추상화 — ✅ 완료

- ✅ `ExecutionGateway` 포트 (`WorkerExecutionGateway` → 워커 `SessionServer` / `SimulatedExecutionGateway`)
- ✅ sync API·스레드 모델·런타임 수명을 워커 `SessionServer` 뒤로 이동(API 프로세스에 브라우저 없음)
- ✅ `E2E_EXECUTION_MODE=remote` 시 Redis job broker + 워커 세션 리스

### Phase 4. 실행 분리 — ✅ 완료

- ✅ Web 프로세스와 Worker 프로세스 분리 (`worker/` + `scripts/run_local.py`)
- ✅ Redis session registry + heartbeat — OTP `WAITING_INPUT` 시 worker 생존이면 API 재기동 후 재개 가능
- ✅ `RunExecutionQueue` → `JobQueuePort` (`RedisJobQueue` / `InMemoryJobQueue`)
- 남은 작업: Playwright MCP Gateway 어댑터 (`worker/` HTTP surface 확장), 시스템/계정 단위 동시 실행 제어

### Phase 3 (ideal). Operational Policy — ✅ 완료

- ✅ `ModuleExecutionPolicy` / `SystemExecutionPolicy` (`app/domain/execution_policy.py`) — 매니페스트 `execution_profile`·`max_retries`·`retryable_on`·`partial_rerun_allowed`
- ✅ `RunStateMachine.decide_post_step_failure` / `decide_partial_rerun` + `RunAggregate.record_retry` / `prepare_partial_rerun`
- ✅ `ExecutionGateway.resume_from_step` — 부분 재실행 세션 재개
- ✅ `ProfilePartitionedRunQueue` — `E2E_RUN_CONCURRENCY_{HEAVY,LIGHT,INTERACTIVE}` 프로필별 큐
- ✅ `POST /api/runs/{run_id}/rerun?from_module={module_id}` + `RunCommandPort.rerun_from_module`

### Phase 5. Automation Bounded Context — ✅ 완료

- ✅ `app/automation/` — BDR 4계층 (Scenario → Flow → PageObject ACL)
- ✅ `app/systems/*/steps/` 제거 — 6시스템 전부 automation BC로 이전
- ✅ 자가 치유 approve: 소스 직접 패치 금지 → `artifacts/healing_patches/` 패치 파일만 생성
- ✅ contract tests (`tests/contract/`)

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

> **진행 상태 (2026-07):** 이상적 아키텍처 리팩토링 3단계(CQRS → Worker → Automation BC) **완료**.
>
> - **Write path**: `RunAggregate` → `SqliteRunWriteRepository` + domain event store + transactional outbox → `OutboxRelay`
> - **Read path**: projection tables + 화면형 질의 포트(`RunSummaryQueryPort`/`ModuleHistoryQueryPort`/`SuiteSummaryQueryPort`) — 목록/집계/실시간 팬아웃 모두 blob 미접근, 필터·정렬·페이지는 SQL
> - **Realtime**: `RealtimeNotificationPort` (저장소와 분리) — `RealtimeProjector` 는 fat event payload 만으로 WS 를 조립(blob 재수화 없음)
> - **Execution**: `E2E_EXECUTION_MODE=local`(개발) / `remote`(prod: `worker/` + Redis)
> - **Automation**: `app/automation/` BC — `systems/*/steps/` 삭제됨
>
> **방향 확정(SSOT):** 목표는 (B) out-of-process 워커 — **달성**. `E2E_EXECUTION_MODE=remote` + `scripts/run_local.py` (로컬 Redis). OTP 재개는 worker heartbeat + session lease가 유효할 때 API 재기동 후에도 가능. worker 미가동·lease 만료 시에만 `reconcile_interrupted_runs`가 `CANCELLED` 봉인.

이 목표 구조로 가면 아래가 가능해진다.

- 서버 재시작 후 Run 상태 유지 (✅ SQLite + encrypted input store)
- 실행 격리 (✅ `worker/` 프로세스 `SessionServer` + `WorkerExecutionGateway`)
- 병렬도 제어 (✅ `RedisJobQueue` + `E2E_RUN_CONCURRENCY`)
- 테스트 모듈과 브라우저 구현 분리 (✅ `ExecutionGateway` + `app/automation/` BC)
- Playwright MCP 기반 이관 (worker HTTP surface 준비; MCP 어댑터는 후속)

## 14. 결론

현재 소스코드는 **이상적 아키텍처 기준 3단계 리팩토링이 완료된** 웹 트리거형 E2E 플랫폼이다.

정리하면 현재 상태는 아래다.

- CQRS + Event Sourcing(outbox) + projection 기반 조회
- Out-of-process 브라우저 실행 (`worker/` + Redis)
- Automation Bounded Context (`app/automation/`: Flow + PageObject)
- 웹에서 시스템 실행·Suite 순차 점검·실시간 대시보드·OTP pause/resume
- manifest 기반 확장 + contract tests

앞으로의 핵심 작업은 Playwright MCP Gateway 어댑터 정식화와 운영 환경 Redis/Worker 스케일링 튜닝이다.
