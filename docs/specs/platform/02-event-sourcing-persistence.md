# SPEC-PLATFORM-002: 이벤트 소싱·영속

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-PLATFORM-002` |
| **상태** | `approved` |
| **우선순위** | P0 |
| **의존** | `SPEC-PLATFORM-001` |
| **SSOT 링크** | `docs/E2E_ARCHITECTURE.md` §2 |
| **구현 위치** | `app/platform/eventing/`, `app/contexts/run/infrastructure/`, `app/contexts/suite/infrastructure/` |

## 1. 개요

### 1.1 목적

Run/Suite 상태의 진실을 append-only `domain_events` 스트림으로 두고, `aggregate_snapshots`·CQRS projection을 파생 캐시로 유지한다.

### 1.2 액터

| 액터 | 설명 |
| --- | --- |
| `system` | OutboxRelay·ProjectionHandlers·스냅샷 리포지토리 |
| `operator` | REST/WS로 파생 상태 조회 |

### 1.3 범위

**In scope:**

- 이벤트 스트림·outbox·스냅샷·CQRS QueryPort·로그/PII 분리·영속 DTO

**Out of scope:**

- WebSocket 전달 (`SPEC-PLATFORM-004`)
- 브라우저 실행 (`SPEC-PLATFORM-003`)

## 2. 기능 요구사항 (FR)

### FR-001: 이벤트 스트림

- 각 이벤트는 `(aggregate_type, aggregate_id, stream_position)` 유일
- `stream_position`은 낙관적 동시성 좌표
- `decide(cmd, state) → events` / `evolve(state, event) → state` / `rebuild_state(stream)`

### FR-002: Transactional Outbox

도메인 이벤트 저장과 outbox 기록은 동일 트랜잭션. `OutboxRelay`가 fan-out:

1. `ProjectionHandlers` — CQRS 읽기 테이블
2. `EventBus` — Suite 사가·AI·메일
3. `RealtimeProjector` — WebSocket

### FR-003: 스냅샷

- `get_run` / `get_suite`는 `aggregate_snapshots.state_json`만 읽음
- 레거시 `runs`/`suites` blob 테이블은 마이그레이션 입력 전용
- CI `snapshot_validate`: 이벤트 폴드 == 라이브 스냅샷

### FR-004: CQRS 읽기

| QueryPort | 용도 |
| --- | --- |
| `RunSummaryQueryPort` | Run 목록·이전 Run 조회 |
| `ModuleHistoryQueryPort` | 모듈 이력 |
| `SuiteSummaryQueryPort` | Suite 목록 |
| `DailyStatusQueryPort` | 일간 대시보드 |
| `AnomalyInboxQueryPort` | 이상징후 인박스 |
| `StatsQueryPort` | 관리자 통계 |

QueryPort는 **Row DTO**만 반환 — `Run`/`SuiteRun` 엔티티 반환 금지 (AG-007).

### FR-005: 모듈 로그 분리

`RunLogStorePort`에 append-only 저장. `RunModuleRecord`에 `logs` 필드 없음. `get_run` 시 hydration으로만 로그 부착.

### FR-006: PII 분리

| 데이터 | 저장소 |
| --- | --- |
| Run 입력 | `RunInputStorePort` (암호화) |
| Suite 입력 | `SuiteInputStorePort` |
| 제어 상태 | `RunControlStorePort`, `SuiteControlStorePort` |
| 세션 체크포인트 | `SessionCheckpointStorePort` |

### FR-007: 영속 DTO

`RunRecord`/`SuiteRecord`는 `from_domain`/`to_domain` 매퍼로 도메인과 분리. `model_dump_json` 직접 영속 금지.

## 3. 수용 기준 (AC)

### AC-001: 프로젝션 결정성

```gherkin
Given domain_events 스트림
When scripts/rebuild_projections.py --validate
Then 라이브 projection 테이블과 재생 결과 일치
```

### AC-002: 스냅샷 결정성

```gherkin
Given Run/Suite 이벤트 스트림
When scripts/rebuild_snapshots.py --validate
Then aggregate_snapshots 와 폴드 결과 일치
```

### AC-003: 로그 비영속

```gherkin
Given 모듈 실행 중 로그 100줄
When Run 스냅샷 저장
Then state_json 에 logs 필드 없음
And run_logs 테이블에 100행 append
```

## 4. API 계약 (해당 시)

해당 없음 — 읽기 API는 각 도메인 Spec이 정의.

## 5. 상태·이벤트 (해당 시)

### 5.1 이벤트 소싱 불변식

| 불변식 | 설명 |
| --- | --- |
| 단일 진실 | `domain_events` append-only |
| 스냅샷 | 폴드 캐시 — 재생 가능 |
| 로그 | 도메인 이벤트 아님 — `RunLogStorePort` 직행 |

## 6. 데이터 모델 (해당 시)

```text
RunRecord / RunModuleRecord / SuiteRecord — app/contexts/*/contracts/records.py
Query Row DTO — app/contexts/*/contracts/query_rows.py
```

## 7. 엣지 케이스·오류 처리

| 상황 | 기대 동작 | HTTP/WS |
| --- | --- | --- |
| 프로세스 재기동 중 RUNNING Run | 체크포인트 없으면 `CANCELLED` 봉인 | — |
| 레거시 FAILED 상태 | ANOMALY로 정규화 표시 | — |
| outbox relay 실패 | 재시도·로그 (구독자 격리) | — |

## 8. 비기능 요구사항 (NFR)

| ID | 요구사항 |
| --- | --- |
| NFR-001 | QueryPort는 blob 재수화 경로를 제공하지 않음 (AG-007) |
| NFR-002 | PII는 스냅샷 JSON에 포함하지 않음 — 별도 InputStore |
| NFR-003 | 프로젝션 재생은 결정적이어야 함 (CI gate) |

## 9. 테스트 요구사항

| AC | 유형 | 위치 | 내용 |
| --- | --- | --- | --- |
| AC-001 | CI 게이트 | `scripts/rebuild_projections.py --validate` | 프로젝션 결정성 |
| AC-002 | CI 게이트 | `scripts/rebuild_snapshots.py --validate` | 스냅샷 결정성 |
| AC-002 | 단위 | `tests/test_snapshot_rebuild.py` | 스냅샷 폴드 |
| AC-003 | 단위 | `tests/test_storage_records.py` | `RunModuleRecord`에 logs 없음·라운드트립 |
| AC-003 | 단위 | `tests/test_module_log_pipeline.py` | 로그는 이벤트 스토어 미경유 |
| — | 단위 | `tests/test_run_decider.py`, `tests/test_suite_decider.py` | decide/evolve |
| — | 단위 | `tests/test_projection_handlers.py`, `tests/test_outbox_relay_*.py` | outbox fan-out |
| — | 단위 | `tests/test_input_crypto.py` | PII 암호화 InputStore |

## 10. 구현 힌트 (참고)

| 구성요소 | 파일 |
| --- | --- |
| Outbox | `app/platform/eventing/outbox.py` |
| Relay | `app/platform/eventing/relay.py` |
| Run decider | `app/contexts/run/domain/decider.py` |
| Run records | `app/contexts/run/contracts/records.py` |
| Run log store | `app/contexts/run/infrastructure/sqlite_run_log_store.py` |

## 11. 변경 이력

| 날짜 | 변경 | 작성자 |
| --- | --- | --- |
| 2026-08-15 | 역공학 초안 | — |
| 2026-08-15 | `_TEMPLATE.md` 정합·테스트 매핑 | SDD 보강 |
