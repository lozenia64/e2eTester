# E2E Tester — Spec-Driven Development (SDD) 카탈로그

> **목적:** AI Agent가 기능을 구현·수정·검증할 때 참조하는 **행동 명세(Spec)** 모음.  
> **원칙:** Spec이 구현보다 선행한다. 구현은 Spec의 Acceptance Criteria를 만족해야 한다.

## SDD 워크플로

```text
1. 요청 수신 → 관련 SPEC ID 식별 (본 인덱스)
2. Spec 읽기 → 의존 SPEC·SSOT 문서 확인
3. 구현 계획 작성 → docs/superpowers/plans/ (선택)
4. 구현 → Spec의 FR/AC 충족
5. 검증 → Spec §9 테스트 요구사항 + `@pytest.mark.spec` + CI 게이트
6. Spec 갱신 → 동작 변경 시 Spec을 먼저/동시에 수정
```

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
| `SPEC-SYS-*` | 대상 시스템 E2E | `SPEC-SYS-HOM` |

## 전체 Spec 인덱스

### 거버넌스·템플릿

| ID | 파일 | 요약 |
| --- | --- | --- |
| — | [00-GOVERNANCE.md](00-GOVERNANCE.md) | SDD 규칙, SSOT 관계, Spec 수명주기 |
| — | [_TEMPLATE.md](_TEMPLATE.md) | 신규 Spec 작성 템플릿 |

### 플랫폼 (Platform)

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-PLATFORM-001 | [platform/01-architecture.md](platform/01-architecture.md) | 계층·바운디드 컨텍스트·실행 분리 |
| SPEC-PLATFORM-002 | [platform/02-event-sourcing-persistence.md](platform/02-event-sourcing-persistence.md) | 이벤트 스트림·스냅샷·CQRS |
| SPEC-PLATFORM-003 | [platform/03-execution-gateway.md](platform/03-execution-gateway.md) | ExecutionGateway·워커·큐 |
| SPEC-PLATFORM-004 | [platform/04-realtime-websocket.md](platform/04-realtime-websocket.md) | Outbox→WS·이벤트 타입 |
| SPEC-PLATFORM-005 | [platform/05-ci-gates.md](platform/05-ci-gates.md) | CI 게이트·AG-001~009 |

### 인증·권한 (Identity)

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-IDENTITY-001 | [identity/01-authentication.md](identity/01-authentication.md) | 로그인·JWT·쿠키·비밀번호 변경 |
| SPEC-IDENTITY-002 | [identity/02-authorization.md](identity/02-authorization.md) | 역할·시스템 접근 스코프 |
| SPEC-IDENTITY-003 | [identity/03-user-admin.md](identity/03-user-admin.md) | 관리자 사용자 CRUD |

### Run 오케스트레이션

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-RUN-001 | [run/01-lifecycle.md](run/01-lifecycle.md) | Run 생성·실행·상태머신·모듈 루프 |
| SPEC-RUN-002 | [run/02-otp-cancel-rerun.md](run/02-otp-cancel-rerun.md) | OTP·취소·재실행·부분재실행 |
| SPEC-RUN-003 | [run/03-queue-concurrency.md](run/03-queue-concurrency.md) | 프로필별 큐·동시성 |
| SPEC-RUN-004 | [run/04-checkpoint-resume.md](run/04-checkpoint-resume.md) | 세션 체크포인트·재기동 복구 |
| SPEC-RUN-005 | [run/05-comparison-artifacts.md](run/05-comparison-artifacts.md) | Run 비교·아티팩트·로그 |

### Suite 사가

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-SUITE-001 | [suite/01-saga-lifecycle.md](suite/01-saga-lifecycle.md) | Suite 순차 실행·OTP·취소 |

### 예약 (Scheduling)

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-SCHED-001 | [scheduling/01-scheduler.md](scheduling/01-scheduler.md) | Cron·자동 Run/Suite |
| SPEC-SCHED-002 | [scheduling/02-schedule-center.md](scheduling/02-schedule-center.md) | 예약 관리 센터 UI·API |
| SPEC-SCHED-003 | [scheduling/03-mobile-trigger.md](scheduling/03-mobile-trigger.md) | 모바일 즉시 점검 토큰 |

