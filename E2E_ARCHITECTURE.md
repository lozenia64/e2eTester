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
- 시스템은 manifest 기반으로 로드된다. (현재 기본 포함 시스템: 대표홈페이지 HOM·MHM, 접속 점검 시스템 FP·HRP·HWTC·CHBOT)
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
          -> InMemoryRunRepository
          -> WorkflowExecutor         (execution_mode -> HOM / MHM / access_common executor)
              -> Shared Playwright browser session
                  -> Split system modules (app/systems/{code}/steps/*.py)
                      -> Site

Browser
  -> FastAPI app
      -> SuiteService
          -> RunService (시스템별 Run 순차 생성·대기)
          -> InMemorySuiteRepository

FastAPI app
  -> HTML routes (/, /runs/{id}, /suites/{id})
  -> JSON APIs
  -> WebSocket stream (/ws/runs, /ws/suites)
  -> Static artifacts mount
```

현재 구조의 핵심 특징:

- 웹 요청과 실행 orchestration은 같은 프로세스에 있다.
- 워크플로 실행기는 `execution_mode`(`hom_workflow_step` / `mhm_workflow_step`) 기준으로 `app/systems/loader.py` 가 동적으로 로드한다.
- 실제 Playwright sync API 실행은 Run마다 만든 단일 스레드 `ThreadPoolExecutor`(`max_workers=1`)에서 수행한다. 같은 Run의 build/step/close 호출이 모두 이 스레드에서 돈다. (실행기에 thread executor가 없으면 `asyncio.to_thread(...)` 로 폴백)
- 하나의 Run 안에서는 공유 브라우저 세션을 유지한 채 단계형 모듈을 순차 실행한다.
- **Suite** 는 시스템 단위로 Run을 순차 생성한다. 각 시스템 Run은 별도 브라우저 세션을 갖고, Suite는 시스템 간 OTP 대기(`WAITING_INPUT`)를 중계한다.
- 모듈 로그와 상태 이벤트는 repository를 통해 WebSocket에 전파된다.

## 4. 현재 폴더 구조

```text
e2eTester/
  app/
    ai/
      failure_analyzer.py
      gemini_http.py
      gemini_models.py
    api/
      routes_dashboard.py
      routes_runs.py
      routes_schedules.py
      routes_suites.py
      routes_systems.py
      ws_runs.py
      ws_suites.py
    core/
      enums.py
      env_utils.py
      models.py
    notifications/
      run_completion_email.py
      report_renderer.py
    orchestrator/
      run_service.py
      suite_service.py
    registry/
      loader.py
    scheduling/
      cron.py
      scheduler.py
    runner/
      artifact_manager.py
      workflow_common.py
      workflow_engine.py         # BaseWorkflowExecutor (공용 실행 골격) + WorkflowRuntime 계약
      hom_workflow_executor.py   # app.systems.hom.executor 재노출
      mhm_workflow_executor.py   # app.systems.mhm.executor 재노출
    systems/
      loader.py                  # execution_mode -> 시스템별 executor 로딩
      hom/
        executor.py
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
        executor.py
        manifest.yaml
        steps/                   # hom 과 동일한 단계 구성 (모바일 selector)
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
        browser.py                 # 공용 브라우저 기동/팝업/모바일 모드/스크린샷 헬퍼
        executor.py                # AccessWorkflowExecutor
        main_access.py             # 단일 main_access 단계
      fp/
      hrp/
      hwtc/
      chbot/
    storage/
      run_repository.py
      schedule_repository.py
      suite_repository.py
    web/
      templates/
        base.html
        index.html
        run.html
        suite.html
      static/
        app.css
        app.js
    main.py
  docs/
    DOCS_GOVERNANCE.md           # 문서 SSOT 매트릭스·PR 체크리스트
    scenarios/
      hom.md
      mhm.md
      fp.md
      hrp.md
      hwtc.md
      chbot.md
  scripts/
    check_docs_consistency.py    # 문서-코드 정합성 가드
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
- `app/web/templates/base.html`
- `app/web/templates/index.html`
- `app/web/templates/run.html`
- `app/web/templates/suite.html`
- `app/web/static/app.js`
- `app/web/static/app.css`

역할:

- 시스템 카드 렌더링
- **전체 시스템 순차 점검(SUITE)** 카드: 시스템 체크박스 선택, 공통 브라우저 모드, HOM/MHM 인증 패널(선택된 시스템만), cron 예약 등록
- 조건부 입력 폼 렌더링
- 실행 모듈 선택 그래프(`module-graph`) 렌더링과 의존성 경고
- Run / Suite 화면 렌더링
- WebSocket 수신 후 노드/로그/OTP 패널 갱신

현재 UX 특징:

- 홈 화면은 “시스템 실행”과 “전체 순차 점검”을 함께 제공한다.
- 홈 화면 상단에는 상태 카드 3종(등록 시스템 수, AI 분석 설정 상태, 종료 메일 설정 상태)이 표시된다.
- 홈 화면에는 “진행 중 / 최근 Run” 패널이 있으며 `GET /api/runs` 요약을 주기적으로 불러와 렌더링한다. (메모리 기반이라 서버 재시작 시 사라짐)
- 개별 시스템 실행 전 모듈 선택 그래프에서 모듈을 개별 해제할 수 있고, 선택값은 실행 요청의 `selected_module_ids` 로 전달된다.
- **SUITE** 실행 전 시스템 체크박스에서 시스템을 개별 해제할 수 있고, 선택값은 `selected_system_codes` 로 전달된다. 미선택 시스템은 Suite step `SKIPPED` 로 남는다.
- 개별 Run 실행 시 곧바로 Run 상세 화면으로, SUITE 실행 시 Suite 상세 화면(`/suites/{suite_id}`)으로 이동한다.
- 인증 수단처럼 시스템별 실행 옵션은 manifest 의 `run_form` 정의로 렌더링된다.

### 5.2 API 계층

현재 구현:

- `GET /` (홈 대시보드 HTML)
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
- `GET /api/schedules` (예약 목록 요약, input_data / suite_systems 제외)
- `POST /api/schedules/systems/{system_code}` (개별 시스템 cron 예약 등록)
- `POST /api/schedules/suites` (전체 점검 cron 예약 등록, `selected_system_codes` 포함)
- `POST /api/schedules/{schedule_id}/toggle` (활성/비활성 전환)
- `POST /api/schedules/{schedule_id}/run-now` (즉시 1회 실행)
- `DELETE /api/schedules/{schedule_id}` (예약 삭제)
- `WS /ws/runs/{run_id}`
- `WS /ws/suites/{suite_id}`

역할:

- 시스템 목록 조회
- 최근 Run 요약 목록 조회 (`list_run_summaries`)
- Run 생성 (`selected_module_ids` 로 실행 모듈 부분 선택 가능)
- Suite 생성 (`selected_system_codes` 로 실행 시스템 부분 선택 가능, 미지정 시 전체)
- Run / Suite / 노드 조회
- OTP 재개 (`POST /api/runs/{run_id}/otp`, Suite 경유 `POST /api/suites/{suite_id}/otp`)
- Run 취소 (`POST /api/runs/{run_id}/cancel`) — 진행 중/대기 중 Run을 `CANCELLED` 로 중단
- Suite 취소 (`POST /api/suites/{suite_id}/cancel`) — 진행 중 Suite와 현재 시스템 Run을 함께 중단
- 동일 입력 재실행 (`POST /api/runs/{run_id}/rerun`) — 같은 시스템·입력·모듈 선택으로 새 Run 생성
- 실시간 상태 이벤트 스트리밍

**참고:** OTP API는 Run이 `WAITING_INPUT` 상태로 멈춰 있을 때만 의미가 있다. 어떤 인증 수단이 이 상태를 만드는지는 각 시스템 시나리오 문서를 참고한다.

### 5.3 Orchestrator 계층

현재 구현 핵심은 `app/orchestrator/run_service.py` 다.

역할:

- Run 생성 시 입력값 검증 (시스템 manifest의 `supported_auth_methods` 기준으로 `auth_method`를 검증하며, HOM·MHM은 `phone`/`kakao`만 허용하고 그 외 값은 요청 단계에서 거절)
- `selected_module_ids` 검증 (미지정 시 전체 선택, 알 수 없는 모듈·선행 모듈 누락 조합은 거절, 선택되지 않은 모듈은 `SKIPPED`)
- manifest 기준 모듈 리스트 생성
- 모듈 상태 전이 관리
- 의존성 실패 시 `BLOCKED` 처리
- OTP 대기 상태 저장(`PendingOtpState`, 공유 runtime 유지)
- OTP 제출 후 중단된 단계부터 재개
- Run 취소(`cancel_run`): 취소 플래그(`_cancel_requested`)를 세팅하고, 실행 루프가 모듈 사이에서 이를 확인해 협력적으로 중단한다. 진행 중인 단계는 끝나거나 timeout 된 뒤 멈추며, 남은 모듈은 `CANCELLED` 로 표시한다. OTP 입력 대기 중에는 루프가 돌지 않으므로 즉시 runtime 을 정리하고 종료한다.
- 동일 입력 재실행(`rerun_run`): Run 생성 시 보관한 입력값(otp_code 제외, `_run_inputs`)으로 같은 시스템·모듈 선택의 새 Run을 만든다. 입력값은 PII를 포함할 수 있어 메모리에만 보관하며 응답/WebSocket payload 로는 직렬화하지 않는다.
- 최근 Run 요약 생성(`list_run_summaries`)
- 이벤트 publish

현재 상태 전이:

Run:

- `PENDING`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED`
- `FAILED`
- `CANCELLED` (사용자가 취소한 Run)

Module:

- `PENDING`
- `QUEUED`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED`
- `FAILED`
- `BLOCKED`
- `SKIPPED`
- `CANCELLED` (Run 취소로 실행되지 않거나 중단된 모듈)

아직 없는 것:

- 재시도 정책
- 실패 모듈만 부분 재실행 (현재는 `rerun_run` 으로 동일 입력 전체 재실행만 지원)

### 5.3.1 Suite Orchestrator 계층

현재 구현 핵심은 `app/orchestrator/suite_service.py` 다.

역할:

- `selected_system_codes` 검증·정규화 (`_resolve_selected_system_codes`, `None` 이면 전체 선택)
- 선택된 시스템에 대해서만 `RunService.validate_run_request` 호출 (HOM 해제 시 HOM 인증 입력 불필요)
- 등록된 모든 시스템에 대해 `SuiteStep` 생성, 미선택 시스템은 `SKIPPED`
- `display_order` 순으로 시스템별 Run을 순차 생성 (`triggered_by="suite"`, `suite_id` 태깅)
- 한 시스템 Run이 실패해도 다음 선택 시스템은 계속 실행
- 시스템 Run의 `WAITING_INPUT`(OTP)을 Suite `WAITING_INPUT`으로 승격하고, OTP 제출 후 재개
- Suite 종료 시 통합 결과 메일 1통 발송 (`RunService.notify_suite_completion`); Suite 소속 개별 Run 종료 메일은 생략

Suite / SuiteStep 상태:

Suite:

- `PENDING`
- `RUNNING`
- `WAITING_INPUT`
- `PASSED` (선택된 시스템이 모두 통과)
- `FAILED` (선택된 시스템 중 하나라도 실패)
- `CANCELLED`

SuiteStep (시스템 단위):

- 위 상태 + `SKIPPED` (사용자가 시스템 선택에서 제외)

### 5.4 Registry 계층

현재 구현:

- `app/registry/loader.py` (`app/systems/*/manifest.yaml` 글롭 로드)
- `app/systems/hom/manifest.yaml`
- `app/systems/mhm/manifest.yaml`

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

현재 구현:

- `app/systems/loader.py` (`execution_mode` → 시스템별 executor 로딩)
- `app/runner/workflow_engine.py` (`BaseWorkflowExecutor` — 시스템 무관 실행 골격: 로그 캡처·아티팩트 수집·예외→`StepExecutionResult` 변환·OTP 일시정지(`WAITING_INPUT_PREFIX`) 해석·브라우저 종료 보호. `WorkflowRuntime` 최소 계약 Protocol)
- `app/systems/hom/executor.py` (`HomWorkflowExecutor(BaseWorkflowExecutor)`, `execution_mode = "hom_workflow_step"`)
- `app/systems/mhm/executor.py` (`MhmWorkflowExecutor(BaseWorkflowExecutor)`, `execution_mode = "mhm_workflow_step"`)
- `app/systems/access_common/executor.py` (`AccessWorkflowExecutor(BaseWorkflowExecutor)`, 접속 점검 공용 실행기)
- `app/runner/workflow_common.py` (`StepExecutionResult`, 로그 라인 기록 `LineWriter` / `write_log_line`)
- `app/runner/artifact_manager.py`
- `app/runner/hom_workflow_executor.py` / `app/runner/mhm_workflow_executor.py` (각 시스템 executor 재노출 모듈)
- `app/systems/{system_code}/steps/` 아래 분할 모듈 파일들

실행 모델:

- Run 단위로 Playwright 런타임 생성 (영속 프로파일 persistent context)
- 하나의 browser/context/page를 공유
- MHM은 `build_runtime()` 에서 페이지 생성 직후 `apply_mobile_device_mode()` 로 모바일 디바이스 모드를 먼저 적용한 뒤 접속
- 단계형 모듈을 순차 실행 (manifest의 `workflow_step` → executor의 `_run_step` 디스패치)
- 표준 출력/표준 에러를 가로채 모듈별 `execution.log` 와 라이브 WebSocket 로그로 저장
- 휴대폰인증 단계는 OTP 미입력 시 `WAITING_INPUT::` 표식을 반환해 Run을 일시정지시킴

이 구조를 택한 이유:

- 로그인 이후 세션을 다음 모듈에 전달해야 함
- 휴대폰 본인인증에서는 OTP 제출 이후에도 동일 세션으로 로그인 완료까지 이어져야 함
- 계약목록·계약상세·보험금청구·보험금청구 결과 조회/취소 등 후속 모듈은 동일 세션이 필요함

### 5.6 Storage 계층

현재 구현:

- `app/storage/run_repository.py`
- `app/storage/suite_repository.py`

역할:

- Run / Suite 객체 저장
- 모듈 로그 저장
- WebSocket listener 큐 관리

제약:

- 메모리 기반 저장소다.
- 서버 재시작 시 Run, Suite, 로그, OTP 대기 상태가 모두 사라진다.

### 5.7 AI 실패 분석 계층

현재 구현:

- `app/ai/failure_analyzer.py` (`GeminiFailureAnalyzer`)
- `app/ai/gemini_http.py` (Gemini HTTP 호출 / SSL 검증 모드 처리)
- `app/ai/gemini_models.py` (기본 Gemini 모델 체인 `DEFAULT_GEMINI_MODEL_CHAIN`·`GEMINI_MODELS` 파싱/검증)
- `app/core/env_utils.py` (환경 변수·`.env` 우선순위 해석)

역할:

- 환경 변수와 `.env` 기준으로 Gemini 설정을 읽는다. (터미널 환경 변수 우선, 없으면 `.env`)
- 실패한 모듈의 최근 로그, 다이얼로그, 현재 URL, 스크린샷을 바탕으로 원인 요약을 시도한다.
- 홈 화면에 현재 AI 분석 설정 상태(`inspect_env_status`)를 표시한다.

제약:

- 기본값은 비활성화다.
- 설정이 잘못되어도 앱은 계속 실행되며, 실패 분석만 생략될 수 있다.
- 회사망 SSL 검사 환경에서는 `E2E_GEMINI_SSL_VERIFY=false` 로 Gemini 호출의 SSL 검증만 우회할 수 있다.

### 5.8 종료 메일 알림 계층

현재 구현:

- `app/notifications/run_completion_email.py` (`RunCompletionEmailNotifier`, `GeminiReportContentComposer`)
- `app/notifications/report_renderer.py` (고정 디자인 HTML 렌더러)

역할:

- Run이 최종 종료(`PASSED`/`FAILED`)되면 Gmail SMTP로 결과 메일을 보낸다. (`WAITING_INPUT` 등 중간 상태에서는 보내지 않음)
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
- `app/storage/schedule_repository.py` (`InMemoryScheduleRepository`) — 메모리 기반 예약 저장소(RunRepository 와 동일하게 재시작 시 사라짐).
- `app/api/routes_schedules.py` — 예약 REST API.

역할:

- 홈 화면 시스템 폼에서 입력값·모듈 선택 그대로 cron 식을 붙여 **개별 시스템** 예약을 등록한다. 등록 시 `RunService.validate_run_request` 로 검증한다.
- 홈 SUITE 카드에서 브라우저 모드·시스템 선택(`selected_system_codes`)·HOM/MHM 인증 정보와 함께 **전체 점검** 예약을 등록한다 (`POST /api/schedules/suites`). 등록 시 `SuiteService.validate_suite_request` 로 검증한다.
- 예약은 `schedule_kind` 가 `system`(개별 Run) 또는 `suite`(전체 점검) 이다.
- 예약은 활성/비활성 전환, 즉시 실행(`run-now`), 삭제가 가능하다. 예약 트리거 Run 은 `triggered_by="schedule"`, `schedule_id` 로 태깅되고, Suite 예약은 `triggered_by="suite"` Run 들을 순차 생성한다.
- 백그라운드 루프는 주기적으로(기본 20초) `next_run_at` 이 지난 활성 예약을 찾아 실행하고 다음 시각을 다시 계산한다. 직전 예약 Run/Suite 가 아직 진행 중이면 중복 실행을 건너뛴다.
- 기준 타임존은 `E2E_SCHEDULE_TZ`(기본 `Asia/Seoul`).
- **이력 비교**: Run 이 `PASSED`/`FAILED` 로 종료되면 `RunService._compute_comparison` 가 같은 시스템의 직전 종료 Run 을 기준선으로 `newly_failed`(새로 실패)/`recovered`(복구)/`still_failing`(계속 실패) 모듈을 계산해 `Run.comparison` 에 담는다. Run 화면의 "직전 실행 대비 변화" 패널과 종료 메일(고정 템플릿의 "직전 실행 대비 변화" 섹션 · Gemini 콘텐츠 프롬프트 · 평문)에 반영된다.

제약:

- 예약과 비교 기준선 모두 메모리 기반이므로 서버 재시작 시 사라진다(영구 저장소 도입 시 함께 개선 대상).
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
- 워크플로 단계 모듈은 스크린샷을 `final.png` 로 남긴다.
- Run 화면에서 아티팩트 링크 노출
- 링크 경로는 `/artifacts/{run_id}/{module_id}/{filename}` 형식이다.

주의:

- 초기 단계에서 실패하면 스크린샷이 없을 수 있다.
- `ModuleDefinition.execution_mode` 의 기본값은 `simulated` 지만 현재 HOM·MHM manifest는 모두 워크플로 단계 모드를 쓰므로 시뮬레이션 경로는 사용되지 않는다. (등록된 executor가 없는 `execution_mode` 일 때만 시뮬레이션으로 동작하며, 이 경우 아티팩트가 생성되지 않는다.)

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
- `suite_step_finished`
- `suite_waiting_input`
- `suite_resumed`
- `suite_finished`

현재 payload 특징:

- Run 이벤트는 `run.model_dump(mode="json")`
- Suite 이벤트는 `suite.model_dump(mode="json")` (+ `step_index` 등 보조 필드)
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
- 실패 모듈만 부분 재실행 (취소·동일 입력 전체 재실행은 구현됨)
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

- 로그인 후 팝업 종료 안정성 보강 (휴대폰·카카오 공통)
- 카카오 인증 팝업·동의 UI 변경에 대한 selector·대기 조건 보강
- 계약목록·계약상세 조회 selector 보강
- 실패 시 디버그 아티팩트 확장 (`trace.zip`, `dom.html` 등)

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
```

```text
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
- **전체 시스템 순차 점검(Suite)** 과 시스템별 선택 실행 가능
- 실시간 모듈 노드 대시보드 존재
- 입력 대기(`WAITING_INPUT`) pause/resume 구조 존재 (Run·Suite)
- 로그인 이후 후속 모듈 실행 구조 존재
- manifest 기반 확장 포인트 존재

앞으로의 핵심 작업은 “새 모듈 추가” 자체보다, 현재 구조를 깨지 않고 저장소, 워커, MCP abstraction을 점진적으로 넣는 것이다.
