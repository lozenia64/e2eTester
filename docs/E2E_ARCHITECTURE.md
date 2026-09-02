# E2E Tester 아키텍처

> **SSOT:** 플랫폼 구조·폴더 트리(§3)·API(§4)·상태 모델(§5). 시나리오: `docs/scenarios/{code}.md`. 설치·env: `docs/INSTALL.md`. 문서 규칙: `docs/DOCS_GOVERNANCE.md`. 기계 검증: `scripts/check_docs_consistency.py`.

## 1. 요약

FastAPI 대시보드가 manifest 기반 Run/Suite 를 오케스트레이션하고, Playwright 실행은 `worker/` 프로세스(`WorkerExecutionGateway`)에 위임한다. 상태는 `domain_events` 스트림이 진실이며 `aggregate_snapshots` 는 파생 캐시다. 실시간 알림은 transactional outbox → `OutboxRelay` → `RealtimeProjector` 단일 파이프라인이다. 모듈 로그만 예외로 이벤트 스토어를 거치지 않는다.

```text
Browser → FastAPI (app/main.py, AppContainer)
  → RunService / SuiteService (순수 RunStateMachine·RunAggregate·SuiteStateMachine·SuiteAggregate)
  → ExecutionGateway → worker/SessionServer → app/automation/ (Flow + PageObject)
  → SqliteRunWriteRepository + outbox → OutboxRelay → projections · EventBus · WebSocket
```

## 2. 실행·영속 핵심

- **API / 워커 분리:** API 프로세스에 Playwright 없음. `E2E_EXECUTION_MODE=remote` + Redis + `scripts/run_local.py`.
- **공유 브라우저 세션:** Run 내 모듈 순차 실행, OTP 일시정지 시 세션 유지. 체크포인트(`SessionCheckpointStorePort`)로 재기동 복구 가능.
- **자동 복구 루프(`SPEC-RUN-006`):** 모듈이 `ERROR` 로 실패하면 실패 신호(`FailureSignal`)에 따라 복구 등급(`RecoveryTier`)을 골라 재시도 전 세션을 되감는다 — tier 0(제자리 재시도) → tier 1(`ExecutionGateway.recover_session` 으로 모듈 진입 URL 재이동) → tier 2(세션 재개설, Run 당 `E2E_RECOVERY_TIER2_BUDGET` 예산). `ANOMALY`(사이트 이상)는 안전 규칙으로 절대 자동 복구하지 않는다. 재시도로 통과한 모듈은 `recovered` 플래그로 Run 상세·일간 현황·완료 메일에 노출된다. 예약 Run 이 `ERROR` 로 끝나면 `E2E_AUTO_RERUN_ENABLED` 설정 시 실패 모듈부터 1회 자동 재실행(같은 Run 을 제자리 재개, `E2E_RUN_MAX_DURATION_S` 상한 적용)한다.
  - **tier 2 현행 한계:** 등급 이름(`REPLAY_FROM_LOGIN`)과 달리, `worker/session_server.py` 의 `_reopen_session` 은 브라우저 런타임을 재구축할 뿐 **로그인 모듈을 다시 주행하지 않는다**. 공용 `user_data_dir` 을 쓰는 레거시 3종(HOM/FP/HRP)은 재구축이 Chromium 프로필 잠금에 걸려 tier 0 으로 안전하게 폴백하고, 그 외 시스템은 새 컨텍스트에 쿠키가 없어 재시도가 미인증으로 실패한다 — 즉 **현재 tier 2 는 `SESSION_LOST` 에 대해 실질적 복구 이득이 없다**. 로그인 재주행 구현은 후속 작업이며, 그래서 `E2E_EXECUTION_MODE=remote` / `E2E_AUTO_RERUN_ENABLED=true` 를 운영에서 켜기 전에 실브라우저 수동 검증(`SPEC-RUN-006` 계획서 Step 4)이 필수 게이트로 남아 있다.
