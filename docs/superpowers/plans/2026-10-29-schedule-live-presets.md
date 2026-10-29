# 예약 최신 프리셋 참조 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 프리셋 변경이 기존 예약의 다음 실행에 반영되도록 한다.

**Architecture:** 예약에는 소유자별 프리셋 ID를 저장한다. 실행 준비에서 참조를 해석하고 Run/Suite 시작 시 입력을 확정한다. 기존 예약은 유일하게 일치하는 프리셋으로 전환하며 모호한 경우 편집으로 연결한다.

**Tech Stack:** Python/FastAPI/Pydantic/SQLite, TypeScript/Vite/Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-10-28-schedule-live-presets-design.md`

## Global Constraints

- UI·로그·README 문자열은 한국어로 작성한다.
- 예약 생성자 기준 소유권을 검증하며 인증값을 응답/로그에 노출하지 않는다.
- 진행 중인 실행 입력, 예약의 모듈·시스템·브라우저 설정은 유지한다.
- 기존 직접 입력 API와 연결되지 않은 기존 예약은 호환한다.

## Review Focus

- 관리자가 타인 예약을 실행/복제할 때 타인 프리셋을 자기 것으로 오인하지 않는다.
- 프리셋 삭제 후 저장된 인증값으로 자동 회귀하지 않는다.
- 여러 프리셋이 일치하면 후보를 임의로 선택하지 않는다.
- 수트 중간에 프리셋 변경이 있어도 시작 때 확정한 입력을 사용한다.
- 단일 폼의 저장되지 않은 수정값은 조용히 무시하지 않는다.

### Task 1: 참조 해석과 예약 실행

**Files:** `app/core/requests.py`, `app/core/schedule_models.py`, `app/contexts/scheduling/preset_bindings.py`(신규), `scheduler.py`, `composition.py`, `app/composition/container.py`, `tests/test_schedule_live_presets.py`(신규).

**Interfaces:** `SchedulePresetBindings(repository)`가 `resolve(schedule)`, `migrate(schedule)`, `describe(schedule)`를 제공한다. SchedulerService는 선택적 프리셋 저장소를 주입받는다. DTO에 단일 `preset_id`, 수트 `preset_ids`, 단일 예약 `browser_mode`를 추가한다.

- [x] pytest로 최신값·새 필드·소유권/시스템·삭제·브라우저 보존·실행 입력 고정 검증을 작성하고 실패를 확인한다.
- [x] 참조 조회와 생성/수정 검증, 실행 전 조회·오류 영속, composition을 구현한다.
- [x] `pytest tests/test_schedule_live_presets.py tests/test_schedule_suite_browser_mode.py tests/test_schedule_center.py -q` 통과를 확인한다.

### Task 2: 기존 예약 전환과 편집 API

**Files:** Task 1 파일, `app/api/routes_schedules.py`, `tests/test_schedule_live_presets.py`.

**Interfaces:** 시작/실행 준비에서 멱등 전환; 상세에 인증값 없는 `preset_bindings`, `preset_options`, `preparation_error` 제공. 변경 요청에서 ID 교체 가능.

- [x] 유일/모호/불일치/타인 후보, DB 재로드, 참조 교체, 관리자 복제, 자동 실패 후 다음 예약 계속 실행을 테스트하고 실패를 확인한다.
- [x] 전환·상세 메타·편집·복제 처리를 구현한다. 다른 소유자로 복제할 때 참조를 거부한다.
- [x] Task 1 검증 명령과 예약 HTTP 테스트를 실행한다.

### Task 3: 생성·편집 화면과 문서

**Files:** `app/web/frontend/execute/{presets,run-form,suite-form}.ts`, `app/web/static/schedules.js`, `app/web/templates/mobile_trigger.html`, `docs/E2E_ARCHITECTURE.md`, `docs/specs/{scheduling/01-scheduler,presets/01-auth-presets}.md`, 프론트 회귀 테스트.

**Interfaces:** 생성 폼은 선택한 ID를 전달하고 수동 실행은 기존 입력 전송을 유지한다. 예약 편집은 소유자의 후보 메타만 사용한다.

- [x] 폼 ID 전달·미저장 입력 차단·브라우저 보존 테스트를 작성하고 실패를 확인한다.
- [x] 생성/편집 및 연결 상태·오류 표시와 문서를 구현한다.
- [x] `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`, 문서 정합 검사를 실행한다.

### Task 4: 전체 검증과 독립 리뷰

- [x] `python scripts/ci/run_all_gates.py --profile full`을 백그라운드 실행하고 결과를 확인한다.
- [x] 별도 리뷰어가 전체 변경과 설계를 대조한다. 중요한 발견은 회귀 테스트로 재현 후 수정한다.
- [x] 수정 내역과 검증 결과를 보고한다. 승인된 구현 범위 안에서 계속 진행하며 추가 실행 방식 확인은 요청하지 않는다.
