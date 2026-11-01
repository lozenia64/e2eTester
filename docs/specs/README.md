# E2E Tester — Spec-Driven Development (SDD) 카탈로그

> **목적:** AI Agent가 기능을 구현·수정·검증할 때 참조하는 **행동 명세(Spec)** 라우팅 인덱스.  
> **규칙·프로토콜 SSOT:** SDD 운영 규칙·수명주기·Agent 작업 프로토콜·`@pytest.mark.spec` 추적성은 [`00-GOVERNANCE.md`](00-GOVERNANCE.md), 전체 문서 SSOT 매트릭스·PR 체크리스트는 [`../DOCS_GOVERNANCE.md`](../DOCS_GOVERNANCE.md)를 따른다.

## Spec ID 규칙

| 접두사 | 영역 | 예시 |
| --- | --- | --- |
| `SPEC-PLATFORM-*` | 플랫폼·아키텍처·인프라 | `SPEC-PLATFORM-001` |
| `SPEC-IDENTITY-*` | 인증·권한·사용자 | `SPEC-IDENTITY-001` |
| `SPEC-RUN-*` | Run 오케스트레이션 | `SPEC-RUN-001` |
| `SPEC-SUITE-*` | Suite 사가 | `SPEC-SUITE-001` |
| `SPEC-SCHED-*` | 예약·스케줄러 | `SPEC-SCHED-001` |
| `SPEC-UI-*` | 대시보드·화면 | `SPEC-UI-001` |
| `SPEC-PRESET-*` | 인증 프리셋 | `SPEC-PRESET-001` |
| `SPEC-INSIGHT-*` | 운영 인텔리전스 | `SPEC-INSIGHT-001` |
| `SPEC-HEAL-*` | 자가 치유 | `SPEC-HEAL-001` |
| `SPEC-INT-*` | 외부 연동 | `SPEC-INT-001` |
| `SPEC-SYS-*` | 대상 시스템 E2E (공통·개별) | `SPEC-SYS-REP-HOME`, `SPEC-SYS-HOM` |

## 전체 Spec 인덱스

### 거버넌스·템플릿

| ID | 파일 | 요약 |
| --- | --- | --- |
| — | [00-GOVERNANCE.md](00-GOVERNANCE.md) | SDD 규칙, Spec 동기화·수명주기, Agent 프로토콜, `@pytest.mark.spec` 규칙 |
| — | [_TEMPLATE.md](_TEMPLATE.md) | 신규 Spec 작성 템플릿 |

### 플랫폼 (Platform)

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-PLATFORM-001 | [platform/01-architecture.md](platform/01-architecture.md) | 계층·바운디드 컨텍스트·실행 평면 분리·`AppContainer` 단일 배선 |
| SPEC-PLATFORM-002 | [platform/02-event-sourcing-persistence.md](platform/02-event-sourcing-persistence.md) | `domain_events` 스트림·Outbox·스냅샷·CQRS QueryPort·로그/PII 분리 |
| SPEC-PLATFORM-003 | [platform/03-execution-gateway.md](platform/03-execution-gateway.md) | `ExecutionGateway`·워커 `SessionServer`·실행 큐 |
| SPEC-PLATFORM-004 | [platform/04-realtime-websocket.md](platform/04-realtime-websocket.md) | Outbox→`RealtimeProjector`·Redis fan-out·WebSocket 이벤트·모듈 로그 직행 |
| SPEC-PLATFORM-005 | [platform/05-ci-gates.md](platform/05-ci-gates.md) | CI 게이트(Tier 0~3)·`AG-001~009`·`FG-001~007`·문서 정합성 가드 |

### 인증·권한 (Identity)

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-IDENTITY-001 | [identity/01-authentication.md](identity/01-authentication.md) | 로그인(`/login`, `/auth/*`)·JWT 쿠키·비밀번호 변경(`/account/password`) |
| SPEC-IDENTITY-002 | [identity/02-authorization.md](identity/02-authorization.md) | 역할(`admin`/`user`)·시스템 접근 스코프(`allowed_system_codes`) |
| SPEC-IDENTITY-003 | [identity/03-user-admin.md](identity/03-user-admin.md) | 관리자 사용자 CRUD·활성 상태·시스템 권한 설정(`/admin/users`) |

### Run 오케스트레이션

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-RUN-001 | [run/01-lifecycle.md](run/01-lifecycle.md) | Run 생성·모듈 실행 루프·상태머신·종료 3분류(`PASSED`/`ANOMALY`/`ERROR`) |
| SPEC-RUN-002 | [run/02-otp-cancel-rerun.md](run/02-otp-cancel-rerun.md) | OTP 일시정지/재개·취소·재실행·실패 지점 부분재실행 |
| SPEC-RUN-003 | [run/03-queue-concurrency.md](run/03-queue-concurrency.md) | `execution_profile`(`heavy`/`light`/`interactive`) 파티션 큐·동시성 |
| SPEC-RUN-004 | [run/04-checkpoint-resume.md](run/04-checkpoint-resume.md) | 모듈 경계 세션 체크포인트·프로세스 재기동 복구 |
| SPEC-RUN-005 | [run/05-comparison-artifacts.md](run/05-comparison-artifacts.md) | 직전 Run 비교(`RunComparator`)·아티팩트(`execution.log`, `final.png`) |
| SPEC-RUN-006 | [run/06-self-recovery-loop.md](run/06-self-recovery-loop.md) | 실패 신호(`FailureSignal`)·복구 등급(tier 0~2)·예약 Run 자동 재실행 |