- **Suite:** 이벤트 기반 Saga. `RunCommandPort` 로 하위 Run 구동. `selected_system_codes` 로 시스템 부분 선택.
- **종료 3분류:** `PASSED`(정상) / `ANOMALY`(사이트 이상) / `ERROR`(도구 실패). 우선순위 ERROR > ANOMALY > PASSED.
- **CQRS:** 쓰기 `RunWriteRepositoryPort` + 이벤트. 읽기 `*QueryPort` projection 테이블. REST/WS 는 `RunView`/`SuiteView` 만.

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
      routes_dashboard.py          # HTML 페이지 라우트 (/, /runs/execute, /runs/history, /presets, /schedules, /anomalies, /insights, /self-healing, /admin/*)
      routes_daily.py              # 일간 점검 현황 데이터 API (/api/dashboard/daily)
      routes_runs.py
      routes_presets.py            # 인증 프리셋 CRUD (/api/presets)
      routes_suites.py
      routes_systems.py
      routes_schedules.py
      routes_trigger.py            # 모바일 즉시 점검 (/m/{trigger_token}, /api/trigger/*)
      routes_wall.py               # 비인증 상황판 (/wall, /wall/fragment)
      routes_anomalies.py          # 이상징후 인박스 (/api/anomalies*)
      routes_insights.py           # 시스템 인사이트 (/api/systems/{code}/health|timeline|modules/breakdown)
      routes_healing.py            # 자가 치유 센터 (/api/healing/*)
      routes_admin.py
      routes_otp.py                # SMS 중계 인바운드 OTP (/api/otp/inbound)
      routes_identity.py           # /login, /auth/*, /account/password
      ws_runs.py
      ws_suites.py
    contexts/identity/             # 인증·사용자(identity) 컨텍스트 (구 app/auth)
      dependencies.py
      jwt.py
      service.py
      models.py
      infrastructure/
        user_repository.py         # UserRepositoryPort + 인메모리 어댑터(테스트용)
        sqlite_user_repository.py  # SQLite 사용자 어댑터(기본 사용)
    core/
      schedule_time.py             # schedule_day_label / resolve_schedule_timezone (프로젝션 결정성)
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
          events.py                # RunEvent 판별 유니온 + RunEventRecord (타입화 도메인 이벤트)
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
        contracts/
          ports.py                 # RunWriteRepositoryPort / RunSummaryQueryPort / RunLogStorePort 등
          query_rows.py            # RunSummaryRow / ModuleHistoryRow / Page / RunSummaryFilter 등
          records.py               # RunRecord / RunModuleRecord (영속 DTO)
        infrastructure/
          sqlite_run_write_repository.py
          codec.py                   # RunEventCodec: RunEventRecord ↔ EventEnvelope
          sqlite_run_control_store.py
          sqlite_run_log_store.py
          sqlite_run_summary_query.py
          sqlite_module_history_query.py
          sqlite_session_checkpoint_store.py
          encrypted_run_input_store.py
          in_memory_run_repository.py
          in_memory_run_control_store.py
          in_memory_run_input_store.py
          in_memory_run_log_store.py
          in_memory_run_summary_query.py
          run_snapshot_fallback.py
          hydration.py             # RunHydrator / RunProjectionLoader
          failure_analysis_subscriber.py
          backfill/                # run_history_index / module_history_index 백필
          migration/legacy_blob_migration.py
      suite/
        domain/
          aggregate.py             # SuiteAggregate: Suite 상태 전이 규칙·불변식(순수, RunAggregate 와 동형)
          state_machine.py         # SuiteStateMachine: Suite 사가 결정 전이표(순수)
          decider.py               # Suite Decider: decide(cmd,state)→events / evolve (순수, 이벤트=진실)
          commands.py              # SuiteCommand 군(BeginSuite/StartStep/... — decide 입력 의도)
          events.py                # SuiteEvent 판별 유니온 + SuiteEventRecord (타입화 도메인 이벤트)
        application/
          service.py               # SuiteService: 이벤트 기반 Saga(결정=StateMachine, 변경=Aggregate 위임)
        views/
          view.py                  # SuiteView: Suite 읽기 모델 프로젝션(RunView 와 동일 규율)
        contracts/
          ports.py                 # SuiteSummaryQueryPort / SuiteControlStorePort / SuiteWriteRepositoryPort 등
          query_rows.py            # SuiteSummaryRow / SuiteStepRow
          records.py               # SuiteRecord / SuiteStepRecord (영속 DTO)
        infrastructure/
          sqlite_suite_write_repository.py
          codec.py                   # SuiteEventCodec: SuiteEventRecord ↔ EventEnvelope
          sqlite_suite_repository.py
          sqlite_suite_control_store.py
          sqlite_suite_summary_query.py
          encrypted_suite_input_store.py
          in_memory_suite_repository.py
          in_memory_suite_control_store.py
          in_memory_suite_input_store.py
          hydration.py             # SuiteHydrator (EventBus SuiteFinished payload)
    domain/                        # 공유 도메인 커널(run+suite 공용)
      execution_policy.py          # ModuleExecutionPolicy / SystemExecutionPolicy (재시도·부분재실행·execution_profile)
      snapshots.py                 # RunSnapshot / SuiteSnapshot (frozen, aggregate.to_snapshot())
      summary_fields.py            # run_summary_fields / suite_summary_fields (fat event 요약)
    composition/
      container.py                 # AppContainer — 컴포지션 루트(저장소·게이트웨이·OutboxRelay·서비스 배선)
    platform/                      # 공유 인프라·기술 유틸(특정 컨텍스트 무소속)
      artifact_manager.py          # 아티팩트 경로·파일 관리(실행 평면 아님 — 오케스트레이션이 경로 계산)
      db.py                        # JsonTableStore + DEFAULT_DB_PATH
      snapshot_rebuild.py          # aggregate_snapshots 이벤트 폴드 재구성
      security/
        input_crypto.py            # AES-GCM 입력 암호화 프리미티브
      eventing/                    # 이벤트 소싱·아웃박스·도메인 버스·프로젝션 핸들러
        envelope.py                # EventEnvelope: domain_events/outbox 직렬화 봉투(물리 계층)
        event_store.py             # SqliteEventStore (domain events append-only)
        outbox.py                  # SqliteOutbox (transactional outbox)
        relay.py                   # OutboxRelay → projection · EventBus · RealtimeProjector
        hydration.py               # AggregateHydratorPort (제네릭 하이드레이션 포트)
        support.py                 # SqliteDatabase + projection 스키마
        bus.py                     # EventBus + RunFinished/RunWaitingInput/RunResumed/SuiteFinished
        handlers.py                # ProjectionHandlers (CQRS read-model 테이블 갱신)
        subscribers/
          email_notification.py    # EmailNotificationSubscriber (종료 메일)
    realtime/
      adapter.py                   # RealtimeNotificationPort 구현
      listener_registry.py         # WebSocket 리스너 큐 레지스트리(프로세스-로컬)
      projector.py                 # RealtimeProjector (OutboxRelay가 WS fan-out 담당)
      ports.py                     # RealtimeNotificationPort
      redis_fanout.py              # Redis pub/sub fan-out (다중 API 프로세스)
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
      infrastructure/
        ports.py                   # HealingEventStorePort / HealingPolicyStorePort / HealingPatchStorePort
        sqlite_healing_stores.py   # SQLite 치유 이벤트/정책/패치 어댑터 + 동기 정책 리더
    notifications/
      run_completion_email.py
      report_renderer.py
      infrastructure/
        sqlite_email_notification_dedup.py
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
    contexts/insights/contracts/
      query_rows.py                # AnomalyInboxRow / DailyStatusRow / StatsRollupRow 등
    contexts/insights/infrastructure/
      ports.py                   # StatsQueryPort / DailyStatusQueryPort / Anomaly* 포트
      sqlite_stats_query.py      # StatsQueryPort SQLite 어댑터
      in_memory_stats_query.py   # StatsQueryPort 인메모리 어댑터(테스트)
      sqlite_daily_status_query.py # DailyStatusQueryPort
      sqlite_anomaly_handling_store.py # AnomalyHandlingStorePort
      sqlite_anomaly_inbox_query.py # AnomalyInboxQueryPort
      module_settings_repository.py # ModuleSettingsRepositoryPort + 인메모리 어댑터
      sqlite_module_settings_repository.py # SQLite 모듈별 수동 업무 시간 설정
    contexts/preset/application/
      service.py                   # PresetService: 인증 프리셋(사용자별 격리·검증 후 저장)
    contexts/preset/infrastructure/
      ports.py                   # PresetRepositoryPort
      sqlite_preset_repository.py # SQLite 인증 프리셋 어댑터(auth_presets 테이블, PII 의도 영속)
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
      infrastructure/
        ports.py                   # ScheduleRepositoryPort
        schedule_repository.py     # 인메모리 예약 어댑터
        sqlite_schedule_repository.py # SQLite 예약 어댑터(기본 사용)
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
    web/
      frontend/
        entries/
          dashboard.ts              # 일간 대시보드 페이지 엔트리 (Vite)
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
        app.js                     # 실행 화면(execute)·Run/Suite 화면 공용 스크립트
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
    INSTALL.md                     # 설치·실행·환경변수
    E2E_ARCHITECTURE.md            # 플랫폼 아키텍처·API·폴더 트리
    otp_relay.md                   # OTP SMS 중계기 구성 가이드
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
  AGENTS.md
