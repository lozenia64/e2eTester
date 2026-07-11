# 소스코드 ↔ 문서 정합성: 이상적 통합 실행 계획 (IDEAL_STATE_PLAN)

> **작성 기준**: 저장소 전체 소스(약 230 파일)와 문서 전체(README.md, E2E_ARCHITECTURE.md, CLAUDE.md,
> docs/DOCS_GOVERNANCE.md, docs/otp_relay.md, docs/ARCHITECTURE_REVIEW_IDEAL.md, docs/scenarios/*.md 6종,
> .env.example, PR 템플릿, CI 워크플로)를 교차 대조한 결과다. 판단 기준은 "지금 작동하는가"가 아니라
> "이 소프트웨어는 어떤 모습이어야 가장 이상적인가"이며, 마이그레이션 비용·하위 호환은 판단에서 배제했다.
>
> **검증 상태 스냅샷(분석 시점)**: `python3 scripts/check_docs_consistency.py` 통과,
> `python3 -m pytest tests/ -q` 237 passed, `ruff check .` / `ruff format --check .` 통과.
> 즉 기존 자동 가드는 전부 초록인데도 아래 표류가 존재한다 — 가드의 사각(단방향 검사, 스캔 범위)이
> 이번 계획의 핵심 교정 대상 중 하나다.
>
> **실행 규칙**: 아래 순서는 논리적 의존관계(코드 변경 → 문서 갱신 → 가드 강화) 순이다.
> 각 항목은 이 파일만 보고 이어서 작업할 수 있도록 대상 파일·현재→목표·근거를 포함한다.

---

## 1단계 — 코드 변경 (문서의 주장을 참으로 만드는 방향이 이상적인 것)

- [ ] **1. `RunAggregate.attach_comparison` 신설 — 서비스의 직접 도메인 변이 제거**
  - 대상: `app/orchestrator/run_service.py:808` (`run.comparison = await self._comparator.compute(run)`),
    `app/domain/run_aggregate.py`, `tests/test_run_aggregate.py`
  - 현재→목표: `_finalize_run` 이 도메인 필드를 직접 대입 → `RunAggregate.attach_comparison(comparison)`
    메서드를 신설해 애그리거트 경유로 변이.
  - 근거: CLAUDE.md·E2E_ARCHITECTURE §5.3·ARCHITECTURE_REVIEW_IDEAL 부록이 일제히
    **"`app/domain` 밖 직접 도메인 필드 대입 0건 (grep 으로 증명 가능)"** 을 주장하나 이 지점이 반례.
    "애그리거트 = 유일 변이자" 원칙을 코드로 참이 되게 만드는 쪽이(문서 주장을 약화시키는 쪽보다) 이상적.

- [ ] **2. 로그 하이드레이션(`module.logs` 대입)을 도메인 메서드로 이동**
  - 대상: `app/orchestrator/run_service.py:121-125` (`_attach_logs` 안의 `module.logs = ...`),
    `app/domain/run_aggregate.py`, `tests/test_run_aggregate.py`
  - 현재→목표: 읽기 모델 조립 시 서비스가 `RunModule.logs` 를 직접 대입 →
    `RunAggregate.hydrate_logs(logs_by_module)`(또는 동등한 도메인 조립 메서드)로 이동.
  - 근거: 항목 1과 동일한 "직접 변이 0건" 불변식의 두 번째(마지막) 반례. 이 둘을 없애면
    grep(`\b(run|module|suite|step)\.[a-z_]+ = ` 류)이 실제로 0건이 되어 문서 주장이 기계 검증 가능해진다.

- [ ] **3. OTP 중계 다건 대기 시 선택 기준을 'OTP 대기 시작 시각'으로 교정**
  - 대상: `app/orchestrator/run_service.py:439-466` (`submit_otp_to_waiting`),
    `app/storage/ports.py` + `sqlite_run_control_store.py` + `run_control_store.py`
    (pending 컨텍스트에 대기 진입 timestamp 추가), `docs/otp_relay.md` §1, `README.md` OTP 중계 절
  - 현재→목표: 후보 다건 시 `run.requested_at`(Run **생성** 시각) 내림차순 → pending(WAITING_INPUT 진입)
    시각 내림차순 선택.
  - 근거: README·otp_relay.md 는 "가장 최근에 **요청**된 Run(방금 도착한 SMS 에 대응)"을 약속한다.
    SMS 요청 시각의 올바른 프록시는 OTP 대기 진입 시각이지 Run 생성 시각이 아니다 — 먼저 생성됐지만
    나중에 OTP 대기에 들어간 Run 이 공존하면 현재 코드는 잘못된 Run 에 코드를 주입한다(예측 가능성·안전성).
    코드 기준 이상형(생성 시각)보다 문서 기준 이상형(요청 시각)이 의미론적으로 우월하므로 코드를 문서에 맞춘다.

## 2단계 — 문서 갱신 (코드가 옳고 문서가 낡은 것)

- [ ] **4. CLAUDE.md 'unit-test suite/린터 없음' 서술 폐기 — pytest·ruff·CI 3잡 명시**
  - 대상: `CLAUDE.md` Commands 절
  - 현재→목표: "There is no unit-test suite, linter, or build step. The one automated check is the docs
    consistency guard" → 실제 상태 반영: `tests/` 40파일·237개 테스트(`python3 -m pytest tests/`),
    `ruff check .` / `ruff format --check .`(pyproject.toml 설정), CI(`.github/workflows/docs-consistency.yml`)는
    check-docs + ruff + pytest **3개 잡** 실행.
  - 근거: 코드가 옳고 문서가 거짓. 같은 CLAUDE.md 가 뒤에서 `python3 -m pytest tests/` 실행을 언급해
    **내부 모순**까지 있음. 에이전트 지침 문서의 명령 절이 틀리면 자동 검증을 건너뛰게 만든다(안전성).

- [ ] **5. E2E_ARCHITECTURE §4 폴더 트리 전면 재생성**
  - 대상: `E2E_ARCHITECTURE.md` §4
  - 현재→목표: 존재하지 않는 `app/web/templates/index.html` 삭제(유령 항목). 누락 반영 —
    `app/healing/`(8파일 전체), orchestrator: `insights_*.py` 7종·`healing_service.py`·`preset_service.py`·
    `daily_dashboard.py`·`suite_view.py`, api: `routes_daily.py`·`routes_anomalies.py`·`routes_insights.py`·
    `routes_healing.py`·`routes_presets.py`·`routes_trigger.py`·`dependencies.py`,
    `scheduling/schedule_center.py`, storage: `sqlite_anomaly_handling_store.py`·`sqlite_healing_stores.py`·
    `sqlite_preset_repository.py`·`suite_input_store.py` 등 실제 파일 전부,
    templates: `dashboard/execute/runs_history/schedules/anomalies/insights/self_healing/mobile_trigger.html`
    + `admin/ops.html`, static: `dashboard/admin-ops/admin-stats/anomalies/insights/schedules/healing.js`
    + 파비콘류, 루트: `tests/`, `pyproject.toml`, `requirements-dev.txt`, `docs/otp_relay.md`,
    `docs/ARCHITECTURE_REVIEW_IDEAL.md`, `CLAUDE.md`.
  - 근거: §4 는 폴더 구조의 SSOT(DOCS_GOVERNANCE 매트릭스)인데 실제 트리와 광범위하게 불일치.
    DOCS_GOVERNANCE §1 이 "폴더 트리 표류"를 과거 사고 사례로 명시했는데 재발한 상태.

- [ ] **6. E2E_ARCHITECTURE §3 구조 다이어그램 현대화**
  - 대상: `E2E_ARCHITECTURE.md` §3 다이어그램
  - 현재→목표: `RunService → WorkflowExecutor` 직결, `SuiteService → RunService (순차 생성·대기)` 표현 →
    `RunExecutionQueue`, `RunAggregate`/`RunStateMachine`, `ExecutionGateway`(Composite → Local/Simulated),
    `SuiteService → RunCommandPort`(이벤트 사가, "대기" 없음) 반영. §5.3/5.3.1·CLAUDE.md 플로우와 정합.
  - 근거: 같은 문서 §5.3.1 이 "RunCommandPort 로 역전, 폴링·대기 제거"를 명시하는데 §3 그림이
    옛 구조를 보여줘 **문서 내부 모순**.

- [ ] **7. ERROR 메일의 운영자 라우팅 규칙 문서화 (README + E2E §5.8)**
  - 대상: `README.md` "선택 기능: 종료 메일 알림" 절, `E2E_ARCHITECTURE.md` §5.8
  - 현재→목표: 문서는 "PASSED/ANOMALY/ERROR 모두 (시스템별 수신자에게) 발송"이라고만 서술 →
    실제 코드(`app/notifications/run_completion_email.py:698-742`)의 규칙 반영:
    **ERROR(점검실패) Run/Suite 는 시스템 수신자가 아니라 `E2E_EMAIL_OPERATOR_RECIPIENTS`(운영자)에게만
    발송하고, 운영자 미설정 시 생략** — 제목 접두사 `[E2E][OPERATOR]`. README 환경변수 카탈로그에
    `E2E_EMAIL_OPERATOR_RECIPIENTS` 항목 추가.
  - 근거: 코드 동작이 이상적이다 — ERROR = 점검 **도구** 고장이므로 대상 시스템 담당자가 아닌 도구
    운영자 소관(3분류 철학과 일관). 문서를 코드에 맞춘다. 현재는 `.env.example` 주석에만 존재해
    "README = 환경변수 카탈로그 SSOT" 원칙 위반.

- [ ] **8. README 'OTP 대기는 본인인증 단계에 한함' 정정**
  - 대상: `README.md` "결과 확인" 절 마지막 괄호 문장
  - 현재→목표: "OTP 대기는 휴대폰인증 Run에서 본인인증 단계에 한합니다" → OTP 일시정지 지점은
    manifest 의 `requires_user_input: true` 선언 모듈이 결정하며, **FP 는 본인인증 + 서류작성 두 모듈이
    pause** 함을 반영.
  - 근거: `app/systems/fp/manifest.yaml` 이 `fp.identity.verification`·`fp.document.writing` 둘 다
    `requires_user_input: true`, `docs/scenarios/fp.md` §3.3 도 서류작성 중 WAITING_INPUT 을 서술 —
    README 만 사실과 불일치. 일시정지 정책의 SSOT(manifest 선언)를 가리키는 서술이 이상적.

- [ ] **9. E2E_ARCHITECTURE 소소 정정 묶음 (§5.4 / §7 / §8 / §10 / §12)**
  - 대상: `E2E_ARCHITECTURE.md` §5.4, §7, §8, §10.1, §12
  - 현재→목표:
    1. §5.4 "현재 구현"이 hom/mhm manifest 2개만 나열 → 6개 시스템 전부.
    2. §7 "현재 사용 중인 필드 타입은 `text` / `select`" → `text` / `select` / **`password`**
       (`fp.ssn_back`, `hrp.password`, `hwtc.password` 가 password 타입 — 마스킹이라는 실동작 차이).
    3. §8 "워크플로 단계 모듈(`hom_workflow_step` / `mhm_workflow_step`)은 로그를 남긴다" →
       전 시스템 공통(`{code}_workflow_step`) 서술.
    4. §10.1 stale 항목 재평가: "오류 분류 체계"는 PASSED/ANOMALY/ERROR 3분류로 이미 구현 →
       제거 또는 잔여 범위 명시; "ModuleContext/ModuleResult 표준화"는 `StepContext`/`StepOutcome` 으로
       상당 부분 실현 → 현황 반영. §12 Phase 체크 표기 재점검.
  - 근거: 전부 코드가 앞서고 문서가 낡은 사례("사소한 차이도 작업 항목화" 원칙).

- [ ] **10. CLAUDE.md 누락 서브시스템 보강**
  - 대상: `CLAUDE.md`
  - 현재→목표:
    1. 로그인 후 첫 화면 = **일간 점검 현황 대시보드**(`GET /` + `GET /api/dashboard/daily`,
       `app/orchestrator/daily_dashboard.py` + `dashboard.js`), Run 트리거 UI 는 `/runs/execute`,
       Run 이력은 `/runs/history` 라는 UX 구조 요약 추가.
    2. **인증 프리셋** 서브시스템(`PresetService`, `routes_presets.py`, `SqlitePresetRepository` —
       PII 의도 영속 + 소유자 격리 + SUITE 카드의 프리셋 강제) 요약 추가.
    3. API DI 불릿의 프로바이더 목록에 `get_insights_service`/`get_preset_service`/`get_run_queue`/
       `get_ops_service`/`get_app_settings`/`get_otp_relay_token`/`get_otp_relay_regex` 반영
       (실제 `app/api/dependencies.py` 와 1:1).
  - 근거: CLAUDE.md 는 에이전트용 코드베이스 요약 SSOT 인데 사용자 대면 주요 서브시스템 2개(첫 화면·
    프리셋)가 통째로 빠져 있고 DI 목록이 코드와 불일치.

- [ ] **11. 시나리오 문서 미세 정정 (hom/mhm 파일명 표기, chbot 생년월일)**
  - 대상: `docs/scenarios/hom.md` §2, `docs/scenarios/mhm.md` §2, `docs/scenarios/chbot.md` §3.2
  - 현재→목표: (1) "`hom.yaml`/`mhm.yaml` `order` 기준" → 실제 파일명 `manifest.yaml`.
    (2) chbot "생년월일(6자리)" → manifest help_text·코드(`simple_auth.py` 의 `_normalize_birthdate`:
    8자리는 앞 2자리 제거)와 일치하게 "6자리(YYMMDD) 또는 8자리(YYYYMMDD, 자동 정규화)".
  - 근거: 시나리오 문서는 해당 영역 SSOT — 파일명·입력 계약의 오기도 방치하지 않는다.

- [ ] **12. README 환경변수 카탈로그 완결 (`E2E_WORKSPACE_DIR` 등)**
  - 대상: `README.md`, (`.env.example` 은 예시값 유지)
  - 현재→목표: 코드가 읽지만(`app/core/settings.py:116`, `access_common/browser.py`) README 본문
    서술이 없는 `E2E_WORKSPACE_DIR`(MCP 프로파일 workspace 해시 기준 경로)를 의미·기본값과 함께 서술.
    (`E2E_EMAIL_OPERATOR_RECIPIENTS` 는 항목 7에서 처리.)
  - 근거: 가드 4번은 "README **또는** .env.example" OR 조건이라 통과하지만, DOCS_GOVERNANCE 매트릭스는
    "README 가 의미·기본값 서술"을 요구 — 카탈로그 이원화는 표류 위험.

- [ ] **13. DOCS_GOVERNANCE 갱신 + 리뷰 문서 스냅샷 헤더**
  - 대상: `docs/DOCS_GOVERNANCE.md` §2·§3, `docs/ARCHITECTURE_REVIEW_IDEAL.md` 헤더
  - 현재→목표:
    1. SSOT 매트릭스에 `docs/otp_relay.md`(OTP 중계기 구성·서버 계약 상세)와
       `docs/ARCHITECTURE_REVIEW_IDEAL.md`(시점 고정 아키텍처 평가 — 역사 기록) 행 추가.
    2. §3 "GitHub Actions 가 이 스크립트를 실행" → 워크플로가 가드 외 **ruff·pytest 잡도** 실행함을 명시.
    3. ARCHITECTURE_REVIEW_IDEAL.md 상단에 "본문은 부록(개선 적용) **이전 시점의 스냅샷** — 본문이
       지적한 결함 다수(runtime.executor 몽키패치, suite 인라인 변이, RunService 구체 import)는 부록
       기준으로 해소됨" 명시 헤더 추가.
  - 근거: 거버넌스 문서가 관리 대상 문서 2개를 누락하면 그 문서들은 규칙 밖에서 표류한다.
    리뷰 문서는 시점 라벨이 없으면 '문서 주장 vs 코드' 대조에서 거짓 양성을 만든다(이번 분석에서 실제 경험).

## 3단계 — 가드 강화 (2단계 문서 정정이 선행돼야 통과)

- [ ] **14. 정합성 가드 확장 — 양방향·스캔 범위·유령 변수·트리 실재 검증**
  - 대상: `scripts/check_docs_consistency.py`, `docs/DOCS_GOVERNANCE.md` §3(검사 항목 목록 동기화)
  - 현재→목표(4개 확장):
    1. **라우트 양방향 검사** — 현재는 코드→문서만 검사해 문서에만 있는 유령 라우트를 통과시킴.
       §5.2 의 `METHOD /path` 가 코드에 없으면 실패.
    2. **라우트 스캔 범위 확대** — 현재 `app/api/*.py` 만 glob. `app/auth/router.py`(문서화된
       `/login`·`/auth/*` 가 현재 **미검증**)와 `app/main.py` 의 `@app.get`(`include_in_schema=False` 제외) 포함.
    3. **유령 환경변수 검출** — README/.env.example 에 있으나 코드가 읽지 않는 변수 실패 처리.
    4. **§4 트리 실재 검증** — E2E_ARCHITECTURE §4 에 나열된 파일 경로가 실제 존재하는지 확인
       (이번에 발견된 유령 `index.html` 재발 방지).
  - 근거: 기존 가드가 전부 초록인 상태에서 유령 index.html·auth 라우트 미검증 등 표류가 실존 —
    단방향 검사의 구조적 사각. 기계 검증 가능한 사실은 기계가 지키는 것이 거버넌스 선언과 일치.
  - 의존: 항목 5, 6, 7, 9, 12, 15 선행(문서가 맞아야 확장 가드가 통과).

## 4단계 — 확인 필요 (근거 불충분 → 방향 결정 후 실행)

- [ ] **15. [확인 필요] 아이콘/정적 라우트의 문서화 정책 결정**
  - 대상: `app/main.py:308-323`(`GET /favicon.ico`, `/apple-touch-icon*.png`), `/static`·`/artifacts` 마운트,
    `E2E_ARCHITECTURE.md` §5.2, 가드
  - 쟁점: §5.2(API 목록 SSOT)에 미기재된 코드 전용 라우트. 선택지 —
    (a) §5.2 에 '인프라 라우트' 소절로 기재, (b) `include_in_schema=False` 라우트는 문서화 대상 제외
    규칙을 DOCS_GOVERNANCE 에 명문화하고 가드도 동일 규칙 적용. **항목 14 이전에 결정 필요.**

- [ ] **16. [확인 필요] settings 의 시스템별 메일 수신자 하드코딩 제거 여부**
  - 대상: `app/core/settings.py:21,82-99,152-161` (`_KNOWN_EMAIL_RECIPIENT_SYSTEMS` + 시스템별 필드 6종)
  - 쟁점: 새 시스템 추가 시 manifest 외에 settings 도 수정해야 함(단일 정보원 위반). 미등록 코드는
    `os.getenv` 폴백이 있으나 pydantic-settings 의 `.env` 로딩을 타지 않아 비대칭. 이상형은
    registry(manifest) 기반 동적 해석 + dotenv 맵 조회 통일 — 구현 방식 결정 필요.
  - 근거: "새 시스템 추가 = manifest + 시나리오 문서" 확장 계약(DOCS_GOVERNANCE §5)을 코드가 온전히 지키게.

- [ ] **17. [확인 필요] 목표 아키텍처 서사의 SSOT 단일화 (E2E §13 vs 리뷰 문서 #3)**
  - 대상: `E2E_ARCHITECTURE.md` §10~§13, `docs/ARCHITECTURE_REVIEW_IDEAL.md` 개선안 #3
  - 쟁점: §13 은 out-of-process 워커·Playwright MCP 를 목표로 유지, 리뷰 문서 #3 은 "(A) in-process 로
    정직하게 축소 vs (B) 진짜 워커 분리" 택일을 요구(부록에서 (B)는 검증 불가로 의도적 보류).
    목표 상태가 두 문서에 이원 서술 — SSOT 매트릭스상 아키텍처 SSOT 인 E2E_ARCHITECTURE.md 로
    단일화하고 리뷰 문서는 역사 기록으로 참조만 남길지 결정. **항목 13 이후 처리.**

---

## 일치 확인(변경 불요) 기록 — 재검토 시 중복 조사 방지용

아래는 이번 분석에서 코드와 문서가 **일치함을 확인**한 대표 항목이다(전수 아님).

- manifest 6종 ↔ 시나리오 문서 6종: 모듈 id/순서/의존성/timeout/`requires_user_input`/인증수단 일치
  (hom·mhm 300s/180s 타임아웃 구분, fp 120/300/420, hrp 120/180/180/180, hwtc 120/180/180, chbot 120/180/120).
- 상태 3분류·레거시 FAILED 처리: `app/core/enums.py`·`status_labels.py`(ADMIN_VISIBLE / RUN_DAILY_PURGE /
  TERMINAL_OUTCOME 상수)가 README·E2E §5.3 서술과 일치.
- WS 이벤트 목록(§9) ↔ 코드 발행 지점 일치(run_* 6종 + module_* 5종 / suite_* 9종).
- §5.2 API 목록의 모든 항목이 코드에 실존(역방향 유령 없음 — 단 가드가 이를 검증하지 않는 것이 항목 14).
- OTP 중계(README·otp_relay.md)의 토큰 503/401/400/404 계약, 상수시간 비교, 코드 미저장 — 코드와 일치.
- 스케줄러 tick 20s, 보존 정리 기본 `0 3 * * *`·ERROR/CANCELLED 만 삭제, ops 링 버퍼 250건,
  치유 기본 임계 0.75·정책 리더 TTL 5s·`>> nth=0` 핀 — 문서 수치와 일치.
- `run.model_dump`/`suite.model_dump` 직접 직렬화 없음(RunView/SuiteView 경유) — 주장대로.
- 컴포지션 루트 배선(main.py): SQLite 어댑터 기본 + InMemory Run/Suite InputStore(Phase 1) — CLAUDE.md 와 일치.