### 대시보드·UI

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-UI-001 | [dashboard/01-daily-dashboard.md](dashboard/01-daily-dashboard.md) | 일간 점검 현황 (랜딩) |
| SPEC-UI-002 | [dashboard/02-execute-page.md](dashboard/02-execute-page.md) | 점검 실행·SUITE 카드 |
| SPEC-UI-003 | [dashboard/03-run-suite-views.md](dashboard/03-run-suite-views.md) | Run/Suite 상세·이력·관리자 |

### 인증 프리셋

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-PRESET-001 | [presets/01-auth-presets.md](presets/01-auth-presets.md) | 내 점검 세트 CRUD |

### 운영 인텔리전스

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-INSIGHT-001 | [insights/01-anomaly-inbox.md](insights/01-anomaly-inbox.md) | 이상징후 인박스 |
| SPEC-INSIGHT-002 | [insights/02-system-insights.md](insights/02-system-insights.md) | 시스템 헬스·타임라인 |
| SPEC-INSIGHT-003 | [insights/03-admin-stats.md](insights/03-admin-stats.md) | 관리자 통계·커버리지 |

### 자가 치유

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-HEAL-001 | [healing/01-self-healing-engine.md](healing/01-self-healing-engine.md) | 런타임 셀렉터 치유 |
| SPEC-HEAL-002 | [healing/02-patch-approval.md](healing/02-patch-approval.md) | 패치 제안·승인 워크플로 |

### 외부 연동

| ID | 파일 | 요약 |
| --- | --- | --- |
| SPEC-INT-001 | [integrations/01-otp-relay.md](integrations/01-otp-relay.md) | SMS OTP 중계 |
| SPEC-INT-002 | [integrations/02-email-notification.md](integrations/02-email-notification.md) | 완료 메일 |
| SPEC-INT-003 | [integrations/03-ai-failure-analysis.md](integrations/03-ai-failure-analysis.md) | Gemini 실패 분석 |

### 대상 시스템 E2E

| ID | 파일 | 시스템 |
| --- | --- | --- |
| SPEC-SYS-REP-HOME | [systems/_shared-rep-homepage.md](systems/_shared-rep-homepage.md) | 대표홈페이지 공통 (HOM·MHM) |
| SPEC-SYS-HOM | [systems/hom.md](systems/hom.md) | 대표홈페이지(PC) |
| SPEC-SYS-MHM | [systems/mhm.md](systems/mhm.md) | 대표홈페이지(모바일) |
| SPEC-SYS-FP | [systems/fp.md](systems/fp.md) | 영업가족 위촉서류 |
| SPEC-SYS-HRP | [systems/hrp.md](systems/hrp.md) | 현장출동 홈페이지 |
| SPEC-SYS-HWTC | [systems/hwtc.md](systems/hwtc.md) | 연수원 |
| SPEC-SYS-CHBOT | [systems/chbot.md](systems/chbot.md) | 챗봇(모바일) |

## 기존 문서와의 관계

| 문서 | 역할 | SDD Spec과의 관계 |
| --- | --- | --- |
| `docs/E2E_ARCHITECTURE.md` | 아키텍처 SSOT | Spec은 **행동·AC** 중심; 아키텍처 사실은 링크 |
| `docs/scenarios/{code}.md` | 시나리오 SSOT | `SPEC-SYS-*`가 시나리오를 AC로 확장 |
| `docs/INSTALL.md` | 설치·env SSOT | Spec은 env **이름**만 참조 |
| `docs/CI.md` | CI 게이트 SSOT | `SPEC-PLATFORM-005`가 AC로 변환 |
| `docs/DOCS_GOVERNANCE.md` | 문서 거버넌스 | `00-GOVERNANCE.md`가 SDD 규칙 추가 |

**충돌 시:** 코드로 검증 가능한 사실 → 소스코드 + 가드. 행동·UX·AC → **Spec 우선**.

## Agent 지침 (요약)

1. **한 번에 하나의 SPEC ID** 범위로 작업한다.
2. Spec에 없는 동작을 추가하려면 **Spec PR을 먼저** 제안한다.
3. manifest·API·env 변경 시 Spec + 기존 SSOT 문서를 **동시 갱신**한다.
4. PR 전 `python3 scripts/ci/run_all_gates.py --profile full` 필수.
5. UI·로그·에러 메시지는 **한국어** 유지.