```

## 5. 계층 요약

오케스트레이션(`RunService`/`SuiteService`)은 `RunStateMachine`·`RunAggregate`·`SuiteStateMachine`·`SuiteAggregate` 에 결정·변경을 위임하고, 브라우저는 `ExecutionGateway` 포트 뒤 `worker/SessionServer` 가 실행한다. 저장소는 포트-어댑터(CQRS write/read 분리). 부수 관심사(AI·메일·치유)는 `EventBus` 구독자.

### 5.2 API 계층

> **인프라 라우트 제외:** `/favicon.ico`, `/apple-touch-icon*.png`, `/static`, `/artifacts` 는 API 계약이 아니며 문서·가드 대상에서 제외한다(`include_in_schema=False` 와 동일).

- `GET /`
- `GET /wall`
- `GET /wall/fragment`
- `GET /runs/execute`
- `GET /login`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `GET /account/password`
- `POST /auth/change-password`
- `GET /runs/history`
- `GET /presets`
- `GET /runs/{run_id}`
- `GET /suites/{suite_id}`
- `GET /schedules`
- `GET /anomalies`
- `GET /self-healing`
- `GET /insights`
- `GET /systems/{system_code}/insights`
- `GET /api/systems`
- `GET /api/systems/{system_code}/health`
- `GET /api/systems/{system_code}/timeline`
- `GET /api/systems/{system_code}/modules/breakdown`
- `GET /api/anomalies`
- `GET /api/anomalies/assignees`
- `PATCH /api/anomalies/{module_run_id}`
- `GET /api/healing/events`
- `GET /api/healing/metrics`
- `GET /api/healing/durability`
- `GET /api/healing/policy`
- `PUT /api/healing/policy`
- `GET /api/healing/patches`
- `POST /api/healing/patches/{patch_id}/approve`
- `POST /api/healing/patches/{patch_id}/reject`
- `GET /api/healing/patches/{patch_id}/download`
- `GET /api/dashboard/daily` — 각 시스템 항목에 `systems[].summary_badge` (`label`, `tone`) 포함
- `GET /api/dashboard/daily/summary`
- `GET /api/dashboard/daily/fragments/{zone}`
- `GET /api/dashboard/daily/fragments/system/{system_code}/panel`
- `GET /api/runs`
- `GET /api/runs/coverage` — 시스템 × 7일 점검 커버리지(사용자 권한 범위). 관리자 전용 `/api/admin/dashboard` 와 같은 read model 을 쿼리 계층 시스템 필터로 재사용한다
- `GET /api/runs/day` — 격자 셀 드릴다운. 그 날 그 시스템의 Run 전량(실행자 필드 제외)
- `POST /api/runs/systems/{system_code}`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/nodes`
- `POST /api/runs/{run_id}/otp`
- `POST /api/runs/{run_id}/cancel`
- `POST /api/runs/{run_id}/rerun`
- `GET /api/presets`
- `POST /api/presets`
- `PUT /api/presets/{preset_id}`
- `DELETE /api/presets/{preset_id}`
- `GET /api/suites`
- `POST /api/suites`
- `GET /api/suites/{suite_id}`
- `POST /api/suites/{suite_id}/cancel`
- `POST /api/suites/{suite_id}/otp`
- `POST /api/otp/inbound`
- `GET /api/schedules`
- `GET /api/schedules/board`
- `GET /api/schedules/calendar`
- `POST /api/schedules/systems/{system_code}`
- `POST /api/schedules/suites`
- `GET /api/schedules/{schedule_id}`
- `PUT /api/schedules/{schedule_id}`
- `GET /api/schedules/{schedule_id}/history`
- `POST /api/schedules/{schedule_id}/toggle`
- `POST /api/schedules/{schedule_id}/run-now`
- `POST /api/schedules/{schedule_id}/pause-until`
- `POST /api/schedules/{schedule_id}/duplicate`
- `DELETE /api/schedules/{schedule_id}`
- `GET /m/{trigger_token}`
- `POST /api/trigger/{trigger_token}`
- `GET /api/trigger/{trigger_token}/status`
- `POST /api/trigger/{trigger_token}/otp`
- `WS /ws/runs/{run_id}`
- `WS /ws/suites/{suite_id}`
- `GET /api/admin/dashboard`
- `GET /api/admin/runs/board`
- `GET /api/admin/runs/heatmap`
- `GET /api/admin/runs`
- `GET /api/admin/runs/export.csv`
- `DELETE /api/admin/runs/{run_id}`
- `GET /api/admin/ops/snapshot`
- `GET /api/admin/stats/usage`
- `GET /api/admin/stats/savings/csv`
- `GET /api/admin/systems`
- `GET /api/admin/module-settings`
- `PUT /api/admin/module-settings/systems/{system_code}`
- `PUT /api/admin/module-settings/{module_id:path}`
- `GET /api/admin/users`
- `POST /api/admin/users`
- `PATCH /api/admin/users/{user_id}/active`
- `DELETE /api/admin/users/{user_id}`
- `PUT /api/admin/users/{user_id}/systems`
- `GET /admin`
- `GET /admin/runs`
- `GET /admin/users`
- `GET /admin/stats`
- `GET /admin/ops`
- `GET /admin/modules`

