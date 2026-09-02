# Task 2 완료 보고서 — 사용자용 커버리지·드릴다운 라우트

## 구현 범위

- `GET /api/runs/coverage`는 admin에게 전체 시스템(`None`)을, 일반 사용자에게는 `allowed_system_codes`의 `frozenset`을 전달한다.
- `GET /api/runs/day`는 시스템 권한을 먼저 확인하고, 요청자 ID가 아닌 요청한 시스템 코드와 KST 기준 하루 범위로 Run을 조회한다.
- 드릴다운 응답에서는 `created_by_user_id`와 `created_by_user_name`을 제거해 실행자 PII를 노출하지 않는다.
- 두 정적 라우트는 `/{run_id}` 라우트보다 위에 선언되어 동적 경로와 충돌하지 않는다.

## 사용자 승인 계획 보정

승인된 계획서의 `_user()` 예시는 현재 `User` 모델의 필수 계약을 모두 반영하지 못했다. 사용자 승인에 따라 `hashed_password="x"`와 `created_at=datetime(2026, 9, 1, tzinfo=UTC)`를 사용했으며, 비결정적인 `datetime.now`는 사용하지 않았다. 이 보정은 권한 축(D8), 라우트 계약(D2), PII 제거(D9)의 의도를 변경하지 않는다.

## 검증

원래 Task 2의 Step 4와 Step 5 명령만 실행했다.

- `python -m pytest tests/test_runs_coverage_api.py tests/test_admin_runs_api.py tests/test_run_list_scope.py -v` — 16 passed
- `python -m pytest tests/test_admin_coverage_dashboard.py tests/test_admin_dashboard_runs.py tests/test_admin_runs_http.py -v` — 30 passed