### Suite 사가

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-SUITE-001 | [suite/01-saga-lifecycle.md](suite/01-saga-lifecycle.md) | Suite 이벤트 기반 사가·순차 실행·시스템 부분 선택·OTP 미러링·취소 |

### 예약 (Scheduling)

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-SCHED-001 | [scheduling/01-scheduler.md](scheduling/01-scheduler.md) | Cron 스케줄러·자동 Run/Suite·프리셋 바인딩(`preset_bindings`)·보존 정리 |
| SPEC-SCHED-002 | [scheduling/02-schedule-center.md](scheduling/02-schedule-center.md) | 예약 관리 센터(`/schedules`)·관제 보드·주간 캘린더·이력·일시정지/복제 |
| SPEC-SCHED-003 | [scheduling/03-mobile-trigger.md](scheduling/03-mobile-trigger.md) | 모바일 즉시 점검 토큰 URL(`/m/{trigger_token}`, `/api/trigger/*`) |
| SPEC-SCHED-004 | [scheduling/04-telegram-bot.md](scheduling/04-telegram-bot.md) | 텔레그램 봇 예약 즉시 실행·OTP 답장·계정 연결(`/account/telegram`) |

### 대시보드·UI

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-UI-001 | [dashboard/01-daily-dashboard.md](dashboard/01-daily-dashboard.md) | 일간 점검 현황 대시보드(`GET /`, 상태·매트릭스·활동·드로어·폴링) |
| SPEC-UI-002 | [dashboard/02-execute-page.md](dashboard/02-execute-page.md) | 점검 실행 페이지(`/runs/execute`, 마스터-디테일·SUITE/시스템 실행 조건) |
| SPEC-UI-003 | [dashboard/03-run-suite-views.md](dashboard/03-run-suite-views.md) | Run/Suite 상세(`/runs/{id}`, `/suites/{id}`)·이력(`/runs/history`)·관리자(`/admin/*`) |

### 인증 프리셋

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-PRESET-001 | [presets/01-auth-presets.md](presets/01-auth-presets.md) | 인증 프리셋 CRUD(`/presets`, `/api/presets`)·사용자별 격리·PII 암호화 |

### 운영 인텔리전스

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-INSIGHT-001 | [insights/01-anomaly-inbox.md](insights/01-anomaly-inbox.md) | 이상징후 인박스(`/anomalies`, `/api/anomalies*`)·담당자 배정·처리 상태 |
| SPEC-INSIGHT-002 | [insights/02-system-insights.md](insights/02-system-insights.md) | 시스템 인사이트(`/insights`, 헬스·타임라인·모듈 딥다이브) |
| SPEC-INSIGHT-003 | [insights/03-admin-stats.md](insights/03-admin-stats.md) | 관리자 월간 성과·7일 커버리지·Run 보드(트리맵)·사용량 통계·모듈 시간 설정·Ops |

### 자가 치유

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-HEAL-001 | [healing/01-self-healing-engine.md](healing/01-self-healing-engine.md) | 런타임 셀렉터 자가 치유 엔진(`SelfHealingEngine`)·내구성 맵·신뢰도 정책 |
| SPEC-HEAL-002 | [healing/02-patch-approval.md](healing/02-patch-approval.md) | 자가 치유 센터(`/self-healing`)·오토픽스 diff 패치 제안·승인/반려/다운로드 |

### 외부 연동

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-INT-001 | [integrations/01-otp-relay.md](integrations/01-otp-relay.md) | SMS OTP 인바운드 중계(`POST /api/otp/inbound`) |
| SPEC-INT-002 | [integrations/02-email-notification.md](integrations/02-email-notification.md) | 완료 이메일 알림(`EmailNotificationSubscriber`·Gmail SMTP·dedup) |
| SPEC-INT-003 | [integrations/03-ai-failure-analysis.md](integrations/03-ai-failure-analysis.md) | Gemini AI 실패 원인 분석(`FailureAnalyzer`·모델 체인 폴백) |

### 대상 시스템 E2E

| ID | 파일 | 시스템 |
| --- | --- | --- |
| SPEC-SYS-REP-HOME | [systems/_shared-rep-homepage.md](systems/_shared-rep-homepage.md) | 대표홈페이지 공통 (HOM·MHM 공유 Flow·도메인 상수) |
| SPEC-SYS-HOM | [systems/hom.md](systems/hom.md) | 대표홈페이지(PC) |
| SPEC-SYS-MHM | [systems/mhm.md](systems/mhm.md) | 대표홈페이지(모바일) |
| SPEC-SYS-FP | [systems/fp.md](systems/fp.md) | 영업가족 위촉서류(PC) |
| SPEC-SYS-HRP | [systems/hrp.md](systems/hrp.md) | 현장출동 홈페이지(PC) |
| SPEC-SYS-HWTC | [systems/hwtc.md](systems/hwtc.md) | 연수원(PC) |
| SPEC-SYS-CHBOT | [systems/chbot.md](systems/chbot.md) | 챗봇(모바일) |