OTP·취소·부분재실행: `POST /api/runs/{run_id}/otp`, `POST /api/runs/{run_id}/cancel`, `POST /api/runs/{run_id}/rerun` (`?from_module=`). Suite OTP: `POST /api/suites/{suite_id}/otp`. SMS 중계: `POST /api/otp/inbound`.

### 5.3 상태·이벤트·아티팩트

**Run 상태:** PENDING, RUNNING, WAITING_INPUT, PASSED, ANOMALY, ERROR, CANCELLED (+ legacy FAILED).

**Module 상태:** 위 + QUEUED, BLOCKED, SKIPPED.

**Suite:** Run 과 동형. SuiteStep 에 SKIPPED(시스템 제외).

**WebSocket (`/ws/runs/{run_id}`, `/ws/suites/{suite_id}`):** `snapshot`, `run_*`/`suite_*`, `module_*`, `module_log`.

**아티팩트:** `artifacts/{run_id}/{module_id}/execution.log`, `final.png` — 모듈 종료 시 엔진이 캡처.

## 6. 시스템 시나리오 문서

시스템별 흐름·모듈·입력은 `docs/scenarios/{system_code}.md` (manifest 1:1). SUITE 는 manifest 전체 모듈 실행, 시스템 포함은 `selected_system_codes`.

- [hom](scenarios/hom.md) · [mhm](scenarios/mhm.md) · [fp](scenarios/fp.md) · [hrp](scenarios/hrp.md) · [hwtc](scenarios/hwtc.md) · [chbot](scenarios/chbot.md)
